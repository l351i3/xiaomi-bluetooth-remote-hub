#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# presence.py — T1 端「设备在线注册中心」 v1.0 (2026-10-13)
#
# 目标（用户 10-13 拍板）: 体面断开 / 优雅连上 + 投递地址（IP）去硬编码。
#
# 【协议】UDP :8790（局域网，无鉴权，与现有链路一致）
#   客户端 → T1:  "PRESENCE <role> <svc> <port>"   role ∈ mac/win/atv; svc 自由串
#                 · 接收端启动即拍（首拍 = IP 学习源），之后 2s 一拍
#                 · 无 ACK 自适应退避 4s→8s→15s（封顶）；收到 ACK 立即复位 2s
#   T1 → 客户端:  "PRESENCE-ACK"（仅回执，无查询接口）
#   本机读端（webui / voice_fwd / atvv_service）经 state/presence.json 读状态。
#
# 【状态机】online --（6s=3 拍无心跳）--> offline --（任一拍到达）--> online
#   · 判定离线 = 服务真的死了/机器离开网络（UDP 心跳证活，不是 ping 设备）
#   · 投递闸门: 目标明确离线 → 跳过投递（读端留一行明确日志），杜绝"假已发送"
#
# 【自动切换】（用户需求: 离线设备不能选、自动跳到在线设备）
#   · desired = 用户手动选择的目标（记忆；经 voice_target 文件与 webui 交互）
#   · 当前目标离线持续 ≥12s 且存在在线设备 → 切到优先级最高的在线设备（mac>win>atv）
#     并向 voice_target 写新目标（复用现有热重载通道），auto=True
#   · desired 连续在线 ≥10s → 自动切回 desired，auto=False（优雅回归）
#   · 用户在网页手动切换（voice_target 被外部改写）→ desired=该值, auto=False
#   · 全部设备离线 → 不切（保留记忆，回连后自动恢复）
#
# 【降级】守护失效（presence.json 过期 >90s）/ 文件缺失/损坏 → 读端按"未知"处理，
#   维持旧行为（照旧投递）。读端永不因本服务而阻塞（纯文件读取 + mtime 缓存）。
#
# 【资源】T1 侧: 1 条 UDP socket + 1s 超时的阻塞循环（空闲 CPU≈0）；状态文件
#   仅在"状态变化/切换/手动检测"时立即原子写 + 每 30s 周期刷新（约 1KB/30s）。
#   客户端: 心跳线程阻塞在 recv 上，正常 2s 一个 ~30B 小包；T1 不在时自动退避。
#
# 【测试】纯逻辑类 Presence 不碰 socket（时间由参数注入）→ presence_test.py 离线全测。
# 运行: systemctl restart t1-presence
#   (手动: cd /root/remote-hub; nohup /usr/bin/python3 presence.py >> /var/log.hdd/presence.log 2>&1 < /dev/null &)
import json
import os
import socket
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
STATE_PATH = os.path.join(STATE_DIR, "presence.json")
TARGET_FILE = os.path.join(HERE, "voice_target")
PORT = 8790

ROLES = ("mac", "win", "atv")
PRIORITY = ("mac", "win", "atv")   # 自动切换挑选取序（用户定: mac > win > atv）
TTL_OFFLINE = 6.0                  # 无心跳判定离线（3 拍 @2s）
CONFIRM_SWITCH = 12.0              # 目标离线持续该时长才自动切换（防抖动误切）
CONFIRM_RESTORE = 10.0             # desired 连续在线该时长才自动切回
WRITE_INTERVAL = 30.0              # 状态文件周期刷新（守护存活凭据）
STATE_MAX_AGE = 90.0               # 读端: 快照超过该时长未刷新 → 视为守护失效, 降级
EVENTS_KEEP = 8                    # 快照里保留的最近事件条数

def log(msg):
    print(time.strftime("%F %T") + " " + msg, flush=True)


# ============================ 状态表 + 决策（纯逻辑） ============================

class Presence:
    """在线状态表 + 自动切换决策。不碰 socket、不读系统时钟（now 由参数注入），
    便于离线测试；main() 负责套接字与真实时钟。"""

    def __init__(self, state_path=STATE_PATH, target_path=TARGET_FILE, log_fn=None):
        self.state_path = state_path
        self.target_path = target_path
        self._log = log_fn or log
        self.devices = {}       # role -> {ip, last_seen, state, since, svcs:{svc:{port,last_seen}}}
        self.desired = None     # 用户手动选定的目标（记忆）
        self.auto = False       # 当前目标是否由自动切换写入
        self.target = None      # 本进程视角的当前目标（与 voice_target 文件同步）
        self._file_mtime = None # 上次读/写 voice_target 后的 mtime_ns（外部变更检测）
        self._last_write = 0.0
        self.dirty = True       # 有变化待落盘
        self.events = []        # [(ts, kind, text)] 最近事件（UI 提示用）
        self._bad_log_t = 0.0   # 非法心跳日志节流

    # ---------------- 状态文件 ----------------

    def load(self):
        """启动加载: 恢复 devices/desired/auto; 损坏文件隔离为 .bad-<ts>。
        注意: 恢复的设备一律先置 offline（重启后未收到本机拍前不信任），首拍即上线。"""
        snap = None
        try:
            with open(self.state_path) as f:
                snap = json.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            bad = self.state_path + ".bad-" + time.strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(self.state_path, bad)
            except Exception:  # noqa: BLE001
                pass
            self._log("presence.json 损坏(%r), 已隔离 -> %s" % (e, os.path.basename(bad)))
        now = time.time()
        if isinstance(snap, dict) and snap.get("v") == 1:
            for role, d in (snap.get("devices") or {}).items():
                if role not in ROLES or not isinstance(d, dict):
                    continue
                try:
                    last = float(d.get("last_seen") or 0.0)
                except (TypeError, ValueError):
                    last = 0.0
                self.devices[role] = {
                    "ip": d.get("ip"), "last_seen": last, "state": "offline", "since": now,
                    "svcs": {k: {"port": v.get("port"), "last_seen": float(v.get("last_seen") or 0.0)}
                             for k, v in (d.get("svcs") or {}).items() if isinstance(v, dict)},
                }
            if snap.get("desired") in ROLES:
                self.desired = snap["desired"]
                self.auto = bool(snap.get("auto"))
            self._log("状态已恢复: %d 设备记录 (desired=%s, auto=%s)"
                      % (len(self.devices), self.desired, self.auto))
        self.target = self._read_target_file()
        if self.desired not in ROLES:
            self.desired = self.target
            self.auto = False
        self._file_mtime = self._stat_target()

    def _stat_target(self):
        try:
            return os.stat(self.target_path).st_mtime_ns
        except Exception:  # noqa: BLE001
            return None

    def _read_target_file(self):
        try:
            with open(self.target_path) as f:
                t = f.read().strip()
            return t if t in ROLES else "mac"
        except Exception:  # noqa: BLE001
            return "mac"

    def _write_target(self, t):
        """原子写 voice_target（复用现有热重载通道; 格式与 webui 一致: 值 + \\n）"""
        tmp = self.target_path + ".tmp-presence"
        with open(tmp, "w") as f:
            f.write(t + "\n")
        os.replace(tmp, self.target_path)
        self.target = t
        self._file_mtime = self._stat_target()

    def _event(self, kind, text, now):
        self.events.append((now, kind, text))
        if len(self.events) > EVENTS_KEEP:
            del self.events[:len(self.events) - EVENTS_KEEP]
        self._log(text)

    # ---------------- 心跳 ----------------

    def handle(self, data, ip, now):
        """处理一条心跳 "PRESENCE <role> <svc> <port>"; 返回是否应答 ACK。"""
        try:
            parts = data.decode("utf-8", "replace").split()
        except Exception:  # noqa: BLE001
            return False
        if len(parts) != 4 or parts[0] != "PRESENCE":
            if now - self._bad_log_t > 60.0:
                self._bad_log_t = now
                self._log("忽略非法心跳: %r" % (data[:80],))
            return False
        role, svc = parts[1], parts[2]
        try:
            port = int(parts[3])
        except ValueError:
            return False
        if role not in ROLES or not svc or len(svc) > 24 or not (0 <= port <= 65535):
            if now - self._bad_log_t > 60.0:
                self._bad_log_t = now
                self._log("忽略非法心跳 (role=%s svc=%s port=%s)" % (role, svc, parts[3]))
            return False

        dev = self.devices.get(role)
        if dev is None:
            dev = self.devices[role] = {"ip": ip, "last_seen": 0.0, "state": "offline",
                                        "since": now, "svcs": {}}
        new_ip = dev.get("ip") is not None and dev.get("ip") != ip   # IP 漂移 = 有意义变化
        new_svc = svc not in dev["svcs"]                              # 新服务项 = 有意义变化
        dev["ip"] = ip
        dev["last_seen"] = now
        dev["svcs"][svc] = {"port": port, "last_seen": now}
        if dev["state"] != "online":
            was = dev["state"]
            dev["state"] = "online"
            dev["since"] = now
            self.dirty = True
            self._event("presence", "%s 上线 (%s; %s:%d; 前态=%s)"
                        % (role, ip, svc, port, was), now)
        elif new_ip or new_svc:
            self.dirty = True
            if new_ip:
                self._event("presence", "%s 地址更新 -> %s（心跳学习）" % (role, ip), now)
        return True

    # ---------------- 周期推进 ----------------

    def tick(self, now):
        """① 离线判定 ② 外部手动切换检测 ③ 自动切换/回切。返回是否有变化。"""
        # ① 超时 → 离线
        for role, dev in self.devices.items():
            if dev["state"] == "online" and (now - dev["last_seen"]) > TTL_OFFLINE:
                dev["state"] = "offline"
                dev["since"] = now
                self.dirty = True
                last = time.strftime("%F %T", time.localtime(dev["last_seen"])) if dev["last_seen"] else "-"
                self._event("presence", "%s 离线（%.0fs 无心跳; ip=%s; 最后在线 %s）"
                            % (role, now - dev["last_seen"], dev["ip"], last), now)

        # ② 外部手动改 voice_target（webui 点击 / 终端写入）→ 用户意图更新
        m = self._stat_target()
        if m != self._file_mtime:
            self._file_mtime = m
            t = self._read_target_file()
            if t != self.target:
                self._event("manual", "目标 -> %s（手动）" % t, now)
            else:
                self._log("目标 %s 被手动重申（auto 清除）" % t)
            self.target = t
            self.desired = t
            self.auto = False
            self.dirty = True

        # ③ 回切（优先判定：desired 稳定在线 → 回到用户选定的设备）
        if self.auto and self.desired in ROLES and self.desired != self.target:
            ddev = self.devices.get(self.desired)
            if ddev and ddev["state"] == "online" and (now - ddev["since"]) >= CONFIRM_RESTORE:
                self._write_target(self.desired)
                self.auto = False
                self.dirty = True
                self._event("switch", "自动切回 %s（已连续在线 %.0fs）"
                            % (self.desired, now - ddev["since"]), now)
        # ③ 切走（当前目标离线且确认非抖动）
        cdev = self.devices.get(self.target)
        if cdev and cdev["state"] == "offline" and (now - cdev["since"]) >= CONFIRM_SWITCH:
            pick = None
            for r in PRIORITY:
                if r == self.target:
                    continue
                d = self.devices.get(r)
                if d and d["state"] == "online":
                    pick = r
                    break
            if pick:
                cur = self.target
                if not self.auto:
                    self.desired = cur               # 记住用户的选择, 回连后切回
                self._write_target(pick)
                self.auto = True
                self.dirty = True
                self._event("switch", "目标 %s 离线 → 自动切到 %s（desired=%s）"
                            % (cur, pick, self.desired), now)
        return self.dirty

    # ---------------- 落盘 ----------------

    def snapshot(self, now):
        return {
            "v": 1, "ts": now, "pid": os.getpid(),
            "ttl": TTL_OFFLINE, "confirm_switch": CONFIRM_SWITCH, "confirm_restore": CONFIRM_RESTORE,
            "devices": {r: {"ip": d["ip"], "state": d["state"], "last_seen": d["last_seen"],
                            "since": d["since"],
                            "svcs": {k: {"port": v["port"], "last_seen": v["last_seen"]}
                                     for k, v in d["svcs"].items()}}
                        for r, d in self.devices.items()},
            "target": self.target, "desired": self.desired, "auto": self.auto,
            "hostname": socket.gethostname(),
            "events": [[round(e[0], 3), e[1], e[2]] for e in self.events],
        }

    def write(self, now, force=False):
        """原子写状态快照; 周期节流（变化即刻写, 无变化每 30s 刷新保活）。"""
        if not force and not self.dirty and (now - self._last_write) < WRITE_INTERVAL:
            return False
        d = os.path.dirname(self.state_path) or "."
        try:
            os.makedirs(d, exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.snapshot(now), f, ensure_ascii=False, indent=1)
                f.write("\n")
            os.replace(tmp, self.state_path)
        except Exception as e:  # noqa: BLE001
            self._log("presence.json 写入失败: %r" % (e,))
            return False
        self._last_write = now
        self.dirty = False
        return True


# ============================ 读端（本机其他服务用） ============================

def read_state(path=STATE_PATH, max_age=STATE_MAX_AGE, now=None):
    """读状态快照; 缺失/损坏/过期/时钟异常 → None（读端降级 = 维持旧行为）。"""
    if now is None:
        now = time.time()
    try:
        with open(path) as f:
            snap = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(snap, dict) or snap.get("v") != 1:
        return None
    ts = snap.get("ts") or 0
    if (now - ts) > max_age or ts > now + 60.0:
        return None
    return snap


class StateView:
    """读端热路径缓存: mtime 变化才重读 JSON（voice_fwd / atvv_service 用）。
    poll() 自带最小刷新间隔节流（默认 0.5s）, 高频调用开销≈一次 stat。"""

    def __init__(self, path=STATE_PATH, refresh=0.5, max_age=STATE_MAX_AGE):
        self.path = path
        self.refresh = refresh
        self.max_age = max_age
        self._snap = None
        self._mtime = None
        self._t = 0.0

    def poll(self, now=None):
        if now is None:
            now = time.time()
        if (now - self._t) < self.refresh:
            snap = self._snap
        else:
            self._t = now
            try:
                m = os.stat(self.path).st_mtime_ns
            except Exception:  # noqa: BLE001
                m = None
            if m != self._mtime:
                self._mtime = m
                self._snap = read_state(self.path, self.max_age, now)
            snap = self._snap
        # 文件未变但已过期（守护停了）→ 降级
        if snap is not None and (now - (snap.get("ts") or 0)) > self.max_age:
            self._snap = snap = None
        return snap

    def device_state(self, role, now=None):
        snap = self.poll(now)
        if not snap:
            return "unknown"
        d = (snap.get("devices") or {}).get(role) or {}
        return d.get("state") or "unknown"

    def ip_of(self, role, now=None):
        """设备当前地址（心跳学习; 未学到返回 None → 调用方回退默认常量）"""
        snap = self.poll(now)
        if not snap:
            return None
        d = (snap.get("devices") or {}).get(role) or {}
        return d.get("ip") or None


# ============================ 守护主循环 ============================

def main():
    p = Presence()
    p.load()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(1.0)
    now = time.time()
    p.write(now, force=True)
    log("presence v1.0 启动: UDP :%d | TTL %.0fs | 自动切换=离线%.0fs后 / 回切=在线%.0fs后 | 状态 -> %s | 当前目标=%s (desired=%s auto=%s)"
        % (PORT, TTL_OFFLINE, CONFIRM_SWITCH, CONFIRM_RESTORE, p.state_path, p.target, p.desired, p.auto))
    while True:
        try:
            data, addr = sock.recvfrom(512)
        except socket.timeout:
            pass
        except KeyboardInterrupt:
            log("收到 Ctrl-C, 退出")
            return
        except OSError as e:
            log("recv 错误: %r" % (e,))
            time.sleep(0.5)
            continue
        else:
            now = time.time()
            if p.handle(data, addr[0], now):
                try:
                    sock.sendto(b"PRESENCE-ACK", addr)
                except OSError:
                    pass
        now = time.time()
        p.tick(now)
        p.write(now)


if __name__ == "__main__":
    main()
