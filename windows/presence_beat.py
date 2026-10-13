#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# presence_beat.py — 「在线注册」客户端心跳库 v1.0 (2026-10-13)
#
# 由接收端服务调用（Mac: voice_bridge/key_bridge/atvv_receiver;
# Windows: win_receiver/win_audio_receiver; T1: relay_min 上报 ATV 在线）:
#
#     import presence_beat
#     hb = presence_beat.start("mac", [("voice", 8788)], log_fn=log)
#
# 【协议】向 T1 UDP :8790 发 "PRESENCE <role> <svc> <port>"; T1 回 "PRESENCE-ACK"。
# 【节奏】启动即拍（首拍 = T1 的 IP 学习源）→ 2s/拍;
#         连续无 ACK 自适应退避 2s→4s→8s→15s（封顶; T1 不在时省资源）;
#         收到 ACK 立即复位 2s。T1 侧 6s（3 拍）无心跳判定离线。
# 【资源】空闲时线程阻塞在 recv 上（~0 CPU）; 正常流量 = 2s 一个 ~30B 小包。
# 【生命周期】随服务进程启动/退出（daemon 线程）; 亦可 hb.stop() 显式停止。
#   心跳发不出/无应答不重试落盘、不排队 —— 状态证活是"当下"语义。
import os
import socket
import threading
import time

PORT = 8790
DEFAULT_HOST = "T1_IP"      # T1（可用环境变量 PRESENCE_HOST 或同目录 presence_host 文件覆盖）
BASE_INTERVAL = 2.0
CAP_INTERVAL = 15.0
ACK_WAIT = 1.0                     # 单拍等待 ACK 上限（秒）
SEND_ERR_LOG_GAP = 60.0            # 发送错误日志节流（秒）


def resolve_host():
    """T1 地址: 环境变量 PRESENCE_HOST > 同目录 presence_host 文件 > 默认常量。"""
    h = (os.environ.get("PRESENCE_HOST") or "").strip()
    if h:
        return h
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presence_host")
        with open(p) as f:
            h = f.read().strip()
    except Exception:  # noqa: BLE001
        h = ""
    return h or DEFAULT_HOST


def next_interval(misses):
    """退避曲线（纯函数, 离线测试）: 0 拍→2s; 1→4s; 2→8s; ≥3→15s（封顶）。"""
    if misses <= 0:
        return BASE_INTERVAL
    return min(CAP_INTERVAL, BASE_INTERVAL * (2 ** min(misses, 3)))


class Heartbeat:
    """单进程一个实例（可含多个服务项, 如 win_receiver 同报 voice+key）。"""

    def __init__(self, role, services, host=None, port=PORT, log_fn=None):
        self.role = role
        self.services = [tuple(s) for s in services]   # [(svc, port), ...]
        self.host = host or resolve_host()
        self.port = port
        self._log = log_fn or (lambda m: None)
        self._stop = threading.Event()
        self._th = None
        self.misses = 0
        self.interval = BASE_INTERVAL

    def start(self):
        if self._th and self._th.is_alive():
            return self
        self._th = threading.Thread(target=self._run, name="presence-beat", daemon=True)
        self._th.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(ACK_WAIT)
        desc = ",".join("%s:%d" % s for s in self.services)
        self._log("presence: heartbeat start role=%s [%s] -> %s:%d (every %gs; backoff to %gs if no ack)"
                  % (self.role, desc, self.host, self.port, BASE_INTERVAL, CAP_INTERVAL))
        err_t = 0.0
        while not self._stop.is_set():
            t0 = time.monotonic()
            for svc, p in self.services:
                msg = ("PRESENCE %s %s %d" % (self.role, svc, p)).encode()
                try:
                    sock.sendto(msg, (self.host, self.port))
                except OSError as e:
                    now = time.monotonic()
                    if now - err_t > SEND_ERR_LOG_GAP:
                        err_t = now
                        self._log("presence: send failed (%r)" % (e,))
            got_n = 0
            deadline = time.monotonic() + ACK_WAIT
            while got_n < len(self.services):
                rem = deadline - time.monotonic()
                if rem <= 0:
                    break
                sock.settimeout(rem)
                try:
                    data, _ = sock.recvfrom(128)
                except socket.timeout:
                    break
                except OSError:
                    break
                if data.startswith(b"PRESENCE-ACK"):
                    got_n += 1
            got = got_n > 0
            if got:
                if self.misses:
                    self._log("presence: ack resumed (was %d misses)" % self.misses)
                self.misses = 0
                self.interval = BASE_INTERVAL
            else:
                self.misses += 1
                ni = next_interval(self.misses)
                if ni != self.interval:
                    self.interval = ni
                    self._log("presence: no ack x%d -> backoff %gs" % (self.misses, ni))
            remaining = max(0.05, self.interval - (time.monotonic() - t0))
            if self._stop.wait(remaining):
                break
        sock.close()
        self._log("presence: heartbeat stopped (role=%s)" % self.role)


def start(role, services, host=None, port=PORT, log_fn=None):
    """便捷入口: 建实例并立刻启动（启动即拍）。返回 Heartbeat（可 .stop()）。"""
    return Heartbeat(role, services, host=host, port=port, log_fn=log_fn).start()
