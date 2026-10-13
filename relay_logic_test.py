#!/usr/bin/env python3
"""relay v0.12 按键状态机离线测试（v2 三份 keymap; mock queue; 临时改 voice_target 后复原）
v0.11: 电源连击切换断言组（1击=__POWER__ / 2击=mac / 3击=win; 窗口提交; 闸门开关;
       离台丢弃; HUD 目标）+ pyatv 最小桩（Mac 本地无 pyatv 也可运行）。
v0.12: 语音键配置驱动断言（默认=开 YouTube / 改绑跟随 / 清空=无动作; mac 目标忽略）。"""
import asyncio
import json
import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # 本地/Mac 与 T1 现网均可运行


def _ensure_pyatv_stub():
    """pyatv 缺失（Mac 本地跑）时注入最小桩 —— ATV 运行时在测试中不会被调用。"""
    try:
        import pyatv  # noqa: F401
        return
    except Exception:
        pass
    pk = types.ModuleType("pyatv")
    const = types.ModuleType("pyatv.const")

    class InputAction:
        SingleTap = "SingleTap"
        DoubleTap = "DoubleTap"

    class PowerState:
        On = "On"
        Off = "Off"

    class Protocol:
        Companion = "Companion"
        AirPlay = "AirPlay"
        MRP = "MRP"

    const.InputAction = InputAction
    const.PowerState = PowerState
    const.Protocol = Protocol
    pk.const = const
    protos = types.ModuleType("pyatv.protocols")
    protos.__path__ = []
    mrp = types.ModuleType("pyatv.protocols.mrp")
    mrp._KEY_LOOKUP = {}
    mrp._send_hid_key = lambda *a, **k: None
    sys.modules.update({"pyatv": pk, "pyatv.const": const,
                        "pyatv.protocols": protos, "pyatv.protocols.mrp": mrp})


_ensure_pyatv_stub()
import relay_min as r  # noqa: E402

EVENTS = []


class FakeQueue:
    def put_nowait(self, item):
        EVENTS.append(item)


def ev(code, val):
    return struct.pack("llHHi", 0, 0, 1, code, val)


def set_target(t):
    with open(r.VOICE_TARGET_PATH, "w") as f:
        f.write(t + "\n")


def get_target():
    try:
        with open(r.VOICE_TARGET_PATH) as f:
            return f.read().strip()
    except Exception:
        return "atv"


async def settle(sec):
    await asyncio.sleep(sec)


async def main():
    orig_target = get_target()
    set_target("atv")
    relay = object.__new__(r.Relay)
    relay.cfg = r.load_cfg()
    relay.key_state = {}
    relay.last_repeat = {}
    relay.queue = FakeQueue()
    relay._cfg_mtime = relay._stat_cfg_mtime()
    relay._last_target = "atv"
    relay._power_count = 0            # v0.11
    relay._power_timer = None
    relay.hud_sock = None
    HINTS = []
    relay._send_target_hint = lambda t: (HINTS.append(t), True)[1]   # 桩: HUD 不出网（本地/T1 均安全）

    atv_keys = relay.cfg["targets"]["atv"]["keys"]

    ok = [0]
    fail = [0]

    def check(name, got, want):
        if got == want:
            ok[0] += 1
            print(f"  PASS {name}: {got}")
        else:
            fail[0] += 1
            print(f"  FAIL {name}: got={got} want={want}")

    try:
        # 0. v2 结构检查
        check("v2 targets 结构", sorted(relay.cfg["targets"].keys()), ["atv", "mac", "win"])
        check("ATV OK 键=select", atv_keys["28"]["single"], "select")

        # 1. 主页单击（atv）
        EVENTS.clear()
        relay._handle_event(ev(102, 1))
        await settle(0.1)
        relay._handle_event(ev(102, 0))
        await settle(0.1)
        check("主页单击", EVENTS[:], [("home", 102)])

        # 2. 主页长按
        EVENTS.clear()
        relay._handle_event(ev(102, 1))
        await settle(0.75)
        relay._handle_event(ev(102, 0))
        await settle(0.1)
        check("主页长按", EVENTS[:], [("home_hold", 102)])

        # 3. 菜单=播放暂停（按下即发）
        EVENTS.clear()
        relay._handle_event(ev(127, 1))
        await settle(0.05)
        relay._handle_event(ev(127, 0))
        check("菜单->播放暂停", EVENTS[:], [("__PLAY_PAUSE__", 127)])

        # 4. 方向连发（节流）
        EVENTS.clear()
        relay._handle_event(ev(103, 1))
        relay._handle_event(ev(103, 2))
        await settle(0.15)
        relay._handle_event(ev(103, 2))
        relay._handle_event(ev(103, 0))
        check("方向连发", EVENTS[:], [("up", 103), ("up", 103)])

        # 5. [v0.10] target=mac: 普通键全部忽略
        EVENTS.clear()
        set_target("mac")
        relay._handle_event(ev(28, 1))
        relay._handle_event(ev(103, 1))
        relay._handle_event(ev(103, 2))
        await settle(0.05)
        relay._handle_event(ev(28, 0))
        relay._handle_event(ev(103, 0))
        check("mac 目标普通键忽略", EVENTS[:], [])

        # 6. 语音键 target=mac -> 忽略（v0.12: 走通用分派, 非 atv 目标全忽略）
        EVENTS.clear()
        relay._handle_event(ev(63, 1))
        relay._handle_event(ev(63, 0))
        check("语音键 mac=忽略", EVENTS[:], [])

        # 7. 语音键 target=atv -> 默认 YouTube（v0.12: 配置驱动, single 无 long/double 按下即发）
        EVENTS.clear()
        set_target("atv")
        relay._handle_event(ev(63, 1))
        check("语音键 atv=YouTube", EVENTS[:], [("__LAUNCH__:com.google.ios.youtube", 63)])

        # 7b. 语音键改绑跟随（临时改内存配置 -> 极空间; 不写盘）
        EVENTS.clear()
        relay.cfg["targets"]["atv"]["keys"]["63"]["single"] = "__LAUNCH__:com.zentraedi.zspaceTV"
        relay._handle_event(ev(63, 1))
        await settle(0.05)
        relay._handle_event(ev(63, 0))
        check("语音键 改绑->极空间", EVENTS[:], [("__LAUNCH__:com.zentraedi.zspaceTV", 63)])

        # 7c. 语音键清空 -> 无动作（用户可关闭该键; 不再有硬编码兜底）
        EVENTS.clear()
        relay.cfg["targets"]["atv"]["keys"]["63"]["single"] = None
        relay._handle_event(ev(63, 1))
        await settle(0.05)
        relay._handle_event(ev(63, 0))
        check("语音键 清空->无动作", EVENTS[:], [])
        relay.cfg["targets"]["atv"]["keys"]["63"]["single"] = "__LAUNCH__:com.google.ios.youtube"

        # 8. 双击（临时改 v2 内存配置: atv 158 double; 不写盘）
        EVENTS.clear()
        relay.cfg = json.loads(json.dumps(relay.cfg))
        relay.cfg["targets"]["atv"]["keys"]["158"]["double"] = "__APP_SWITCH__"
        relay.key_state.clear()
        relay._handle_event(ev(158, 1))
        await settle(0.05)
        relay._handle_event(ev(158, 0))
        await settle(0.05)
        relay._handle_event(ev(158, 1))
        await settle(0.05)
        relay._handle_event(ev(158, 0))
        await settle(0.1)
        check("双击->应用切换器", EVENTS[:], [("__APP_SWITCH__", 158)])

        # 9. 单击（同配置, 延迟 0.3s 发 menu）
        EVENTS.clear()
        relay.key_state.clear()
        relay._handle_event(ev(158, 1))
        await settle(0.05)
        relay._handle_event(ev(158, 0))
        await settle(0.4)
        check("单击(带双击配置, 延迟)", EVENTS[:], [("menu", 158)])

        # 10. 长按优先（102 加 double 后长按 -> 仍 home_hold）
        EVENTS.clear()
        relay.cfg["targets"]["atv"]["keys"]["102"]["double"] = "__APP_SWITCH__"
        relay.key_state.clear()
        relay._handle_event(ev(102, 1))
        await settle(0.75)
        relay._handle_event(ev(102, 0))
        await settle(0.1)
        check("长按优先于双击", EVENTS[:], [("home_hold", 102)])

        # 11. 双击半程变长按（第二击按住超阈值 -> 发 long 丢 double）
        EVENTS.clear()
        relay.key_state.clear()
        relay._handle_event(ev(102, 1))
        await settle(0.05)
        relay._handle_event(ev(102, 0))
        await settle(0.05)
        relay._handle_event(ev(102, 1))
        await settle(0.75)
        relay._handle_event(ev(102, 0))
        await settle(0.1)
        check("双击半程变长按", EVENTS[:], [("home_hold", 102)])

        # 12. v1 旧结构兼容（临时文件归一化检查）
        v1p = "/tmp/relay_test_v1_cfg.json"
        with open(v1p, "w") as f:
            json.dump({"version": 1, "hold_threshold": 0.6, "double_window": 0.3,
                       "keys": {"28": {"single": "select", "repeat": False}}}, f)
        c = r._load_cfg_file(v1p)
        check("v1 归一化->atv", c["targets"]["atv"]["keys"]["28"]["single"], "select")

        # 13. v0.11 电源连击切换（1击=__POWER__ / 2击=mac / 3击=win）
        check("连击 闸门值(现网)", (relay._akeys().get("116") or {}).get("single"), "TARGET:SWITCH")

        # 13a. 单击: 不即时; 窗口期满 -> __POWER__
        set_target("atv")
        relay.key_state.clear()
        EVENTS.clear()
        HINTS.clear()
        relay._handle_event(ev(116, 1))
        await settle(0.1)
        check("连击 单击不即时", EVENTS[:], [])
        await settle(0.5)
        check("连击 单击期满 -> 电源切换", EVENTS[:], [("__POWER__", 116)])
        relay._handle_event(ev(116, 0))
        await settle(0.05)
        check("连击 单击 up 无额外事件", EVENTS[:], [("__POWER__", 116)])

        # 13b. 双击: 窗口内二击 -> 切 mac + HUD; 绝不出 __POWER__
        EVENTS.clear()
        HINTS.clear()
        set_target("atv")
        relay._handle_event(ev(116, 1))
        await settle(0.08)
        relay._handle_event(ev(116, 0))
        await settle(0.04)
        relay._handle_event(ev(116, 1))
        await settle(0.08)
        relay._handle_event(ev(116, 0))
        check("连击 双击中不出事件", EVENTS[:], [])
        await settle(0.5)
        check("连击 双击期满 -> 切 mac", get_target(), "mac")
        check("连击 双击无 __POWER__ 事件", EVENTS[:], [])
        check("连击 双击 HUD 目标", HINTS[:], ["mac"])

        # 13c. 三击: 第 3 击立即提交 -> 切 win（免等窗口）
        EVENTS.clear()
        HINTS.clear()
        set_target("atv")
        relay._handle_event(ev(116, 1))
        await settle(0.05)
        relay._handle_event(ev(116, 0))
        await settle(0.03)
        relay._handle_event(ev(116, 1))
        await settle(0.05)
        relay._handle_event(ev(116, 0))
        await settle(0.03)
        relay._handle_event(ev(116, 1))
        await settle(0.1)
        check("连击 三击立即切 win", get_target(), "win")
        check("连击 三击 HUD", HINTS[:], ["win"])
        relay._handle_event(ev(116, 0))
        await settle(0.55)
        check("连击 三击后无额外提交", (get_target(), EVENTS[:]), ("win", []))

        # 13d. 闸门撤下（single 改回 __POWER__）-> 旧语义（按下即发, 无连击等待）
        set_target("atv")
        EVENTS.clear()
        HINTS.clear()
        _bak116 = relay.cfg["targets"]["atv"]["keys"]["116"]
        relay.cfg["targets"]["atv"]["keys"]["116"] = {"single": "__POWER__", "double": None,
                                                      "long": None, "repeat": False}
        relay._handle_event(ev(116, 1))
        check("连击 闸门撤下 -> 按下即发", EVENTS[:], [("__POWER__", 116)])
        await settle(0.55)
        check("连击 闸门撤下 无二次提交", EVENTS[:], [("__POWER__", 116)])
        relay._handle_event(ev(116, 0))
        relay.cfg["targets"]["atv"]["keys"]["116"] = _bak116

        # 13e. 目标≠atv 时 #116 全忽略（连击层不参与 —— 交 voice_fwd 侧）
        set_target("mac")
        EVENTS.clear()
        HINTS.clear()
        relay._handle_event(ev(116, 1))
        await settle(0.1)
        relay._handle_event(ev(116, 0))
        await settle(0.55)
        check("连击 mac 目标忽略", (EVENTS[:], HINTS[:], get_target()), ([], [], "mac"))

        # 13f. 计数期间离开 atv -> 提交丢弃（防串台）
        set_target("atv")
        EVENTS.clear()
        HINTS.clear()
        relay._handle_event(ev(116, 1))
        await settle(0.05)
        set_target("mac")
        await settle(0.6)
        check("连击 离台提交丢弃", (EVENTS[:], HINTS[:]), ([], []))
    finally:
        set_target(orig_target)

    print(f"\n== 结果: {ok[0]} PASS / {fail[0]} FAIL ==")
    return 0 if fail[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
