#!/usr/bin/env python3
"""voice_fwd v2.3 KeyForwarder 离线逻辑测试（纯决策, 不发网络）
v2.3: handle() 返回列表（一次事件可发多条）; 新增长按（long）断言组。"""
import sys

sys.path.insert(0, "/root/remote-hub")
import voice_fwd as v  # noqa: E402

CFG = {"version": 2, "hold_threshold": 0.6, "targets": {
    "atv": {"keys": {"28": {"single": "select"}}},
    "mac": {"keys": {
        "28": {"single": "ENTER", "repeat": False},
        "158": {"single": "ESC", "repeat": False},
        "103": {"single": "UP", "repeat": True},
        "116": {"single": None, "repeat": False},
        "102": {"single": "APP:CYCLE", "long": "APP:PICK", "repeat": False},
        "105": {"single": "LEFT", "repeat": True},
    }},
    "win": {"keys": {}},
}}


def main():
    ok = [0]
    fail = [0]

    def check(name, got, want):
        if got == want:
            ok[0] += 1
            print(f"  PASS {name}: {got}")
        else:
            fail[0] += 1
            print(f"  FAIL {name}: got={got} want={want}")

    # 1. 基础 down/up（v2.3: 返回 list）
    kf = v.KeyForwarder()
    kf.set_cfg(CFG)
    check("mac OK down", kf.handle(28, 1, "mac", now=100.0), [("mac", "ENTER", "down")])
    check("mac OK up", kf.handle(28, 0, "mac", now=100.1), [("mac", "ENTER", "up")])

    # 2. atv 目标普通键全忽略
    check("atv 忽略", kf.handle(28, 1, "atv", now=101.0), [])

    # 3. repeat 键连发（val=2 节流 0.12）
    kf = v.KeyForwarder()
    kf.set_cfg(CFG)
    check("连发 down", kf.handle(103, 1, "mac", now=200.0), [("mac", "UP", "down")])
    check("连发节流内忽略", kf.handle(103, 2, "mac", now=200.05), [])
    check("连发过节流", kf.handle(103, 2, "mac", now=200.2), [("mac", "UP", "down")])
    check("连发 up", kf.handle(103, 0, "mac", now=201.0), [("mac", "UP", "up")])

    # 4. 非 repeat 键 val=2 忽略
    kf2 = v.KeyForwarder()
    kf2.set_cfg(CFG)
    kf2.handle(28, 1, "mac", now=300.0)
    check("非连发键 val2 忽略", kf2.handle(28, 2, "mac", now=300.2), [])
    kf2.handle(28, 0, "mac", now=300.3)

    # 5. 配对纪律: down@mac 后切到 atv, 松开仍回 mac
    kf3 = v.KeyForwarder()
    kf3.set_cfg(CFG)
    kf3.handle(158, 1, "mac", now=400.0)
    check("配对纪律(切换目标)", kf3.handle(158, 0, "atv", now=400.2), [("mac", "ESC", "up")])

    # 6. 配对纪律(连发): down@mac 后切 atv, val=2 仍发 mac
    kf4 = v.KeyForwarder()
    kf4.set_cfg(CFG)
    kf4.handle(103, 1, "mac", now=500.0)
    check("配对纪律(连发)", kf4.handle(103, 2, "atv", now=500.2), [("mac", "UP", "down")])

    # 7. 空动作键 → []
    check("空动作键忽略", kf.handle(116, 1, "mac", now=600.0), [])

    # 8. 无 down 记录的孤儿 up → []
    check("孤儿 up 忽略", kf.handle(105, 0, "mac", now=700.0), [])

    # 9. v1 旧结构归一化
    c = v._normalize_cfg({"keys": {"28": {"single": "ENTER"}}})
    check("v1 归一化->atv", c["targets"]["atv"]["keys"]["28"]["single"], "ENTER")
    check("v1 归一化 mac 空", c["targets"]["mac"]["keys"], {})

    # 10. 现网 keymap.json 集成检查
    live = v.load_cfg()
    mk = live["targets"]["mac"]["keys"]
    check("现网 mac OK=ENTER", mk.get("28", {}).get("single"), "ENTER")
    check("现网 mac 返回=BACKSPACE/连发", [mk.get("158", {}).get("single"), mk.get("158", {}).get("repeat")], ["BACKSPACE", True])
    check("现网 mac 左=LEFT/连发", [mk.get("105", {}).get("single"), mk.get("105", {}).get("repeat")], ["LEFT", True])
    check("现网 mac 菜单=ESC/连发", [mk.get("127", {}).get("single"), mk.get("127", {}).get("repeat")], ["ESC", True])
    check("现网 atv OK=select(未被改动)", live["targets"]["atv"]["keys"]["28"]["single"], "select")
    check("现网 hold_threshold 可读", isinstance(live.get("hold_threshold"), (int, float)), True)

    # 11. v2.1 自建连发 tick（v2.3 格式: ("repeat", tgt, action, code)）
    kf5 = v.KeyForwarder()
    kf5.set_cfg(CFG)
    kf5.handle(103, 1, "mac", now=800.0)
    check("tick 首延迟内不补发", kf5.tick(now=800.4), [])
    check("tick 首延迟到 -> 补发", kf5.tick(now=800.6), [("repeat", "mac", "UP", 103)])
    check("tick 节流内不补发", kf5.tick(now=800.65), [])
    check("tick 过节流 -> 再补发", kf5.tick(now=800.75), [("repeat", "mac", "UP", 103)])
    kf5.handle(103, 0, "mac", now=801.0)
    check("tick 松手后停", kf5.tick(now=801.5), [])
    kf6 = v.KeyForwarder()
    kf6.set_cfg(CFG)
    kf6.handle(28, 1, "mac", now=900.0)
    check("tick 非 repeat 键不补发", kf6.tick(now=902.0), [])
    kf6.handle(103, 1, "mac", now=910.0)
    kf6.reset()
    check("reset 后 tick 空（重挂防幽灵）", kf6.tick(now=912.0), [])
    kf7 = v.KeyForwarder()
    kf7.set_cfg(CFG)
    kf7.handle(103, 1, "mac", now=1000.0)
    check("tick 配对纪律(down时目标)", kf7.tick(now=1001.0), [("repeat", "mac", "UP", 103)])
    kf8 = v.KeyForwarder()
    kf8.set_cfg(CFG)
    kf8.handle(103, 1, "mac", now=1100.0)
    check("val2 补发(兼容路径)", kf8.handle(103, 2, "mac", now=1100.6), [("mac", "UP", "down")])
    check("tick 与 val2 共用节流", kf8.tick(now=1100.65), [])
    check("tick 过后可再补", kf8.tick(now=1100.75), [("repeat", "mac", "UP", 103)])

    # 12. v2.3 长按（long）断言组
    kfL = v.KeyForwarder()
    kfL.set_cfg(CFG)
    check("长按键 val=1 不即时发", kfL.handle(102, 1, "mac", now=1200.0), [])
    check("长按 pending 登记", 102 in kfL.pending_long, True)
    check("长按未满阈值不触发", kfL.tick(now=1200.5), [])
    check("长按满阈值触发 long", kfL.tick(now=1200.7), [("long", "mac", "APP:PICK", 102)])
    check("long 只触发一次", kfL.tick(now=1201.0), [])
    check("触发后 UP 发 long", kfL.handle(102, 0, "mac", now=1201.3), [("mac", "APP:PICK", "up")])
    check("long_fired 清理", 102 not in kfL.long_fired, True)

    kfL2 = v.KeyForwarder()
    kfL2.set_cfg(CFG)
    kfL2.handle(102, 1, "mac", now=1300.0)
    check("短按(未满阈值)松开发 single 成对",
          kfL2.handle(102, 0, "mac", now=1300.3),
          [("mac", "APP:CYCLE", "down"), ("mac", "APP:CYCLE", "up")])

    kfL3 = v.KeyForwarder()
    kfL3.set_cfg(CFG)
    kfL3.handle(102, 1, "mac", now=1400.0)
    kfL3.reset()
    check("reset 清长按态", not kfL3.pending_long and not kfL3.long_fired, True)

    kfL4 = v.KeyForwarder()
    kfL4.set_cfg(dict(CFG, hold_threshold=0.3))
    kfL4.handle(102, 1, "mac", now=1500.0)
    check("阈值可配置(0.3s)",
          kfL4.tick(now=1500.35), [("long", "mac", "APP:PICK", 102)])
    kfL4.handle(102, 0, "mac", now=1500.5)

    kfL5 = v.KeyForwarder()
    kfL5.set_cfg(CFG)
    kfL5.handle(102, 1, "mac", now=1600.0)
    check("long 键 val=2 忽略（repeat=False）", kfL5.handle(102, 2, "mac", now=1600.3), [])
    kfL5.handle(102, 0, "mac", now=1600.5)

    # 13. long 触发后配对纪律（目标切换, UP 回原目标 long 动作）
    kfL6 = v.KeyForwarder()
    kfL6.set_cfg(CFG)
    kfL6.handle(102, 1, "mac", now=1700.0)
    kfL6.tick(now=1700.7)
    check("long 后配对纪律(切目标)", kfL6.handle(102, 0, "atv", now=1701.0), [("mac", "APP:PICK", "up")])

    # 14. long 与 repeat 互斥双保险（人为双开场景: long_fired 后不补发）
    CFG2 = {"version": 2, "hold_threshold": 0.6, "targets": {
        "atv": {"keys": {}}, "win": {"keys": {}},
        "mac": {"keys": {"103": {"single": "UP", "long": "SPACE", "repeat": True}}}}}
    kfX2 = v.KeyForwarder()
    kfX2.set_cfg(CFG2)
    kfX2.handle(103, 1, "mac", now=1900.0)
    check("双开场景: long 优先触发", kfX2.tick(now=1900.7), [("long", "mac", "SPACE", 103)])
    r = kfX2.tick(now=1901.2)
    check("双开场景: long 后不连发", all(k != "repeat" for k, t, a, c in r), True)

    print(f"\n== 结果: {ok[0]} PASS / {fail[0]} FAIL ==")
    return 0 if fail[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
