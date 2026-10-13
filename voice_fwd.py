#!/usr/bin/env python3
# voice_fwd.py — T1 端「遥控器键 · 非ATV目标转发器」 v2.9 (2026-10-14)
#
# v2.9（10-14 presence 接线 —— 投递地址去硬编码 + 体面断开; 承 10-13 拍板的心跳注册制）:
#   接入 presence 心跳注册制（服务端 presence.py + 客户端 presence_beat.py）:
#   · 投递地址动态化 —— 目标 IP 优先取心跳学习地址（T1: state/presence.json）,
#     MAC_IP/WIN_IP 常量降级为 fallback（DHCP 换址自动跟上, 无需改代码）;
#   · 投递闸门 —— 目标「明确离线」（6s=3 拍无心跳）→ 跳过投递并留一行日志,
#     杜绝"假已发送"; 恢复心跳后自动继续（离线/恢复各一条边沿日志）;
#   · 降级安全 —— presence 守护未部署 / 快照过期 / 文件损坏 → 状态 unknown,
#     维持旧行为（照旧投递, 地址回退常量）; 读端永不阻塞;
#   · atv 目标不受影响（T1 本机 relay 处理, 不经本模块投递）。
#
# v2.8（10-14 鼠标模式内 #41 放行, 用户反馈「鼠标模式下按焦点聚焦键不灵、不好使」）:
#   模式内短按 #41 不再吸收（v2.6 曾改为弹「模式仍开着」提示——反而造成「按了没反应」
#   的观感）——直接放行走 KeyForwarder: 短按=FOCUS_INPUT 转发到实时目标（聚焦输入框）,
#   长按=MOUSE:TOGGLE 关模式, 与键盘模式行为完全一致（用户心智: #41 任何时候都该聚焦）。
#   同时修正: 模式内喂 kf 的目标由固定 "mac" 改为实时 target（放行转发必须用真实目标;
#   键表 mac/win 的 #41 同构, 自定义不同则按当前目标语义生效）。
#   配套接收端: Mac key_bridge v1.15（不变）+ remotehub_focus.lua v1.5 /
#   win_receiver v1.10（不变）+ win_actions v1.15 —— 两端 NOEDIT 时新增「底部中央
#   兜底点击」(0.5, 0.92)（治微信等无 AX/无 UIA 内容层应用「聚焦不了」, 点击后恢复鼠标位置）。
# v2.7（10-13 电源键连击切换设备, 用户需求「免开网页切目标」）:
#   电源键 #116 连击 = 切换遥控目标（1 击=ATV / 2 击=macOS / 3 击=Windows）。
#   启用条件（每事件热读）: 当前目标 keymap #116.single == "TARGET:SWITCH"——
#   两份 keymap 默认均已为该值; 改回具体动作者立即退回普通键语义, 无需改代码。
#   实现 = TargetSwitcher 状态机（纯逻辑, 离线可测）:
#   · 连击窗口 0.5s（自最后一次 DOWN 起算）; 第 3 击按下立即提交, 其余期满且已松开提交;
#   · 长按 >= hold_threshold 中止计数, 走 keymap #116.long（现行=APP:CLOSE）—— 语义不变;
#   · 提交后 0.5s 吞键期（连敲续期 = 整串吞完）—— 防手抖多敲一记把目标又切走;
#   · 提交 = 原子写 voice_target + 向接收端发 HUD "TARGET:SWITCH:<ATV|MAC|WIN>"
#     （切到 atv 发旧目标端 / 切到 mac·win 发新目标端）;
#   · 切到 atv 时鼠标模式强制退出（atv 无鼠标通道）; 目标=atv 时 #116 交 relay
#     （relay v0.11 对等实现: 1 击=电视电源 / 2 击=mac / 3 击=win）。
#   接收端配套: Mac key_bridge v1.15 + remotehub_focus.lua v1.4（switchHud）/
#   win_receiver v1.10 + win_actions v1.14（Tk 浮层）。
# v2.6（10-13 实测反馈修复轮, 承 v2.5 鼠标模式 —— 用户首测五问之三）:
#   ① 模式切换提示: 开关模式 / 模式内单按 #41 时, 向当前目标发 "MOUSE:MODE:ON|OFF"
#      （接收端弹 HUD —— 治"按了不知道生效没有"）;
#   ② 模式内放行键: 电源 116 / 主页 102 透传正常键路径（治"没法跳走打开应用"）;
#   ③ handle() 对放行键返回 None -> 调用方转 KeyForwarder（含长按机制, 行为与模式外一致）;
#   ④ 配套接收端: Mac key_bridge v1.14 + remotehub_focus.lua v1.3（HUD 浮层）/
#      win_receiver v1.8 + win_actions v1.12（HUD + 滑行速度清零修复）。
# v2.5（10-13 鼠标模式, 用户需求「遥控器模拟鼠标」）: 新增鼠标模式状态机
#   —— 长按 #41 直播 开/关（keymap #41 long=MOUSE:TOGGLE, 经 KeyForwarder 长按机制）;
#   模式内: 方向=滑行移动(MOUSE:MOVE:*) / OK 短=左键 长=右键(MOUSE:LCLICK/RCLICK) /
#   音量±=连续滚动(MOUSE:SCROLL:*) / 返回=退出(MOUSE:OFF, 本地消化)。
#   转发动作发给「DOWN 时快照的目标」; MOVE/SCROLL 按住期间按 0.4s 补发保活
#   （接收端 1.2s 无刷新看门狗自停 —— 保活即掉线安全带）。MOUSE:TOGGLE/OFF 为本地动作,
#   不转发; 模式内短按 #41（FOCUS_INPUT）吸收。接收端: Mac key_bridge v1.13 /
#   win_receiver v1.7 + win_actions v1.11（对等实现, 滑行参数两端一致）。
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

try:  # v2.9: presence 心跳读端（降级: 无 presence.py -> None, 全程回退常量投递）
    from presence import StateView as _StateView
except Exception:  # noqa: BLE001
    _StateView = None

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_FILE = os.path.join(HERE, "voice_target")
CFG_PATH = os.path.join(HERE, "keymap.json")
CFG_DEFAULT_PATH = os.path.join(HERE, "keymap.default.json")
MAC_IP = "MACOS_IP"      # macOS (en1) —— v2.9: fallback（优先用心跳学习地址）
MAC_PORT = 8788              # voice_bridge 监听端口（语音）
MAC_KEY_PORT = 8791          # key_bridge 监听端口（普通键）
WIN_IP = "WINDOWS_IP"      # Windows（10-11 完工接线；接收端 win_receiver.py）—— v2.9: fallback
WIN_PORT = 8788
WIN_KEY_PORT = 8791
VOICE_KEY = 63               # RC003 语音键 = KEY_F5
REPEAT_THROTTLE = 0.12       # 连发节流（与 relay 一致）
REPEAT_INITIAL = 0.5         # v2.1: 按住多久后开始自建连发（设备无 EV_REP）
DEV_MATCH = ("hog", "小米", "RC003", "MI RC")  # "MI RC"=10-11 bluetoothd 重启后 HOG 节点新名

# ---- v2.5: 鼠标模式（长按 #41 开/关; 模式内映射见 MouseMode） ----
MOUSE_TOGGLE_CODE = 41       # 长按直播 = 开/关鼠标模式（keymap #41 long=MOUSE:TOGGLE）
MOUSE_MOVE_CODES = {103: "UP", 108: "DOWN", 105: "LEFT", 106: "RIGHT"}   # dpad -> 滑行
MOUSE_SCROLL_CODES = {115: "UP", 114: "DOWN"}                            # 音量± -> 滚动
MOUSE_OK_CODE = 28           # 短按=左键（松开发）/ 长按=右键（阈值触发）
MOUSE_BACK_CODE = 158        # 返回 = 退出模式（本地消化）
MOUSE_KEEPALIVE = 0.4        # 保活补发节奏（< 接收端 1.2s 看门狗窗口, 留 3 倍丢包容忍）
# v2.6: 模式内放行键（透传 KeyForwarder 正常路径 —— 用户实测要求「能跳走打开应用」）
MOUSE_PASSTHROUGH_CODES = {116, 102}   # 116=电源（v2.7: single=TARGET:SWITCH 时由连击层
                                       #   先接管, 此处仅在网关撤下后放行）
                                       # 102=主页（短 APP:CYCLE / 长 APP:PICK）

# ---- v2.7: 电源键连击切换设备（keymap #116.single == TARGET:SWITCH 时启用） ----
POWER_KEY_CODE = 116
TARGET_SWITCH_ACTION = "TARGET:SWITCH"   # 网关值（网页下拉「★ 电源（连击切设备）」）
TARGET_SWITCH_WINDOW = 0.5               # 连击窗口（自最后一次 DOWN 起算; 期满提交）
TARGET_SWITCH_MAX = 3                    # 连击上限（第 3 击立即提交; 更多敲击吞掉）
TARGET_ORDER = ("atv", "mac", "win")     # 计数 -> 目标（1 击=atv / 2 击=mac / 3 击=win）


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


# ---- v2.9: presence 投递闸门（地址动态化 + 离线跳过） ----
_pv = _StateView() if _StateView else None   # 读端热缓存（0.5s 节流 + mtime 缓存, 热路径≈一次 stat）
_pv_offline = set()                          # 已报告过离线的 role（边沿日志: 离线/恢复各一条）
_pv_noaddr_t = {}                            # 「无可用地址」日志节流（60s）


def _send_to(sock, msg, role, fallback_ip, port):
    """v2.9 统一投递闸门 —— 返回是否实际发出。

    · 目标明确离线（3 拍无心跳）→ 跳过 + 边沿日志（首次报告/恢复各一条）;
    · 在线 / unknown（守护未就绪）→ 心跳学习 IP 优先, 回退常量（unknown=降级旧行为）;
    · 无常量且无心跳地址 → 节流日志后丢弃。"""
    ip = fallback_ip
    if _pv is not None:
        if _pv.device_state(role) == "offline":
            if role not in _pv_offline:
                _pv_offline.add(role)
                log(f"presence: {role} 离线（心跳超时）, 暂停投递")
            return False
        ip = _pv.ip_of(role) or fallback_ip
        if role in _pv_offline:
            _pv_offline.discard(role)
            log(f"presence: {role} 已恢复心跳, 恢复投递")
    if not ip:
        now = time.time()
        if now - _pv_noaddr_t.get(role, 0.0) > 60.0:
            _pv_noaddr_t[role] = now
            log(f"presence: {role} 无可用地址（常量未配置且无心跳）, 丢弃")
        return False
    sock.sendto(msg, (ip, port))
    return True


def read_target():
    """读取当前目标（atv/mac/win）；文件缺失/损坏回退 mac（现状）"""
    try:
        with open(TARGET_FILE) as f:
            t = f.read().strip()
        return t if t in ("atv", "mac", "win") else "mac"
    except Exception:  # noqa: BLE001
        return "mac"


def write_target(t):
    """v2.7: 原子写 voice_target（tmp + os.replace, 与 t1_webui 同构）——
    电源连击切换提交用；读端 relay/voice_fwd 均为按键时热读, 无需重启。"""
    tmp = TARGET_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(t + "\n")
    os.replace(tmp, TARGET_FILE)


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


class MouseMode:
    """v2.5 鼠标模式状态机（纯逻辑, 离线可测; 实际发送由调用方负责）。

    开关: 长按 #41（keymap long=MOUSE:TOGGLE）—— 模式开/关两种状态下均由
    KeyForwarder 的长按机制产出该动作（模式开时 main 把 #41 事件照旧喂 kf,
    目标固定用 mac 键表——两表 #41 同构）, main 消化切换 + kf.reset()。
    模式内映射（DOWN 时快照目标; UP 回原目标, 配对纪律）:
      方向 103/105/106/108 → MOUSE:MOVE:UP/DOWN/LEFT/RIGHT（按住滑行; 补发保活）
      音量+ 115 / 音量- 114 → MOUSE:SCROLL:UP/DOWN（按住连续滚动）
      OK 28  短按（松开时发）→ MOUSE:LCLICK; 长按满阈值 → MOUSE:RCLICK（每按住一次一发）
      返回 158 → ("", "MOUSE:OFF", "down") 本地动作 —— 调用方消化退出, 不转发
      电源 116 / 主页 102 → 放行（返回 None, 调用方转 KeyForwarder 正常处理 —— v2.6）
      其余键 → 忽略（#41 不经过本类, 由 main 路由给 KeyForwarder）
    """

    def __init__(self):
        self.on = False
        self.moves = {}       # code -> (target, action)  按住中的方向/音量键
        self.keep_at = {}     # code -> 上次发送 monotonic（保活节流）
        self.ok_down = False
        self.ok_at = 0.0
        self.ok_fired = False
        self.ok_target = "mac"
        self.ok_threshold = 0.6   # 与 KeyForwarder.hold_threshold 同步（main 每轮刷新）

    def toggle(self):
        self.on = not self.on
        self.reset()
        return self.on

    def reset(self):
        """清空按住/长按状态（模式切换、设备重挂时调用——防幽灵保发）。"""
        self.moves.clear()
        self.keep_at.clear()
        self.ok_down = False
        self.ok_fired = False

    def handle(self, code, val, target, now=None):
        """模式开时非 #41 键映射。返回 [(tgt, action, phase)] 列表（可能为空）。"""
        now = now if now is not None else time.monotonic()
        if not self.on:
            return []
        if code in MOUSE_PASSTHROUGH_CODES:
            return None      # v2.6: 放行（调用方转 KeyForwarder 正常路径, 含长按）
        if val == 1:
            if code in MOUSE_MOVE_CODES:
                act = "MOUSE:MOVE:" + MOUSE_MOVE_CODES[code]
                self.moves[code] = (target, act)
                self.keep_at[code] = now
                return [(target, act, "down")]
            if code in MOUSE_SCROLL_CODES:
                act = "MOUSE:SCROLL:" + MOUSE_SCROLL_CODES[code]
                self.moves[code] = (target, act)
                self.keep_at[code] = now
                return [(target, act, "down")]
            if code == MOUSE_OK_CODE:
                self.ok_down = True
                self.ok_at = now
                self.ok_fired = False
                self.ok_target = target
                return []
            if code == MOUSE_BACK_CODE:
                return [("", "MOUSE:OFF", "down")]
            return []
        if val == 0:
            if code == MOUSE_OK_CODE:
                fired = self.ok_fired
                self.ok_down = False
                self.ok_fired = False
                if fired:
                    return []     # 长按已发 RCLICK（松开仅收尾）
                return [(self.ok_target, "MOUSE:LCLICK", "down")]   # 短按=左键（松开发）
            rec = self.moves.pop(code, None)
            self.keep_at.pop(code, None)
            if not rec:
                return []
            tgt, act = rec
            return [(tgt, act, "up")]
        return []   # val==2: 设备空连发不用; 保活由 tick 负责

    def tick(self, now=None):
        """① OK 长按满阈值 → RCLICK（每按住一次最多一发）;
        ② 按住键 0.4s 保活补发 DOWN（接收端滑行/滚动刷新, 防 1.2s 看门狗自停）。
        返回 [(tgt, action, phase)]。"""
        now = now if now is not None else time.monotonic()
        if not self.on:
            return []
        out = []
        if self.ok_down and not self.ok_fired and now - self.ok_at >= self.ok_threshold:
            self.ok_fired = True
            out.append((self.ok_target, "MOUSE:RCLICK", "down"))
        for code, (tgt, act) in list(self.moves.items()):
            if now - self.keep_at.get(code, 0.0) < MOUSE_KEEPALIVE:
                continue
            self.keep_at[code] = now
            out.append((tgt, act, "down"))
        return out


class TargetSwitcher:
    """v2.7 电源键（#116）连击切换设备（纯逻辑, 离线可测; 写文件/发 HUD 由调用方负责）。

    启用条件（调用方判定, 每事件热读）: 当前目标 (mac/win) 的 keymap
    targets.<tgt>.keys["116"].single == "TARGET:SWITCH"。启用期间 #116 事件由本类
    全权消化（不再进 MouseMode/KeyForwarder; 目标=atv 不用本类 —— relay 侧对等实现）。

    判定规则:
      · DOWN 计数 +1（上限 3）; 窗口 TARGET_SWITCH_WINDOW 自最后一次 DOWN 起算;
      · 计数达 3 -> 第 3 次 DOWN 立即提交（免等窗口）;
      · 其余情况: 窗口期满且当前未按住 -> 提交（tick 或松开事件触发）;
      · 长按（当前按下时长 >= hold_threshold）-> 中止计数, 走 long 路径（调用方查
        keymap #116.long 发送; 现行=APP:CLOSE 关闭当前应用, 语义不变）;
      · 提交后 0.5s 吞键期: 期内 #116 事件全部吞掉（防手抖多敲一记把目标又切走;
        连敲续期 = 整串吞完为止）。

    事件元组（输出）: ("commit", count) —— 调用方按 TARGET_ORDER[count-1] 切目标;
                      ("long", target)  —— 调用方查 keymap 发 long DOWN（用 DOWN 时目标）;
                      ("long_end", None) —— 调用方对已发 long 动作补 UP 收尾。
    """

    def __init__(self, window=TARGET_SWITCH_WINDOW):
        self.window = window
        self.count = 0
        self.deadline = 0.0
        self.holding = False
        self.down_at = 0.0
        self.down_target = None
        self.long_fired = False
        self.cooldown_at = None

    def reset(self):
        """清空会话（设备重挂 / 网关撤下等场景 —— 防幽灵提交）。"""
        self.count = 0
        self.deadline = 0.0
        self.holding = False
        self.down_at = 0.0
        self.down_target = None
        self.long_fired = False
        self.cooldown_at = None

    def _swallow(self, now):
        """提交后吞键期检查（仅事件侧调用, 连敲续期; 非吞键返回 False）。"""
        if self.cooldown_at is None:
            return False
        if now - self.cooldown_at <= self.window:
            self.cooldown_at = now
            return True
        self.cooldown_at = None
        return False

    def _commit(self, now):
        n = max(1, self.count)
        self.count = 0
        self.deadline = 0.0
        self.holding = False
        self.long_fired = False
        self.cooldown_at = now
        return [("commit", n)]

    def handle(self, code, val, now, target=None):
        """#116 DOWN/UP 事件 -> 事件列表。窗口期满的提交在 tick 完成（50ms 精度）。"""
        if code != POWER_KEY_CODE:
            return []
        if self._swallow(now):
            return []
        if val == 1:
            self.count = min(self.count + 1, TARGET_SWITCH_MAX)
            self.down_at = now
            self.holding = True
            self.down_target = target
            self.deadline = now + self.window
            if self.count >= TARGET_SWITCH_MAX:
                return self._commit(now)     # 第 3 击: 立即提交
            return []
        if val == 0:
            if self.long_fired:              # 长按已发 -> UP 收尾
                self.long_fired = False
                self.holding = False
                return [("long_end", None)]
            self.holding = False
            if self.count and now >= self.deadline:
                return self._commit(now)     # 按住期间窗口已过 -> 松开即成
            return []
        return []                            # val==2 忽略（设备无 EV_REP）

    def tick(self, now, hold_threshold):
        """周期检查: ①长按触发（中止计数）; ②窗口期满提交。"""
        if self.cooldown_at is not None and now - self.cooldown_at <= self.window:
            return []                        # 吞键期（tick 不续期）
        if self.holding:
            if not self.long_fired and now - self.down_at >= hold_threshold:
                self.long_fired = True
                self.count = 0
                self.deadline = 0.0
                return [("long", self.down_target)]
            return []
        if self.count and now >= self.deadline:
            return self._commit(now)
        return []


def send_voice(sock, is_down, target):
    """按目标发送 VOICE up/down；返回是否实际发出
    （v2.9: 经 presence 闸门 —— 离线跳过 / 地址心跳优先回退常量）"""
    msg = b"VOICE down" if is_down else b"VOICE up"
    if target == "mac":
        return _send_to(sock, msg, "mac", MAC_IP, MAC_PORT)
    if target == "win":
        return _send_to(sock, msg, "win", WIN_IP, WIN_PORT)
    # atv: 不转发（relay 处理语音键 → 开 YouTube）
    return False


def send_key(sock, target, action, phase):
    """按目标发送 KEY <动作> DOWN/UP；返回是否实际发出（v2.9: 同 send_voice）"""
    msg = f"KEY {action} {'DOWN' if phase == 'down' else 'UP'}".encode()
    if target == "mac":
        return _send_to(sock, msg, "mac", MAC_IP, MAC_KEY_PORT)
    if target == "win":
        return _send_to(sock, msg, "win", WIN_IP, WIN_KEY_PORT)
    return False


def send_mode_hint(sock, on, target):
    """v2.6: 鼠标模式切换提示 —— 向当前目标发 MOUSE:MODE:ON|OFF。

    接收端弹 HUD 浮层（治用户反馈「按了不知道生效没有」）。
    v2.8: 模式内单按 #41 已改为放行聚焦（不再复用本提示）。
    仅 mac/win 有 HUD 接收端（key_bridge / win_receiver+win_actions）；atv 无此通道，不发。
    返回是否实际发出。"""
    if target not in ("mac", "win"):
        return False
    return send_key(sock, target, "MOUSE:MODE:" + ("ON" if on else "OFF"), "down")


def send_target_hint(sock, new_target, old_target):
    """v2.7: 设备切换 HUD —— 向接收端发 "KEY TARGET:SWITCH:<ATV|MAC|WIN> DOWN"。

    规则: 切到 atv -> 发旧目标端（mac/win 一端必见提示）; 切到 mac/win -> 发新目标端。
    接收端弹浮层（Mac remotehub_focus.lua v1.4 switchHud / Win win_actions v1.14 Tk）。
    atv 无接收端, 不发。返回是否实际发出。"""
    tgt = old_target if new_target == "atv" else new_target
    if tgt not in ("mac", "win"):
        return False
    return send_key(sock, tgt, "TARGET:SWITCH:" + new_target.upper(), "down")


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
    mode = MouseMode()                                   # v2.5: 鼠标模式状态机
    sw = TargetSwitcher()                                # v2.7: 电源键连击切换
    sw_long = [None, None]                               # [tgt, action] 已发 #116 long（等 UP 配对）

    def apply_switch_events(events):
        """v2.7: TargetSwitcher 事件落地 —— 切目标原子写文件 + HUD; long 转发与收尾。"""
        for kind, arg in events:
            if kind == "commit":
                old_t, new_t = read_target(), TARGET_ORDER[arg - 1]
                write_target(new_t)
                if new_t == "atv" and mode.on:           # atv 无鼠标通道 -> 强制退出
                    mode.toggle()
                    send_mode_hint(sock, False, old_t)
                send_target_hint(sock, new_t, old_t)
                log(f"电源连击 x{arg}: 目标 {old_t} -> {new_t}（HUD 已发）")
            elif kind == "long":
                act = (kf.keys_for(arg).get(str(POWER_KEY_CODE)) or {}).get("long")
                if act:
                    send_key(sock, arg, act, "down")
                    sw_long[0], sw_long[1] = arg, act
                    log(f"电源长按 -> {arg} {act}（DOWN）")
            elif kind == "long_end":
                if sw_long[1]:
                    send_key(sock, sw_long[0], sw_long[1], "up")
                    log(f"电源长按收尾 -> {sw_long[0]} {sw_long[1]}（UP）")
                    sw_long[0] = sw_long[1] = None

    log(f"voice_fwd v2.9 启动: target={read_target()} "
        f"(mac={MAC_IP}:{MAC_PORT}/{MAC_KEY_PORT}, win={WIN_IP}) key={VOICE_KEY} "
        f"| presence={'on' if _pv else 'off'}(闸门: 离线跳过 / 心跳地址优先) "
        f"| 鼠标模式=关 (长按 #41 开/关; 模式内短按 #41=聚焦输入框) | 电源连击=1击ATV/2击Mac/3击Win (窗0.5s)")
    fd = None
    dev = None
    last_down_target = None   # 语音键 down 时目标；up 必须发回同一目标
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
            sw.reset()   # v2.7: 连击会话同样清空（防幽灵提交）
            log(f"已挂载 {dev} [{name}]")
        try:
            # v2.1/v2.3: 每轮先做长按触发 + 自建连发补发（select 超时 0.05s, 保精度）
            for kind_r, tgt_r, action_r, code_r in kf.tick():
                if action_r == "MOUSE:TOGGLE":   # v2.5: 长按 #41 -> 开/关鼠标模式（本地消化）
                    on = mode.toggle()
                    kf.reset()
                    tgt_n = read_target()
                    send_mode_hint(sock, on, tgt_n)      # v2.6: HUD 提示（治"不知道生效没有"）
                    log(f"鼠标模式 {'开' if on else '关'} (长按直播, 目标={tgt_n})")
                    continue
                if send_key(sock, tgt_r, action_r, "down"):
                    log(f"KEY {code_r} {kind_r} -> {tgt_r} {action_r}")
            # v2.5: 鼠标模式 tick（OK 长按 -> 右键; 按住键保活补发）
            for tgt_m, action_m, phase_m in mode.tick():
                if send_key(sock, tgt_m, action_m, phase_m):
                    log(f"MOUSE {action_m} {phase_m} -> {tgt_m}")
            # v2.7: 电源连击 tick（长按触发 / 窗口期满提交）
            apply_switch_events(sw.tick(time.monotonic(), kf.hold_threshold()))
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
                mode.ok_threshold = kf.hold_threshold()   # v2.5: OK 长按阈值跟随配置
                target = read_target()

                # ---- v2.7: 电源键连击切换（先于鼠标模式/键转发; 目标=atv 时交 relay）----
                if code == POWER_KEY_CODE and target in ("mac", "win"):
                    gate = (kf.keys_for(target).get(str(POWER_KEY_CODE)) or {}).get("single")
                    if gate == TARGET_SWITCH_ACTION:
                        apply_switch_events(sw.handle(code, val, now, target))
                        continue      # 连击层全权消化（不进鼠标模式/键转发）
                    sw.reset()        # 网关撤下（keymap 改动）-> 清残留会话, 走普通路径

                if mode.on and code != MOUSE_TOGGLE_CODE:
                    outs = mode.handle(code, val, target, now)     # v2.5: 模式内映射
                    if outs is None:                               # v2.6: 放行键 -> 正常键路径
                        outs = kf.handle(code, val, target, now)   #   （电源/主页, 含长按语义）
                elif mode.on:
                    # v2.8: 模式内 #41 喂 kf（短按=FOCUS_INPUT 放行 / 长按=MOUSE:TOGGLE 关模式）;
                    # 用实时目标（旧版固定 "mac" 仅为长按检测——放行转发后必须用真实目标）
                    outs = kf.handle(code, val, target, now)
                else:
                    outs = kf.handle(code, val, target, now)
                for tgt, action, phase in outs:
                    if action == "MOUSE:TOGGLE":      # v2.5: 本地动作, 不转发
                        if phase == "down":
                            on = mode.toggle()
                            kf.reset()
                            send_mode_hint(sock, on, target)   # v2.6: HUD 提示
                            log(f"鼠标模式 {'开' if on else '关'} (长按直播, 目标={target})")
                        continue
                    if action == "MOUSE:OFF":         # v2.5: 返回键退出（本地）
                        on = mode.toggle()
                        kf.reset()
                        send_mode_hint(sock, on, target)       # v2.6: HUD 提示（此刻必为关）
                        log("鼠标模式 关 (返回键)")
                        continue
                    if send_key(sock, tgt, action, phase):
                        log(f"KEY {code} {phase} -> {tgt} {action}")
                    # （v2.9: 投递失败原因已由 presence 闸门明确日志 —— 离线=边沿一条 /
                    #   无地址=60s 节流一条; 原「win 未配置」兜底提示退役）
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
