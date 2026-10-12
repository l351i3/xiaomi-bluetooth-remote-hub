#!/usr/bin/env python3
"""relay v0.10 按键状态机离线测试（v2 三份 keymap; mock queue; 临时改 voice_target 后复原）"""
import asyncio
import json
import struct
import sys

sys.path.insert(0, "/root/remote-hub")
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

        # 6. 语音键 target=mac -> 忽略
        EVENTS.clear()
        relay._handle_event(ev(63, 1))
        relay._handle_event(ev(63, 0))
        check("语音键 mac=忽略", EVENTS[:], [])

        # 7. 语音键 target=atv -> YouTube
        EVENTS.clear()
        set_target("atv")
        relay._handle_event(ev(63, 1))
        check("语音键 atv=YouTube", EVENTS[:], [("__LAUNCH__:com.google.ios.youtube", 63)])

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
    finally:
        set_target(orig_target)

    print(f"\n== 结果: {ok[0]} PASS / {fail[0]} FAIL ==")
    return 0 if fail[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
