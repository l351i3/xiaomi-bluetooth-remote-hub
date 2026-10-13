#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remotehub-win receiver v1.7 —— Windows 遥控接收端（Windows）
=========================================================
由 T1（T1_IP）的 voice_fwd 发包，本机接收并注入：

  :8788  "VOICE down" / "VOICE up"      -> 按住/松开 Ctrl+Win（微信输入法语音）
  :8791  "KEY <动作> DOWN/UP"           -> 注入对应键盘事件（SendInput）
  任意端口 "PING"                         -> 回 "PONG"（连通性自检）

键盘动作表（与 T1 侧 keymap 一致，勿改）：
  ENTER / ESC / TAB / SPACE / BACKSPACE / UP / DOWN / LEFT / RIGHT / PAGEUP / PAGEDOWN

扩展动作表（win_actions.py 实现, 对齐 Mac key_bridge / app_switch / remotehub_focus）:
  CLICK / FOCUS_INPUT / APP:CYCLE / APP:TOGGLE / APP:NEXT / APP:PICK / APP:<名称>
  / URL:<网址> / RUN:<命令>（v1.5）
  —— 仅 DOWN 触发; 收包线程快速防抖(CLICK/FOCUS/URL/RUN=0.6s, APP=0.35s)后交 action-worker

鼠标动作表（v1.7, win_actions.mouse_control —— 专用路由, 不走扩展 down-only 管道）:
  MOUSE:MOVE:UP|DOWN|LEFT|RIGHT（滑行; 按住语义: DOWN 启动/保活刷新, UP 停止）
  MOUSE:SCROLL:UP|DOWN（连续滚动, 同 hold 语义） / MOUSE:LCLICK | MOUSE:RCLICK（仅 DOWN）

v1.7 变更（2026-10-13，鼠标模式 —— 遥控器 dpad 模拟鼠标, 用户需求）：
  - handle_key 新增 MOUSE:* 前置分支 -> handle_mouse -> win_actions.mouse_control。
    MOVE/SCROLL 是 DOWN+UP 双向 hold 语义 —— 不能走 handle_ext（down-only 管道）, 故
    在 VK 查表/picker 路由之前独立分流; 不做防抖（保活包即刷新信号; 重复 DOWN 幂等）。
  - v1.6 键盘/语音/扩展动作/picker 路由 行为不变。

v1.6 变更（2026-10-11 深夜三期，防抖首击语义修复 —— 随 picker v2.3 配套分发）：
  - handle_ext 防抖 "从未记录" 哨兵修复: 原 `now - _ext_last.get(action, 0.0) < d` 把
    "从未触发（取默认 0.0）" 在 now < d 的单调时钟环境（从 0 起计时: 刚开机/虚拟化/
    部分解释器）误判为 "d 秒内刚触发" → 扩展动作首击被吞。改 None 哨兵显式判定。
  - 其余（语音链/键盘注入/picker 路由/麦克风切换）行为不变。

v1.5 变更（2026-10-11，扩展动作值大小写保真 —— URL: / RUN: 支持）：
  - handle_key 不再把整个动作串 upper 化：分派判定用大写副本, 传给扩展动作
    （handle_ext → win_actions）的是**原始串**——URL 路径/命令大小写敏感, 不可被改写。
  - 配合 win_actions v1.2（新增 URL:<网址> / RUN:<命令> 动作, 与 Mac key_bridge v1.11 同构）。
  - 键盘动作（VK 表）/ picker 路由 / 语音链 / 麦克风切换 行为全部不变。

v1.4 变更（2026-10-11，应用选择器按键直连路由）：
  - APP:PICK 选择器打开期间, UP/DOWN/ENTER/ESC/BACKSPACE 等按键不再走 SendInput 注入,
    而是直连投递给选择器（win_actions.picker_route → 选择器队列）。
    根因：本进程为计划任务/后台上下文, 其 tkinter 窗口无法保证获得系统键盘焦点,
    注入按键会落到别的窗口（用户实测「上下键无法切换」）；路由绕过焦点模型, 100% 可靠。
  - picker_route 不存在于旧版 win_actions 时自动回退旧行为（getattr 保护）。
  - v1.3 麦克风切换 / v1.2 扩展动作 / v1.1 语音链 全部保持不变。

v1.3 变更（2026-10-11，麦克风按需自动切换——方案 V）：
  - 新增 win_audio_switch.py：语音**按下** → 系统「默认录音设备」切到 CABLE Output
    （配合微信输入法麦克风=「默认设备」）；**松开后延迟 ~2s 自动切回**原设备。
  - 时序：down 先切设备（~200ms 预算, fail-open）再注入 Ctrl+Win；up 注入释放后调度切回；
    连按（会话未结束又按下）自动取消待切回 —— 调度与竞态防护在 win_audio_switch 内。
  - 启动自愈：上次进程若在「已切到 CABLE」状态下退出/崩溃, 本次启动自动切回原设备。
  - --selftest 输出追加音频设备段（虚拟设备匹配 + 当前默认, 打印感知原始值供人工确认）。
  - v1.2 扩展动作 / v1.1 语音链 / 键盘注入 / watchdog 行为全部保持不变。

v1.2 变更（2026-10-11，Mac 对等扩展动作）：
  - 新增 win_actions.py 扩展动作分发：未知动作不再直接丢弃, 转 win_actions.handle()。
  - 独立 action-worker 线程承载扩展动作（UIA 等数百 ms 级调用不阻塞收包线程）。
  - --selftest 自检模式（平台/UIA/窗口/焦点元素概况; 完整输出写 selftest.log）。
  - v1.1 的语音链/键盘注入/异步日志/watchdog 行为全部保持不变。

v1.1 变更（2026-10-11，修「按键延迟特别大」）：
  - 日志全面异步化：收包线程只入队（µs 级），独立日志线程消费写盘；
    日志文件句柄常开 + 行缓冲，不再每行 open/write/close
    （v1.0 每消息 2 次写盘且全在收包线程串行 = 延迟主因）。
  - 收包线程零 IO：recvfrom -> SendInput -> 入队；RX 明细行默认不记（--debug 打开）。
  - 控制台输出默认关闭（pythonw 后台静默）；--debug 时打印到控制台。
  - socket 接收缓冲加大（256KB），防突发积压。
  - 语音键兜底释放：VOICE down 后 60s 未收到 up 自动补释放（防 UDP 丢包卡住 Ctrl+Win）。
  - 日志队列满时丢弃日志、绝不阻塞链路（保链路优先）。

运行：python  win_receiver.py            （前台，静默）
      python  win_receiver.py --debug    （前台 + 控制台明细）
      python  win_receiver.py --selftest （自检: 平台/UIA/窗口/焦点元素/音频设备, 不启动服务）
      pythonw win_receiver.py            （后台无窗口；开机自启用这个）
日志：同目录 receiver.log（UTF-8，追加写，异步）
"""
import ctypes
import os
import queue
import socket
import sys
import threading
import time
from ctypes import wintypes as wt

try:
    import win_actions                      # v1.2: 扩展动作实现（同目录）
except Exception as _wa_err:                # 加载失败 -> 扩展动作降级为 unknown action
    win_actions = None
    _WA_ERR = str(_wa_err)
else:
    _WA_ERR = ""

try:
    import win_audio_switch                 # v1.3: 默认录音设备按需切换（方案 V, 同目录）
except Exception as _was_err:               # 加载失败 -> 麦克风切换降级为禁用（链路不受影响）
    win_audio_switch = None
    _WAS_ERR = str(_was_err)
else:
    _WAS_ERR = ""

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "receiver.log")
VOICE_PORT = 8788
KEY_PORT = 8791
DEBUG = "--debug" in sys.argv

VOICE_MAX_HOLD = 60.0   # 秒：down 后无 up 的兜底释放时限（v1.1）

# ---- 语音触发按键：微信输入法"按住 Ctrl+Win"；如实际快捷键不同，改这一行 ----
VOICE_MODS = [0x11, 0x5B]   # 0x11 = Ctrl, 0x5B = 左 Win

VK = {
    "ENTER": 0x0D, "ESC": 0x1B, "TAB": 0x09, "SPACE": 0x20, "BACKSPACE": 0x08,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
}
EXTENDED = {"UP", "DOWN", "LEFT", "RIGHT", "PAGEUP", "PAGEDOWN"}

# ---------------- SendInput 定义 ----------------
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.windll.user32 if os.name == "nt" else None
if _user32 is not None:
    _user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = wt.UINT


def send_vk(vk, up=False, extended=False):
    """注入单个按键事件；返回是否成功。"""
    flags = 0
    if up:
        flags |= KEYEVENTF_KEYUP
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = 0
    inp.u.ki.dwFlags = flags
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = 0
    return _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


# ---------------- 日志（v1.1: 异步队列 + 句柄常开） ----------------
_LOGQ = queue.Queue(maxsize=4000)


def _log_worker():
    """独立线程消费日志队列；文件句柄常开（行缓冲）。写失败自动重开。"""
    f = None
    while True:
        line = _LOGQ.get()
        if f is None:
            try:
                f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
            except Exception:
                f = None
                time.sleep(0.5)
                continue          # 本次消息丢弃，下次再试
        try:
            f.write(line + "\n")
        except Exception:
            try:
                f.close()
            except Exception:
                pass
            f = None


threading.Thread(target=_log_worker, daemon=True, name="log-worker").start()


def log(msg, also_console=False):
    """v1.1: 只做入队（µs 级返回），绝不阻塞调用线程。"""
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    if DEBUG or also_console:
        try:
            print(line, flush=True)
        except Exception:
            pass
    try:
        _LOGQ.put_nowait(line)
    except queue.Full:
        pass                      # 保链路优先：日志可丢弃


# ---------------- 业务处理 ----------------
_voice_lock = threading.Lock()
_voice_held = False
_voice_down_at = 0.0              # v1.1: 兜底释放用


def _mic_switch_down():
    """v1.3: 语音按下——先把系统默认录音设备切到 CABLE Output（微信输入法读「默认设备」），
    调用方随后才注入 Ctrl+Win（先切后注入）。fail-open：切换失败照常注入。"""
    if win_audio_switch is None:
        log("mic switch: module NOT loaded (%s)" % _WAS_ERR)
        return
    t0 = time.monotonic()
    sok, sdet = win_audio_switch.switch_to_virtual()
    log("mic switch -> ok=%s [%s] (%.0fms)" % (sok, sdet, (time.monotonic() - t0) * 1000))


def _mic_restore_up():
    """v1.3: 语音松开——注入释放后调用；延迟 ~2s 切回原设备（连按自动取消）。"""
    if win_audio_switch is None:
        return
    win_audio_switch.schedule_restore()
    log("mic restore scheduled (%.1fs)" % win_audio_switch.RESTORE_DELAY)


def _release_locked():
    """（调用方持 _voice_lock）逆序释放 Ctrl+Win；返回是否全部成功。"""
    global _voice_held
    ok = True
    for vk in reversed(VOICE_MODS):
        ok = send_vk(vk, up=True) and ok
    _voice_held = False
    return ok


def handle_voice(msg):
    global _voice_held, _voice_down_at
    m = msg.strip().lower()
    with _voice_lock:
        if m == "voice down":
            if _voice_held:
                log("VOICE down ignored (already held)")
                return
            _mic_switch_down()          # v1.3: 先切设备（~200ms 预算; fail-open 不拦链路）
            ok = True
            for vk in VOICE_MODS:
                ok = send_vk(vk, up=False) and ok
            _voice_held = True
            _voice_down_at = time.monotonic()
            log("VOICE start (hold %s) ok=%s" % ("+".join(hex(v) for v in VOICE_MODS), ok))
        elif m == "voice up":
            if not _voice_held:
                log("VOICE up ignored (not held)")
                return
            ok = _release_locked()
            _voice_down_at = 0.0
            log("VOICE stop (release) ok=%s" % ok)
            _mic_restore_up()           # v1.3: 释放后延迟切回默认设备
        else:
            log("voice msg ignored: [%s]" % msg)


def check_voice_hold(now=None):
    """v1.1 兜底：down 超时未见 up -> 自动释放（防丢包卡住 Ctrl+Win）。
    watchdog 线程每 5s 调一次；测试可直接调。返回是否触发了释放。"""
    now = now if now is not None else time.monotonic()
    with _voice_lock:
        if _voice_held and _voice_down_at and (now - _voice_down_at) > VOICE_MAX_HOLD:
            ok = _release_locked()
            log("VOICE auto-release (held %.0fs without up, watchdog) ok=%s"
                % (now - _voice_down_at, ok))
            _mic_restore_up()           # v1.3: 兜底释放同样切回
            return True
    return False


def _voice_watchdog():
    while True:
        time.sleep(5)
        try:
            check_voice_hold()
        except Exception as e:
            log("watchdog error: %s" % e)


def handle_key(msg):
    parts = msg.strip().split()
    if len(parts) != 3 or parts[0].upper() != "KEY":
        log("bad key msg: [%s]" % msg)
        return
    action_raw = parts[1]                # v1.5: 原值传扩展动作（URL/RUN 大小写保真）
    action = action_raw.upper()          # 键盘查表/分派判定用大写
    phase = parts[2].lower()
    # v1.7: MOUSE:* 专用路由（DOWN+UP 双向 hold 语义 —— 不走 ext down-only 管道;
    # 在 picker 路由/VK 查表之前直接分流）
    if action.startswith("MOUSE:"):
        handle_mouse(action, phase)
        return
    # v1.4: 应用选择器打开时, 键盘动作直连路由（GUI 选择器不依赖系统键盘焦点）
    if win_actions is not None and phase in ("down", "up"):
        _pr = getattr(win_actions, "picker_route", None)
        if _pr is not None and _pr(action, phase):
            log("KEY %s %s -> picker (routed)" % (action, phase))
            return
    vk = VK.get(action)
    if vk is None:
        handle_ext(action_raw, phase)       # v1.2: 扩展动作; v1.5: 传原始串（大小写保真）
        return
    up = (phase == "up")
    ok = send_vk(vk, up=up, extended=(action in EXTENDED))
    log("KEY %s %s -> vk=0x%02X ok=%s" % (action, phase, vk, ok))


# ---------------- v1.7: 鼠标模式（MOUSE:* 专用路由） ----------------
def handle_mouse(action, phase):
    """v1.7: MOUSE:* 动作 -> win_actions.mouse_control 直呼（状态机 + 平台执行）。
    收包线程内执行（win_actions 侧仅集合操作/懒启动线程, µs 级）; 不做防抖 ——
    重复 DOWN 是保活刷新（幂等）, UP 是配对刹车（不可去重）。"""
    if win_actions is None or not hasattr(win_actions, "mouse_control"):
        log("mouse action dropped (win_actions missing/old): [%s]" % action)
        return
    r = win_actions.mouse_control(action, phase)
    log("MOUSE %s %s -> %s" % (action, phase.upper(), r))


# ---------------- v1.2: 扩展动作（CLICK / FOCUS_INPUT / APP:*） ----------------
_ext_last = {}                              # action -> 上次触发 monotonic 时间戳（防抖）
_action_q = queue.Queue(maxsize=64)         # 收包线程 -> action-worker 的任务队列


def handle_ext(action, phase):
    """v1.2 扩展动作入口（收包线程内, 只做防抖+入队——µs 级, 绝不阻塞收包）。
    语义对齐 Mac key_bridge: 仅 DOWN 触发; CLICK/FOCUS/URL/RUN=0.6s, APP=0.35s 防抖。"""
    if win_actions is None:
        log("unknown action (win_actions 未加载: %s): [%s]" % (_WA_ERR, action))
        return
    if not win_actions.is_ext_action(action):
        log("unknown action: [%s]" % action)
        return
    if phase != "down":
        log("KEY %s up ignored (ext: down-only)" % action)
        return
    now = time.monotonic()
    d = win_actions.debounce_for(action)
    last = _ext_last.get(action)
    if last is not None and now - last < d:   # v1.6: 从未记录 ≠ 刚触发（低时钟环境勿误拦）
        log("KEY %s debounced (%.2fs window)" % (action, d))
        return
    _ext_last[action] = now
    try:
        _action_q.put_nowait(action)
        log("KEY %s queued (ext)" % action)
    except queue.Full:
        log("action queue full (%d), dropped: %s" % (_action_q.maxsize, action))


def _action_worker():
    """v1.2: 扩展动作执行线程（UIA 等慢操作都在这里; 同时是 COM apartment 属主线程）。"""
    while True:
        action = _action_q.get()
        try:
            if win_actions is None:
                log("EXT %s dropped (win_actions missing)" % action)
                continue
            r = win_actions.handle(action)
            log("EXT %s -> %s" % (action, r))
        except Exception as e:
            log("EXT %s error: %s" % (action, e))


# ---------------- UDP 监听 ----------------
def listen_udp(port, handler):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)   # v1.1: 防突发积压
    except Exception:
        pass
    try:
        # 不设 SO_REUSEADDR：防止双实例同时绑定造成"幽灵双收"，
        # 第二个实例会 bind 失败并明确退出（日志 FATAL，属正常保护）。
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log("FATAL bind udp :%d failed: %s (another instance running?)" % (port, e),
            also_console=True)
        os._exit(1)
    log("listening udp :%d (%s)" % (port, handler.__name__))
    while True:
        try:
            data, addr = s.recvfrom(1024)
        except Exception as e:
            log("recv error on :%d: %s" % (port, e))
            continue
        msg = data.decode("utf-8", "replace").strip()
        if DEBUG:
            log("RX %s:%d [%s]" % (addr[0], addr[1], msg))
        if msg.upper() == "PING":
            try:
                s.sendto(b"PONG", addr)
            except Exception as e:
                log("PONG send error: %s" % e)
            continue
        try:
            handler(msg)
        except Exception as e:
            log("handler error for [%s]: %s" % (msg, e))


def selftest_main():
    """v1.4: --selftest —— 打印平台/UIA/窗口/焦点元素/音频设备概况（ASCII 安全输出到控制台,
    完整内容写同目录 selftest.log）。"""
    print("=== win_receiver v1.7 selftest ===")
    print("python: %s" % sys.version.split()[0])
    if win_audio_switch is None:
        print("win_audio_switch: LOAD FAILED (%s)" % _WAS_ERR)
    else:
        try:
            win_audio_switch.init(lambda m: None)
            print("win_audio_switch: v%s" % win_audio_switch.VERSION)
            astat = win_audio_switch.status()
            print(astat.encode("ascii", "replace").decode("ascii"))
        except Exception as e:
            print("win_audio_switch status error: %s" % e)
    if win_actions is None:
        print("win_actions: LOAD FAILED (%s)" % _WA_ERR)
        return 1
    try:
        win_actions.init(lambda m: None)    # selftest 静默模块日志（未启动日志线程前的兜底）
        win_actions.prepare()
        text = win_actions.selftest()
        print(text.encode("ascii", "replace").decode("ascii"))
        try:
            with open(os.path.join(HERE, "selftest.log"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print("(full output -> selftest.log)")
        except Exception as e:
            print("(selftest.log write failed: %s)" % e)
        return 0
    except Exception as e:
        print("selftest error: %s" % e)
        return 1


def main():
    if os.name != "nt":
        log("FATAL this receiver only runs on Windows", also_console=True)
        sys.exit(1)
    if "--selftest" in sys.argv:
        sys.exit(selftest_main())
    log("=== remotehub-win receiver v1.7 starting ===", also_console=True)
    log("python=%s user=%s host=%s dir=%s" % (
        sys.version.split()[0], os.environ.get("USERNAME", "?"),
        socket.gethostname(), HERE))
    if win_actions is not None:
        try:
            win_actions.init(log)
            win_actions.prepare()
            log("win_actions v%s loaded (uia=%s)" % (win_actions.VERSION,
                                                     win_actions.uia_probe()))
        except Exception as e:
            log("win_actions init failed: %s (extended actions may fail)" % e)
        threading.Thread(target=_action_worker, daemon=True, name="action-worker").start()
    else:
        log("win_actions NOT loaded (%s) -> extended actions disabled" % _WA_ERR)
    if win_audio_switch is not None:
        try:
            win_audio_switch.init(log)
            _pre = win_audio_switch.list_capture()      # v1.3: 预热 COM（一次性 ~200ms; 让热路径 <100ms）
            log("win_audio_switch v%s loaded (%d capture devices)"
                % (win_audio_switch.VERSION, len(_pre)))
            rok, rdet = win_audio_switch.recover_if_needed()   # 崩溃自愈（上次会话未切回）
            if rdet != "no-recovery-needed":
                log("win_audio_switch startup recover: ok=%s [%s]" % (rok, rdet))
        except Exception as e:
            log("win_audio_switch init failed: %s (mic auto-switch may fail)" % e)
    else:
        log("win_audio_switch NOT loaded (%s) -> mic auto-switch disabled" % _WAS_ERR)
    threading.Thread(target=_voice_watchdog, daemon=True, name="voice-watchdog").start()
    threading.Thread(target=listen_udp, args=(VOICE_PORT, handle_voice), daemon=True).start()
    threading.Thread(target=listen_udp, args=(KEY_PORT, handle_key), daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
