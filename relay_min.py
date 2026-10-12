#!/usr/bin/env python3
"""M4 全键中继 daemon v0.10: RC003 遥控器 -> T1 -> ATV4K

数据流: /dev/input/event2 (只读, 不 grab) -> pyatv remote_control -> ATV4K
按键映射 (2026-10-09 用户拍板 v0.7 五轮调整; v0.8 摘除语音键; v0.9 配置外置+双击+语音分流;
          v0.10 三份 keymap 按目标分流):
  v0.10 变更（2026-10-10 用户指示"keymapping 需要有三份"）:
    · keymap.json v2 = {targets: {atv, mac, win}}，三个目标各一份 13 键配置
    · 本服务只负责 target=atv：取 targets.atv.keys（与 v0.9 行为完全一致）
    · target=mac/win 时本服务忽略全部按键（交 voice_fwd.py 转发目标电脑）
    · 兼容 v1 旧结构（无 targets 时自动视为 atv 单份）
  映射表外置到 keymap.json（:8765 /keymap 页三 tab 可改），按键时 mtime 检测自动热重载
  —— 不重建 ATV 连接、不断蓝牙。ATV 份默认（=v0.8 行为）:
    方向 103/108/105/106 -> up/down/left/right (长按连发, 节流 120ms)
    OK 28 -> select
    返回 158 -> menu (纯单发, 长按功能已取消) [v0.6]
    菜单 127 -> play_pause [v0.5, HID 直发(12,0xCD), 原厂播放暂停键等效]
    主页 102 -> 短按 home / 长按(>=0.6s) home_hold=控制中心 [v0.6]
    音量 115/114 -> volume_up/volume_down
    电源 116 -> 电源切换 (__POWER__)
    直播 41  -> 一键打开极空间 launch_app [v0.3]
    语音 63  -> [v0.9] 按语音目标分流 (voice_target 文件, :8765 主页三按钮切换):
                target=atv -> 一键打开 YouTube (bundle 经 app_list 实机核实);
                target=mac/win -> 忽略 (转交 voice_fwd.py 转发语音输入)
按键实际由 pyatv facade 转发: 全部走 MRP 隧道(AirPlay 凭据), launch 走 Companion
  ※ play_pause 教训(10-09): facade/MRP 的 play_pause 走"媒体命令通道"(TogglePlayPause),
    依赖播放器注册媒体状态, 第三方 app/非播放场景会被静默跳过(日志假成功);
    改走 HID 按键通道(运行时给 pyatv _KEY_LOOKUP 注入 play_pause 键位), 与原厂键等效
  ※ 应用切换器: 配置可选 __APP_SWITCH__(home DoubleTap); 物理双击主页键即用, 默认不挂
配置模型 (keymap.json v2): {hold_threshold, double_window, targets: {atv/mac/win: {keys: {"code": {single,double,long,repeat}}}}}
  - 本服务仅消费 targets.atv.keys；target≠atv 时忽略按键（voice_fwd 接管转发）
  - 无 long/double 键: 按下即发 single (repeat 键按住连发)
  - 有 long 键: 按住 >=hold_threshold 触发 long; 未到阈值松开发 single
  - 有 double 键: 单击延迟 double_window 判定, 窗口内二击发 double (长按优先)
  - repeat 键不允许 long/double (repeat=按住连发机制, 与二者互斥)
运行: systemctl restart t1-relay
  (手动: cd /root/remote-hub; nohup /opt/pyatv/bin/python3 relay_min.py > /tmp/relay_min.log 2>&1 < /dev/null &)
特性: 遥控器断开/重连自动重挂 event 设备（按设备名动态发现, 不绑定 eventN 编号）
"""
import asyncio
import glob
import json
import os
import struct
import time

import pyatv
from pyatv.const import InputAction, PowerState, Protocol

# v0.5: 给 pyatv MRP 键位表运行时注入 play_pause (Consumer page 0xCD = Play/Pause Toggle)
# 仅影响本进程, 不动 site-packages; 失败则回退 facade 调用
try:
    from pyatv.protocols.mrp import _KEY_LOOKUP, _send_hid_key

    _KEY_LOOKUP.setdefault("play_pause", (12, 0xCD))
    _HID_PLAYPAUSE_READY = True
except Exception:  # noqa: BLE001
    _HID_PLAYPAUSE_READY = False

ATV_ID = "F6AFC21D-9D6A-4505-B0FC-4E84E9D4D2FF"
CREDS = "/root/remote-hub/atv-credentials.json"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "keymap.json")
CFG_DEFAULT_PATH = os.path.join(HERE, "keymap.default.json")
VOICE_TARGET_PATH = os.path.join(HERE, "voice_target")
EV_KEY = 1
REPEAT_THROTTLE = 0.12
VOICE_KEY = 63                            # 语音键 = KEY_F5
YOUTUBE_BUNDLE = "com.google.ios.youtube"  # v0.7 经 app_list 实机核实

# 特例动作（sender 分派用）
SWITCH_CMD = "__APP_SWITCH__"     # 应用切换器 (home DoubleTap)
PLAY_PAUSE_CMD = "__PLAY_PAUSE__"  # 播放/暂停 (HID 直发)
POWER_CMD = "__POWER__"           # 电源切换
LAUNCH_PREFIX = "__LAUNCH__:"     # __LAUNCH__:<bundle_id>

# 内置兜底（keymap.json 与 keymap.default.json 均不可读时保 ATV 核心键可用;
# mac/win 目标留空 —— 配置文件双双损坏属重大异常, 此时保守仅保 ATV 链路）
FALLBACK_CFG = {
    "version": 2,
    "hold_threshold": 0.6,
    "double_window": 0.3,
    "targets": {
        "atv": {"keys": {
            "102": {"single": "home", "double": None, "long": "home_hold", "repeat": False},
            "158": {"single": "menu", "double": None, "long": None, "repeat": False},
            "103": {"single": "up", "double": None, "long": None, "repeat": True},
            "108": {"single": "down", "double": None, "long": None, "repeat": True},
            "105": {"single": "left", "double": None, "long": None, "repeat": True},
            "106": {"single": "right", "double": None, "long": None, "repeat": True},
            "28": {"single": "select", "double": None, "long": None, "repeat": False},
            "115": {"single": "volume_up", "double": None, "long": None, "repeat": True},
            "114": {"single": "volume_down", "double": None, "long": None, "repeat": True},
            "116": {"single": POWER_CMD, "double": None, "long": None, "repeat": False},
            "41": {"single": LAUNCH_PREFIX + "com.zentraedi.zspaceTV", "double": None, "long": None, "repeat": False},
            "127": {"single": PLAY_PAUSE_CMD, "double": None, "long": None, "repeat": False},
        }},
        "mac": {"keys": {}},
        "win": {"keys": {}},
    },
}


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


def _load_cfg_file(path):
    """读取并规范化配置: v2 (targets) 或 v1 (单份 keys -> 视为 atv)"""
    with open(path) as f:
        cfg = json.load(f)
    if isinstance(cfg.get("targets"), dict):
        for t in ("atv", "mac", "win"):
            tk = cfg["targets"].get(t)
            if not isinstance(tk, dict) or not isinstance(tk.get("keys"), dict):
                raise ValueError(f"targets.{t}.keys 缺失")
        return cfg
    if isinstance(cfg.get("keys"), dict):
        # v1 兼容: 单份键表视为 atv 目标
        return {
            "version": 2,
            "hold_threshold": cfg.get("hold_threshold", 0.6),
            "double_window": cfg.get("double_window", 0.3),
            "targets": {"atv": {"keys": cfg["keys"]}, "mac": {"keys": {}}, "win": {"keys": {}}},
        }
    raise ValueError("keys/targets 缺失")


def load_cfg():
    """keymap.json -> keymap.default.json -> 内置兜底（三级保护）"""
    for p in (CFG_PATH, CFG_DEFAULT_PATH):
        try:
            return _load_cfg_file(p)
        except Exception as e:  # noqa: BLE001
            log(f"配置加载失败 {p}: {e!r}")
    log("使用内置兜底配置")
    return FALLBACK_CFG


def read_voice_target():
    """语音目标: atv/mac/win；文件缺失或损坏回退 mac（现状）"""
    try:
        with open(VOICE_TARGET_PATH) as f:
            t = f.read().strip()
        return t if t in ("atv", "mac", "win") else "mac"
    except Exception:  # noqa: BLE001
        return "mac"


def find_dev():
    """动态发现遥控器 HOG 输入设备（不绑定 eventN 编号）"""
    for ev in sorted(glob.glob("/dev/input/event*")):
        try:
            with open(f"/sys/class/input/{os.path.basename(ev)}/device/name") as f:
                name = f.read().strip()
            if "hog" in name.lower() or "小米" in name or "RC003" in name:
                return ev
        except Exception:  # noqa: BLE001
            continue
    return None


class Relay:
    def __init__(self):
        self.atv = None
        self.queue = asyncio.Queue()
        self.sent = 0
        self.fail = 0
        self.last_repeat = {}
        self.mrp_protocol = None  # MRP 底层 protocol (v0.5, HID 直发用)
        # v0.9: 配置与按键状态
        self.cfg = load_cfg()
        self._cfg_mtime = self._stat_cfg_mtime()
        self.key_state = {}  # code -> {hold_task, hold_fired, single_timer, armed_double, down_t}
        self._last_target = read_voice_target()  # v0.10: 目标切换日志去抖
        log(f"配置就绪: ATV 份 {len(self._akeys())} 键  hold={self.cfg.get('hold_threshold')}s "
            f"double={self.cfg.get('double_window')}s  voice_target={self._last_target}")

    # ---- v0.10 三份 keymap：本服务取 atv 份 ----
    def _akeys(self):
        return self.cfg.get("targets", {}).get("atv", {}).get("keys", {})

    def _now_target(self):
        """读当前目标；切换时留一行日志（本服务仅 atv 生效）"""
        t = read_voice_target()
        if t != self._last_target:
            self._last_target = t
            if t == "atv":
                log("目标=atv: relay 接管按键")
            else:
                log(f"目标={t}: relay 忽略按键（交 voice_fwd 转发）")
        return t

    # ---- v0.9 配置热重载 ----
    def _stat_cfg_mtime(self):
        try:
            return os.stat(CFG_PATH).st_mtime
        except Exception:  # noqa: BLE001
            return None

    def _maybe_reload(self):
        """按键事件时检查 keymap.json 变更 -> 热重载（不断 BLE、不重建 ATV 连接）"""
        m = self._stat_cfg_mtime()
        if m == self._cfg_mtime:
            return
        self.cfg = load_cfg()
        self._cfg_mtime = self._stat_cfg_mtime()
        log(f"keymap.json 变更 -> 配置已热重载 (ATV 份 {len(self._akeys())} 键)")

    async def connect_atv(self):
        loop = asyncio.get_event_loop()
        while True:
            try:
                atvs = await pyatv.scan(loop, timeout=8, identifier=ATV_ID)
                if atvs:
                    conf = atvs[0]
                    creds = json.load(open(CREDS))
                    conf.set_credentials(Protocol.Companion, creds.get("Companion"))
                    conf.set_credentials(Protocol.AirPlay, creds.get("AirPlay"))
                    self.atv = await pyatv.connect(conf, loop)
                    log(f"ATV connected: {self.atv.device_info}")
                    self._find_mrp_protocol()
                    return
                log("未发现 ATV，5s 后重试")
            except Exception as e:  # noqa: BLE001
                log(f"ATV connect 失败: {e!r}")
            await asyncio.sleep(5)

    def _find_mrp_protocol(self):
        """从 facade 的 remote_control 实例里找到 MRP 实现, 保存其底层 protocol"""
        try:
            for inst in self.atv.remote_control.instances:
                if "mrp" in inst.__class__.__module__:
                    self.mrp_protocol = getattr(inst, "protocol", None)
                    break
        except Exception as e:  # noqa: BLE001
            log(f"MRP protocol 查找失败: {e!r}")
        log(f"MRP protocol: {'OK' if self.mrp_protocol else 'NOT FOUND'} (HID 直发{'可用' if _HID_PLAYPAUSE_READY else '不可用'})")

    async def power_toggle(self):
        try:
            state = self.atv.power.power_state
            if state == PowerState.On:
                await self.atv.power.turn_off()
                log("POWER: On -> turn_off")
            else:
                await self.atv.power.turn_on()
                log(f"POWER: {state} -> turn_on")
        except Exception as e:  # noqa: BLE001
            log(f"POWER-FAIL: {e!r}")

    async def _send_play_pause(self):
        """v0.5: 播放/暂停 HID 直发 (Consumer page 0xCD)。
        旧路径 facade play_pause 走 MRP 媒体命令(TogglePlayPause), 依赖播放器注册
        媒体状态, 第三方 app/非播放场景会被静默跳过(日志假成功)。"""
        if _HID_PLAYPAUSE_READY and self.mrp_protocol is not None:
            await _send_hid_key(self.mrp_protocol, "play_pause", InputAction.SingleTap)
        else:
            # 兜底: facade 媒体命令通道 (可用性有限)
            await self.atv.remote_control.play_pause()

    async def sender(self):
        while True:
            cmd, code = await self.queue.get()
            try:
                if cmd == SWITCH_CMD:
                    # 应用切换器: 双击 home (tvOS App Switcher)
                    await self.atv.remote_control.home(action=InputAction.DoubleTap)
                    self.sent += 1
                    log(f"SENT code={code} -> app_switcher (home DoubleTap) (sent={self.sent} fail={self.fail})")
                elif cmd == PLAY_PAUSE_CMD:
                    # 播放/暂停: HID 直发 (12,0xCD), 与原厂 play/pause 键等效 [v0.5]
                    await self._send_play_pause()
                    self.sent += 1
                    log(f"SENT code={code} -> play_pause (HID 0xCD) (sent={self.sent} fail={self.fail})")
                elif cmd == POWER_CMD:
                    await self.power_toggle()
                elif cmd.startswith(LAUNCH_PREFIX):
                    bundle = cmd[len(LAUNCH_PREFIX):]
                    await self.atv.apps.launch_app(bundle)
                    self.sent += 1
                    log(f"SENT code={code} -> launch_app {bundle} (sent={self.sent} fail={self.fail})")
                else:
                    await getattr(self.atv.remote_control, cmd)()
                    self.sent += 1
                    log(f"SENT code={code} -> {cmd} (sent={self.sent} fail={self.fail})")
            except Exception as e:  # noqa: BLE001
                self.fail += 1
                log(f"SEND-FAIL code={code} -> {cmd}: {e!r}")

    # ---- v0.9 通用按键处理（单击/双击/长按 + 连发） ----
    def _emit(self, code, cmd):
        self.queue.put_nowait((cmd, code))

    def _emit_single(self, code):
        """双击窗口到点：发单击"""
        st = self.key_state.get(code)
        if st:
            st["single_timer"] = None
        ck = self._akeys().get(str(code)) or {}
        single = ck.get("single")
        if single:
            log(f"KEY {code} 单击 -> {single}")
            self._emit(code, single)

    async def _hold_timer(self, code):
        threshold = self.cfg.get("hold_threshold", 0.6)
        try:
            await asyncio.sleep(threshold)
        except asyncio.CancelledError:
            return
        ck = self._akeys().get(str(code)) or {}
        lng = ck.get("long")
        if not lng:
            return
        st = self.key_state.get(code)
        if st is not None:
            st["hold_fired"] = True
        log(f"KEY {code} 长按 -> {lng}")
        self._emit(code, lng)

    def _handle_event(self, data):
        _s, _us, etype, code, val = struct.unpack("llHHi", data[:24])
        if etype != EV_KEY:
            return
        self._maybe_reload()

        # v0.9: 语音键按目标分流（atv=开 YouTube; mac/win=忽略交 voice_fwd）
        if code == VOICE_KEY:
            if val == 1:
                t = self._now_target()
                if t == "atv":
                    log("KEY63 语音 (atv 模式) -> launch YouTube")
                    self._emit(VOICE_KEY, LAUNCH_PREFIX + YOUTUBE_BUNDLE)
                else:
                    log(f"KEY63 语音 -> 忽略 (target={t}, 交 voice_fwd)")
            return

        # v0.10: 普通键仅 target=atv 时生效；mac/win 全交 voice_fwd 转发
        if self._now_target() != "atv":
            return

        ck = self._akeys().get(str(code))
        if not ck:
            return
        single = ck.get("single")
        double = ck.get("double")
        lng = ck.get("long")
        repeat = bool(ck.get("repeat"))
        st = self.key_state.setdefault(code, {"hold_task": None, "hold_fired": False,
                                              "single_timer": None, "armed_double": False, "down_t": 0.0})

        if val == 1:
            # 重置连发节流（防"按下紧邻的重复事件"双发; v0.8 同款）
            self.last_repeat[code] = time.monotonic()
            # 双击窗口内第二击？
            if st["single_timer"]:
                st["single_timer"].cancel()
                st["single_timer"] = None
                st["armed_double"] = True
            st["hold_fired"] = False
            st["down_t"] = time.monotonic()
            if lng:
                t = st.get("hold_task")
                if t and not t.done():
                    t.cancel()
                st["hold_task"] = asyncio.create_task(self._hold_timer(code))
            # 无长按、无双击 -> 按下即发（v0.8 等价路径）
            if single and not lng and not double:
                log(f"KEY code={code} ({single}) pressed")
                self._emit(code, single)
        elif val == 2:
            # 长按自动重复 -> 连发（节流）
            if repeat and single:
                now = time.monotonic()
                if now - self.last_repeat.get(code, 0.0) >= REPEAT_THROTTLE:
                    self.last_repeat[code] = now
                    self._emit(code, single)
        elif val == 0:
            t = st.get("hold_task")
            if t and not t.done():
                t.cancel()
            st["hold_task"] = None
            if st["hold_fired"]:
                # 长按已触发（含双击半程变长按）: 丢弃双击意图
                st["armed_double"] = False
                return
            if st["armed_double"]:
                st["armed_double"] = False
                if double:
                    log(f"KEY {code} 双击 -> {double}")
                    self._emit(code, double)
                return
            # 普通短按松开（未达长按阈值）
            if double:
                # 配置了双击 -> 单击延后 double_window 判定
                if single:
                    st["single_timer"] = asyncio.get_event_loop().call_later(
                        self.cfg.get("double_window", 0.3), self._emit_single, code)
            elif single and lng:
                # 有长按配置的键: 短按在松开时发（v0.8 主页逻辑）
                log(f"KEY {code} 短按 -> {single}")
                self._emit(code, single)
            # (single 且无 lng 无 double: 已在按下时发出)

    def on_ev(self, fd):
        try:
            while True:
                try:
                    data = os.read(fd, 24)
                except BlockingIOError:
                    return
                if not data:
                    raise OSError("EOF")
                if len(data) < 24:
                    return
                self._handle_event(data)
        except OSError as e:  # noqa: BLE001
            log(f"event 设备失效: {e!r} -> 等待重挂")
            loop = asyncio.get_event_loop()
            try:
                loop.remove_reader(fd)
            except Exception:  # noqa: BLE001
                pass
            try:
                os.close(fd)
            except Exception:  # noqa: BLE001
                pass
            asyncio.create_task(self.reattach())

    async def reattach(self):
        dev = None
        while dev is None:
            dev = find_dev()
            if dev is None:
                log("等待遥控器 HOG 设备重建 ...")
                await asyncio.sleep(2)
        await asyncio.sleep(0.5)
        fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
        loop = asyncio.get_event_loop()
        loop.add_reader(fd, self.on_ev, fd)
        log(f"event 设备重挂完成: {dev}")


async def main():
    relay = Relay()
    await relay.connect_atv()
    asyncio.create_task(relay.sender())
    await relay.reattach()
    log("relay v0.10 就绪：三份 keymap（:8765 /keymap 三 tab，热重载）| 仅 target=atv 生效 | "
        "主页短=主屏/长=控制中心 | 菜单=播放暂停(HID) | 直播=开极空间 | "
        "语音63=按目标分流(ATV→YouTube / Mac·Win→语音输入) | 电源=切换")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
