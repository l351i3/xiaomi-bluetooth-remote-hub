#!/usr/bin/env python3
# voice_fwd.py — T1 端「遥控器键 · 非ATV目标转发器」 v2.4 (2026-10-12)
#
# v2.1（10-10 17:1x）: 用户态自建连发 —— 修复「长按不连发」。
#   实证（17:05 用户实测长按 BACKSPACE 2s）: 遥控器（bluez-hog-device）的
#   capabilities/rep 为空 —— 设备不支持 EV_REP, 长按期间 evdev 零事件
#   （既无 val=2 也无重发 DOWN）。原「连发=靠内核软重复(val=2)节流转发」的设计
#   对 Mac 目标从未真正生效（方向键同理——历史日志全为短按配对, 无连发痕迹）。
#   改法: repeat=true 的键, DOWN 持续满 REPEAT_INITIAL(0.5s) 后由本服务按
#   REPEAT_THROTTLE(0.12s) 主动补发 DOWN 直至 UP; 与 val=2 路径共用节流防双发。
#   ⚠ relay/atv 侧同类问题未改（atv 方向键连发同样受此影响, 待需要时再修）。
# v2.3（10-10 17:4x）: 长按（long）支持 —— mac/win 键表解禁 long 字段（用户需求「长按
#   还是没有选择」; v1 时代校验端强制置空）。语义对齐 relay v0.9:
#   · 有 long 的键: 按下不即时发; 按住满 hold_threshold(0.6s) 由 tick 触发 long 动作;
#   · 未满阈值松开 → 松开时发 single（成对 down+up）;
#   · 触发 long 后松开 → UP 发回 long 动作（配对纪律）; long 与 repeat 互斥（校验端保证）;
#   · handle() 返回改为列表（一次事件可发多条）。
#   主页 #102 生产绑定: single=APP:CYCLE（短按轮询）/ long=APP:PICK（长按开应用选择器）。
# v2.4（10-12 21:3x）: 文案同步 —— 修正注释/日志中「Windows 待部署 / IP 待定」等过时描述
#   （10-11 已完工接线: WIN_IP=WINDOWS_IP; win_receiver 按键 + 语音链实机验收; 键位与
#   mac 100% 对齐）。无行为变更。
# 职责: RC003 遥控器事件 → 按当前目标 UDP 转发（voice_target 文件, :8765 主页三按钮切换）
#   target=atv  → 本服务全部忽略（语音键交 relay_min: atv=一键开 YouTube; 普通键 relay 已处理）
#   target=mac  → macOS MACOS_IP
#     · 语音键(63): "VOICE down/up"      → :8788 voice_bridge（输入法语音上屏）
#     · 普通键:     "KEY <动作> DOWN/UP" → :8791 key_bridge（键盘注入; OK=回车/返回=Esc/方向=方向键）
#   target=win  → Windows WINDOWS_IP（10-11 完工接线; 接收端 win_receiver.py）
# 动作解析: keymap.json v2 的 targets[<目标>].keys[code].single（兼容 v1 旧结构, 视为 atv）
#   长按/双击: 长按已解禁（v2.3, mac/win 同款）; 双击暂不支持（网页校验端强制置空; 语音键不参与映射）
# 配对纪律: UP（含连发）永远发回 DOWN 时的目标与动作 —— 防"录音/按键悬挂"
#   （按住中切换目标不断: 松开仍回原目标收尾）
# 连发: val=2 且该键 repeat=true 时, 按 REPEAT_THROTTLE 节流补发 DOWN
#   （macOS 对合成键不做系统级自动 repeat, 由本侧补发驱动"按住连续移动"）
# 特点: 只读事件设备(不 grab), 与 relay_min.py / t1-evwatch 多读者共存;
#       按设备名动态发现(不绑 eventN 号), 断开自动重挂
# 运行: systemctl restart t1-voice-fwd
#   (手动: cd /root/remote-hub; nohup /usr/bin/python3 voice_fwd.py > /var/log.hdd/voice_fwd.log 2>&1 < /dev/null &)
import glob
import json
import os
import select
import socket
import struct
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_FILE = os.path.join(HERE, "voice_target")
CFG_PATH = os.path.join(HERE, "keymap.json")
CFG_DEFAULT_PATH = os.path.join(HERE, "keymap.default.json")
MAC_IP = "MACOS_IP"      # macOS (en1)
MAC_PORT = 8788              # voice_bridge 监听端口（语音）
MAC_KEY_PORT = 8791          # key_bridge 监听端口（普通键）
WIN_IP = "WINDOWS_IP"      # Windows（10-11 完工接线；接收端 win_receiver.py）
WIN_PORT = 8788
WIN_KEY_PORT = 8791
VOICE_KEY = 63               # RC003 语音键 = KEY_F5
REPEAT_THROTTLE = 0.12       # 连发节流（与 relay 一致）
REPEAT_INITIAL = 0.5         # v2.1: 按住多久后开始自建连发（设备无 EV_REP）
DEV_MATCH = ("hog", "小米", "RC003", "MI RC")  # "MI RC"=10-11 bluetoothd 重启后 HOG 节点新名


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


def read_target():
    """读取当前目标（atv/mac/win）；文件缺失/损坏回退 mac（现状）"""
    try:
        with open(TARGET_FILE) as f:
            t = f.read().strip()
        return t if t in ("atv", "mac", "win") else "mac"
    except Exception:  # noqa: BLE001
        return "mac"


def _normalize_cfg(cfg):
    """v2 (targets) 直用；v1 (单份 keys) 视为 atv"""
    if isinstance(cfg.get("targets"), dict):
        return cfg
    if isinstance(cfg.get("keys"), dict):
        return {"version": 2, "targets": {"atv": {"keys": cfg["keys"]},
                                          "mac": {"keys": {}}, "win": {"keys": {}}}}
    raise ValueError("keys/targets 缺失")


def load_cfg():
    """keymap.json -> keymap.default.json -> 空键表（三级保护）"""
    for p in (CFG_PATH, CFG_DEFAULT_PATH):
        try:
            with open(p) as f:
                return _normalize_cfg(json.load(f))
        except Exception as e:  # noqa: BLE001
            log(f"配置加载失败 {p}: {e!r}")
    log("使用空键表兜底")
    return {"version": 2, "targets": {"atv": {"keys": {}}, "mac": {"keys": {}}, "win": {"keys": {}}}}


class KeyForwarder:
    """mac/win 目标普通键转发决策（纯逻辑, 便于离线测试; 实际发送由调用方负责）"""

    def __init__(self):
        self.cfg = {"targets": {}}
        self._cfg_mtime = None
        self.down = {}         # code -> (target, action)  配对记录
        self.down_at = {}      # code -> monotonic DOWN 时刻（v2.1 自建连发首延迟）
        self.last_repeat = {}  # code -> monotonic 连发节流
        self.pending_long = {} # code -> (target, long_action)  等待阈值的长按（v2.3）
        self.long_fired = set()  # 已触发长按的 code（v2.3）

    def set_cfg(self, cfg):
        self.cfg = cfg
        self._cfg_mtime = self._stat_mtime()

    def _stat_mtime(self):
        try:
            return os.stat(CFG_PATH).st_mtime
        except Exception:  # noqa: BLE001
            return None

    def maybe_reload(self):
        m = self._stat_mtime()
        if m != self._cfg_mtime:
            self.set_cfg(load_cfg())
            log("keymap.json 变更 -> 键位配置已热重载")

    def keys_for(self, target):
        return self.cfg.get("targets", {}).get(target, {}).get("keys", {})

    def handle(self, code, val, target, now=None):
        """非语音键事件决策。返回 [(tgt, action, phase)] 列表（可能为空; v2.3: 短按松开
        未达长按阈值时会发成对 down+up 两条）。"""
        now = now if now is not None else time.monotonic()
        if val == 1:
            if target not in ("mac", "win"):
                return []
            ck = self.keys_for(target).get(str(code)) or {}
            action = ck.get("single")
            lng = ck.get("long")
            if not action and not lng:
                return []
            self.down[code] = (target, action or lng)
            self.down_at[code] = now
            self.last_repeat[code] = now
            if lng:
                # v2.3: 有长按 → 先不发; 等 tick 满阈值触发 long / 松开时补发 single
                self.pending_long[code] = (target, lng)
                return []
            return [(target, action, "down")]
        if val == 2:
            rec = self.down.get(code)
            if not rec:
                return []
            tgt, action = rec
            ck = self.keys_for(tgt).get(str(code)) or {}
            if not ck.get("repeat"):
                return []
            if now - self.last_repeat.get(code, 0.0) < REPEAT_THROTTLE:
                return []
            self.last_repeat[code] = now
            return [(tgt, action, "down")]
        if val == 0:
            rec = self.down.pop(code, None)
            self.down_at.pop(code, None)
            pend = self.pending_long.pop(code, None)
            fired = code in self.long_fired
            self.long_fired.discard(code)
            if not rec:
                return []
            tgt, action = rec
            if fired:
                # 长按已触发 → 只收尾 UP（配对纪律: 发回 long 动作; tick 已把 down 更新为 long）
                return [(tgt, action, "up")]
            if pend:
                # 短按（未达阈值松开）→ 发 single 成对（v2.3, 对齐 relay「短按在松开时发」）
                single = self.keys_for(tgt).get(str(code), {}).get("single")
                if not single:
                    return []
                return [(tgt, single, "down"), (tgt, single, "up")]
            return [(tgt, action, "up")]
        return []

    def reset(self):
        """设备重挂等场景清空按住状态（v2.1: 防幽灵连发; v2.3: 含长按状态）"""
        self.down.clear()
        self.down_at.clear()
        self.last_repeat.clear()
        self.pending_long.clear()
        self.long_fired.clear()

    def hold_threshold(self):
        """长按阈值秒数（v2.3; 与 relay 共用配置键 hold_threshold）"""
        try:
            return float(self.cfg.get("hold_threshold", 0.6))
        except Exception:  # noqa: BLE001
            return 0.6

    def tick(self, now=None):
        """周期检查: ①v2.3 长按触发（pending_long 满阈值 → long, 每键一次）;
        ②v2.1 自建连发（repeat 键补发 DOWN）。
        返回 [("long"|"repeat", tgt, action, code)]。
        连发与 val=2 路径共用 last_repeat 节流（设备若产生 val=2 也不会双发）。"""
        now = now if now is not None else time.monotonic()
        out = []
        # ① 长按判定（触发后从 pending 移除; down 切换为 long 动作供 UP 配对）
        for code, (tgt, lng) in list(self.pending_long.items()):
            if now - self.down_at.get(code, 0.0) < self.hold_threshold():
                continue
            self.pending_long.pop(code, None)
            self.long_fired.add(code)
            self.down[code] = (tgt, lng)
            out.append(("long", tgt, lng, code))
        # ② 自建连发
        for code, (tgt, action) in list(self.down.items()):
            if code in self.long_fired:
                continue                    # 与 long 互斥（双保险）
            if now - self.down_at.get(code, 0.0) < REPEAT_INITIAL:
                continue
            ck = self.keys_for(tgt).get(str(code)) or {}
            if not ck.get("repeat"):
                continue
            if now - self.last_repeat.get(code, 0.0) < REPEAT_THROTTLE:
                continue
            self.last_repeat[code] = now
            out.append(("repeat", tgt, action, code))
        return out


def send_voice(sock, is_down, target):
    """按目标发送 VOICE up/down；返回是否实际发出"""
    msg = b"VOICE down" if is_down else b"VOICE up"
    if target == "mac":
        sock.sendto(msg, (MAC_IP, MAC_PORT))
        return True
    if target == "win":
        if WIN_IP:
            sock.sendto(msg, (WIN_IP, WIN_PORT))
            return True
        log("win 目标未配置（WIN_IP 为空），丢弃")
        return False
    # atv: 不转发（relay 处理语音键 → 开 YouTube）
    return False


def send_key(sock, target, action, phase):
    """按目标发送 KEY <动作> DOWN/UP；返回是否实际发出"""
    msg = f"KEY {action} {'DOWN' if phase == 'down' else 'UP'}".encode()
    if target == "mac":
        sock.sendto(msg, (MAC_IP, MAC_KEY_PORT))
        return True
    if target == "win":
        if WIN_IP:
            sock.sendto(msg, (WIN_IP, WIN_KEY_PORT))
            return True
        return False
    return False


def find_dev():
    for ev in sorted(glob.glob("/dev/input/event*")):
        try:
            with open(f"/sys/class/input/{os.path.basename(ev)}/device/name") as f:
                name = f.read().strip()
            low = name.lower()
            if any(m.lower() in low for m in DEV_MATCH):
                return ev, name
        except Exception:  # noqa: BLE001
            continue
    return None, None


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    kf = KeyForwarder()
    kf.set_cfg(load_cfg())
    log(f"voice_fwd v2.4 启动: target={read_target()} "
        f"(mac={MAC_IP}:{MAC_PORT}/{MAC_KEY_PORT}, win={WIN_IP}) key={VOICE_KEY}")
    fd = None
    dev = None
    last_down_target = None   # 语音键 down 时目标；up 必须发回同一目标
    win_warn_t = [0.0]        # win 未配置提示节流
    dev_check_t = [0.0]       # v2.1: 设备节点存在性低频检查（原由 2s select 超时承担）

    while True:
        if fd is None:
            dev, name = find_dev()
            if dev is None:
                log("等待遥控器设备 ...")
                time.sleep(2)
                continue
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            kf.reset()   # v2.1: 重挂后清空按住状态, 防幽灵连发
            log(f"已挂载 {dev} [{name}]")
        try:
            # v2.1/v2.3: 每轮先做长按触发 + 自建连发补发（select 超时 0.05s, 保精度）
            for kind_r, tgt_r, action_r, code_r in kf.tick():
                if send_key(sock, tgt_r, action_r, "down"):
                    log(f"KEY {code_r} {kind_r} -> {tgt_r} {action_r}")
            r, _, _ = select.select([fd], [], [], 0.05)
            if not r:
                # 周期检查设备节点是否还在（低频 2s; 蓝牙断开会话时节点可能消失）
                now = time.monotonic()
                if now - dev_check_t[0] > 2.0:
                    dev_check_t[0] = now
                    if not os.path.exists(dev):
                        raise OSError("device node gone")
                continue
            # 读到 EAGAIN 为止（一次可能堆积多条事件）
            while True:
                try:
                    data = os.read(fd, 24)
                except BlockingIOError:
                    break
                if len(data) < 24:
                    raise OSError("short read")
                _s, _us, etype, code, val = struct.unpack("llHHi", data[:24])
                if etype != 1:
                    continue
                now = time.monotonic()

                # ---- 语音键（既有逻辑不变）----
                if code == VOICE_KEY:
                    if val == 1:
                        t = read_target()
                        last_down_target = t
                        if send_voice(sock, True, t):
                            log(f"KEY63 down -> {t}")
                        elif t == "atv":
                            log("KEY63 down 忽略 (atv 模式, relay 侧开 YouTube)")
                    elif val == 0:
                        t = last_down_target if last_down_target else read_target()
                        last_down_target = None
                        if send_voice(sock, False, t):
                            log(f"KEY63 up   -> {t}")
                    # val == 2: 长按自动重复, 忽略
                    continue

                # ---- 普通键: 仅 mac/win 目标（atv 交 relay）----
                kf.maybe_reload()
                for tgt, action, phase in kf.handle(code, val, read_target(), now):
                    if send_key(sock, tgt, action, phase):
                        log(f"KEY {code} {phase} -> {tgt} {action}")
                    elif tgt == "win" and now - win_warn_t[0] > 5.0:
                        win_warn_t[0] = now
                        log(f"KEY {code} {phase}: win 目标未配置，丢弃")
        except OSError as e:  # noqa: BLE001
            log(f"设备失效: {e!r} -> 重挂")
            try:
                os.close(fd)
            except Exception:  # noqa: BLE001
                pass
            fd = None
            dev = None
            time.sleep(1)
        except Exception as e:  # noqa: BLE001
            log(f"ERR: {e!r}")
            time.sleep(1)


if __name__ == "__main__":
    main()
