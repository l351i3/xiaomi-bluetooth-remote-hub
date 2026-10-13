#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATVV 常驻语音服务 v1.2 (T1) — RC003 语音流 → 实时 UDP 双播 Mac + Windows

链路: RC003 按住语音键 → (BLE/ATVV) → 本服务(常驻)
      → UDP :8789 → Mac + Windows（目标地址由 presence 心跳学习; 常量回退; 离线跳过）
v1.2 (2026-10-14): presence 接线 —— 投递地址去硬编码 + 体面断开:
                   目标 IP 优先取心跳学习地址（state/presence.json; MAC_IP/WIN_IP 降级 fallback）;
                   目标「明确离线」（3 拍无心跳）→ 跳过发送（边沿日志; 恢复自动继续）;
                   降级安全: 守护未部署/快照过期 -> unknown, 维持旧行为（照旧投递常量地址）。
v1.1 (2026-10-11): 双目标发送（Windows 音频链接入；接收端 windows/win_audio_receiver.py）；
                   单目标失败不影响其他目标（错误日志按目标 60s 节流）。
协议 T1→接收端 (每包 = [1B type][payload]):
  0x01 audio 帧 (payload = 120B IMA ADPCM)
  0x02 会话开始 (payload = 1B sid)
  0x03 会话结束 (payload 空)
特性: 事件驱动（AUDIO_START 起 / STOP 止）; 每 2s MIC_EXTEND 防断流;
      BlueZ/遥控器离线自动退避重挂; UDP 无接收方时静默丢弃（无害）
运行: cd /root/remote-hub; nohup /usr/bin/python3 -u atvv_service.py >> /var/log.hdd/atvv_service.log 2>&1 < /dev/null &
"""
import os
import select
import socket
import time
import traceback

import dbus

try:  # v1.2: presence 心跳读端（降级: 无 presence.py -> None, 全程回退常量投递）
    from presence import StateView as _StateView
except Exception:  # noqa: BLE001
    _StateView = None

MAC = "C0:5D:39:XX:XX:XX"
SVC_UUID = "ab5e0001"
RX_UUID = "ab5e0002"
AU_UUID = "ab5e0003"
CT_UUID = "ab5e0004"

GET_CAPS = [0x0A, 0x01, 0x00, 0x00, 0x03, 0x03]
MIC_OPEN = [0x0C, 0x00]
MIC_CLOSE = [0x0D]

MAC_IP = "MACOS_IP"    # macOS —— v1.2: fallback（优先用心跳学习地址）
WIN_IP = "WINDOWS_IP"    # Windows（10-11 接入音频链）—— v1.2: fallback
UDP_PORT = 8789
_TARGETS = (("mac", MAC_IP, UDP_PORT), ("win", WIN_IP, UDP_PORT))   # v1.2: 角色-常量-端口（投递时动态解析）
T_EXTEND = 2.0


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg, flush=True)


# ---- v1.2: presence 投递闸门（地址动态化 + 离线跳过） ----
_pv = _StateView() if _StateView else None   # 读端热缓存（0.5s 节流 + mtime 缓存）
_pv_offline = set()                          # 已报告过离线的 role（边沿日志: 离线/恢复各一条）


def _dests():
    """v1.2: 动态目标表 [(role, ip, port)...] —— 心跳 IP 优先/常量回退;
    明确离线 -> 跳过（边沿日志）; unknown/守护未就绪 -> 降级旧行为（常量）。"""
    out = []
    for role, fb, port in _TARGETS:
        if _pv is not None:
            if _pv.device_state(role) == "offline":
                if role not in _pv_offline:
                    _pv_offline.add(role)
                    log(f"presence: {role} 离线（心跳超时）, 暂停音频发送")
                continue
            ip = _pv.ip_of(role) or fb
            if role in _pv_offline:
                _pv_offline.discard(role)
                log(f"presence: {role} 已恢复心跳, 恢复音频发送")
        else:
            ip = fb
        if ip:
            out.append((role, ip, port))
    return out


def arr76(vals):
    return dbus.Array([dbus.Byte(x) for x in vals], signature="y")


def einfo():
    return dbus.Dictionary({}, signature="sv")


_last_err = {}


def send_all(sock, payload):
    """v1.2 双目标发送: 单目标失败不影响其他目标; 错误日志按目标 60s 节流。
    目标表每次动态解析（presence 心跳地址优先; 明确离线的目标跳过）。"""
    for _role, _ip, _port in _dests():
        dst = (_ip, _port)
        try:
            sock.sendto(payload, dst)
            _last_err.pop(dst, None)
        except OSError as e:
            now = time.time()
            if now - _last_err.get(dst, 0.0) > 60.0:
                _last_err[dst] = now
                log("send -> %s:%d 失败(60s节流): %s" % (dst[0], dst[1], e))


def run_once(sock):
    """一轮: 连接 ATVV 并服务直到异常/断开"""
    bus = dbus.SystemBus()
    om = dbus.Interface(bus.get_object("org.bluez", "/"),
                        "org.freedesktop.DBus.ObjectManager")
    objs = om.GetManagedObjects()
    dev_frag = MAC.replace(":", "_")
    svc_uuid = {}
    chars = {}
    for path, ifaces in objs.items():
        if "org.bluez.GattService1" in ifaces:
            svc_uuid[str(path)] = str(ifaces["org.bluez.GattService1"].get("UUID", "")).lower()
        if "org.bluez.GattCharacteristic1" in ifaces:
            c = ifaces["org.bluez.GattCharacteristic1"]
            chars[str(path)] = (str(c.get("UUID", "")).lower(), str(c.get("Service", "")))
    atvv_svc = None
    for p, u in svc_uuid.items():
        if u.startswith(SVC_UUID) and dev_frag in p:
            atvv_svc = p
            break
    if not atvv_svc:
        raise RuntimeError("ATVV svc 未找到(遥控器离线?)")
    found = {}
    for p, (u, s) in chars.items():
        if s == atvv_svc:
            found[u.split("-")[0]] = p
    wpath = found.get(RX_UUID)
    apath = found.get(AU_UUID)
    cpath = found.get(CT_UUID)
    if not (wpath and apath and cpath):
        raise RuntimeError("ATVV 特征不全")

    def cif(p):
        return dbus.Interface(bus.get_object("org.bluez", p), "org.bluez.GattCharacteristic1")

    w = cif(wpath)
    fd_a, mtu_a = cif(apath).AcquireNotify(einfo())
    fd_c, mtu_c = cif(cpath).AcquireNotify(einfo())
    rfd_a = fd_a.take() if hasattr(fd_a, "take") else int(fd_a)
    rfd_c = fd_c.take() if hasattr(fd_c, "take") else int(fd_c)
    log("已连接 ATVV (mtu=%s/%s), 进入事件循环" % (mtu_a, mtu_c))
    try:
        w.WriteValue(arr76(GET_CAPS), einfo())
        log("GET_CAPS 已发送")
        streaming = False
        sid = 0
        last_extend = 0.0
        n_frames = 0
        t_start = 0.0
        while True:
            r, _, _ = select.select([rfd_a, rfd_c], [], [], 0.5)
            for fd in r:
                data = os.read(fd, 4096)
                if not data:
                    raise RuntimeError("notify fd EOF(连接断开)")
                if fd == rfd_c:
                    if data[0] == 0x04 and not streaming:
                        streaming = True
                        sid = data[3] if len(data) >= 4 else 0
                        w.WriteValue(arr76(MIC_OPEN), einfo())
                        last_extend = time.time()
                        t_start = last_extend
                        n_frames = 0
                        send_all(sock, bytes([0x02, sid & 0xFF]))
                        log("会话开始 sid=%d (MIC_OPEN)" % sid)
                    elif data[0] == 0x00 and streaming:
                        streaming = False
                        w.WriteValue(arr76(MIC_CLOSE), einfo())
                        send_all(sock, bytes([0x03]))
                        log("会话结束 sid=%d: %d 帧 / %.2fs (MIC_CLOSE)" % (sid, n_frames, time.time() - t_start))
                else:  # AUDIO
                    n_frames += 1
                    send_all(sock, bytes([0x01]) + bytes(data))
            if streaming and (time.time() - last_extend) > T_EXTEND:
                w.WriteValue(arr76([0x0E, sid & 0xFF]), einfo())
                last_extend = time.time()
    finally:
        for fd in (rfd_a, rfd_c):
            try:
                os.close(fd)
            except OSError:
                pass


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    log("atvv_service v1.2 启动 -> " + ", ".join("%s@%s:%d" % d for d in _dests())
        + (" | presence=on" if _pv else " | presence=off"))
    backoff = 2.0
    while True:
        try:
            run_once(sock)
            backoff = 2.0
        except Exception as e:
            log("!! %s: %s" % (type(e).__name__, e))
            if "未找到" in str(e) or "不全" in str(e):
                time.sleep(10.0)
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)


if __name__ == "__main__":
    main()
