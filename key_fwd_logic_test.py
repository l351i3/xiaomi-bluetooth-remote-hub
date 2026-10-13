#!/usr/bin/env python3
"""voice_fwd v2.9 离线逻辑测试（纯决策, 不发网络）
v2.3: handle() 返回列表（一次事件可发多条）; 新增长按（long）断言组。
v2.5: 新增鼠标模式（MouseMode）断言组 —— 键映射/OK 长短按/保活补发/返回退出/
     配对纪律/现网 keymap #41 集成（long=MOUSE:TOGGLE）。
v2.6: 放行键（模式内电源/主页 -> None 转 kf 正常路径, 含长按语义）/
     main 路由语义还原 / send_mode_hint 目标分派与报文（HUD 提示）。
v2.7: 电源连击切换（TargetSwitcher）断言组 —— 单击/双击/三击、窗口提交、按住延后、
     长按中止计数、吞键期、val2/非116 忽略、reset、自定义窗口、send_target_hint 分派。
v2.8: 模式内 #41 放行断言组（16e）—— 短按成对直发实时目标（win/mac 双目标）;
     长按仍 MOUSE:TOGGLE（挂起/满阈值/UP 配对）; 替换 v2.6「吸收+提示」语义。
v2.9: presence 闸门断言组（18）—— stub 读端注入 unknown/online(漂移)/offline/恢复/
     无地址 五态; 断言「离线跳过 + 心跳 IP 优先 + 常量回退 + 降级照旧」。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 本地/Mac 与 T1 现网均可运行
import voice_fwd as v  # noqa: E402

v._pv = None   # v2.9: 测试环境显式退出 presence 闸门（无 state/presence.json 时
               #   device_state 恒 unknown 本也安全; 显式 None 防未来本机出现快照干扰）

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

    # 15. v2.5 鼠标模式（MouseMode 状态机）
    m0 = v.MouseMode()
    check("鼠标模式默认关", m0.on, False)
    check("模式关时 handle 空", m0.handle(103, 1, "mac", now=0.0), [])
    check("toggle 开", m0.toggle(), True)

    m = v.MouseMode()
    m.toggle()
    check("方向上 down", m.handle(103, 1, "mac", now=10.0), [("mac", "MOUSE:MOVE:UP", "down")])
    check("方向上 up 配对", m.handle(103, 0, "mac", now=10.2), [("mac", "MOUSE:MOVE:UP", "up")])
    r = [m.handle(c, 1, "mac", now=20.0)[0][1] for c in (108, 105, 106)]
    check("方向下/左/右映射", r, ["MOUSE:MOVE:DOWN", "MOUSE:MOVE:LEFT", "MOUSE:MOVE:RIGHT"])
    for c in (108, 105, 106):
        m.handle(c, 0, "mac", now=20.5)
    check("音量+ -> 滚动上", m.handle(115, 1, "mac", now=30.0), [("mac", "MOUSE:SCROLL:UP", "down")])
    check("音量- -> 滚动下", m.handle(114, 1, "mac", now=30.0), [("mac", "MOUSE:SCROLL:DOWN", "down")])
    check("滚动 up 配对", m.handle(115, 0, "mac", now=30.2), [("mac", "MOUSE:SCROLL:UP", "up")])
    check("滚动 down 配对", m.handle(114, 0, "mac", now=30.2), [("mac", "MOUSE:SCROLL:DOWN", "up")])

    check("OK down 不即时发", m.handle(28, 1, "mac", now=40.0), [])
    check("OK 短按(松开时发左键)", m.handle(28, 0, "mac", now=40.3), [("mac", "MOUSE:LCLICK", "down")])
    m.handle(28, 1, "mac", now=41.0)
    check("OK 长按未满阈值不发", m.tick(now=41.5), [])
    check("OK 长按满阈值发右键", m.tick(now=41.7), [("mac", "MOUSE:RCLICK", "down")])
    check("OK 长按只发一次", m.tick(now=42.0), [])
    check("长按后松开不补左键", m.handle(28, 0, "mac", now=42.2), [])

    check("返回键 -> MOUSE:OFF(本地)", m.handle(158, 1, "mac", now=50.0), [("", "MOUSE:OFF", "down")])
    check("返回键 up 无输出", m.handle(158, 0, "mac", now=50.2), [])
    check("菜单键忽略", m.handle(127, 1, "mac", now=51.0), [])
    check("主页键放行(v2.6: None)", m.handle(102, 1, "mac", now=51.1), None)
    check("电源键放行(v2.6: None)", m.handle(116, 1, "mac", now=51.2), None)

    # 保活补发（0.4s 节奏; tick 输出格式 (tgt, action, phase)）
    m.handle(106, 1, "mac", now=60.0)
    check("保活未到不发", m.tick(now=60.3), [])
    check("保活到点补发", m.tick(now=60.45), [("mac", "MOUSE:MOVE:RIGHT", "down")])
    check("保活节流内不发", m.tick(now=60.6), [])
    check("保活再过 0.4s 再发", m.tick(now=60.9), [("mac", "MOUSE:MOVE:RIGHT", "down")])
    m.handle(106, 0, "mac", now=61.0)
    check("松开后保活停", m.tick(now=61.5), [])

    # 配对纪律（DOWN 时目标快照, UP 回原目标）
    m.handle(103, 1, "win", now=70.0)
    check("快照 win, UP 回 win", m.handle(103, 0, "mac", now=70.2), [("win", "MOUSE:MOVE:UP", "up")])

    # 模式关时 tick 空; toggle 清状态
    m.toggle()
    check("toggle 关后 on=False", m.on, False)
    check("模式关时 tick 空", m.tick(now=80.0), [])
    check("toggle 清按住态", (m.moves, m.ok_down, m.ok_fired), ({}, False, False))

    # 现网 keymap: #41 long=MOUSE:TOGGLE（mac/win 对齐; atv 不变）
    live2 = v.load_cfg()
    check("现网 mac #41 long=MOUSE:TOGGLE",
          live2["targets"]["mac"]["keys"]["41"]["long"], "MOUSE:TOGGLE")
    check("现网 win #41 long=MOUSE:TOGGLE",
          live2["targets"]["win"]["keys"]["41"]["long"], "MOUSE:TOGGLE")
    check("现网 atv #41 保持 __LAUNCH__",
          live2["targets"]["atv"]["keys"]["41"]["single"], "__LAUNCH__:com.zentraedi.zspaceTV")
    check("现网 mac #41 single 不变(FOCUS_INPUT)",
          live2["targets"]["mac"]["keys"]["41"]["single"], "FOCUS_INPUT")

    # 16. v2.6 修复轮（用户首测反馈: TV键单按困惑 / 模式内电源主页无法跳走 / 无模式提示）
    # 16a. 放行键语义: 模式内电源/主页 -> None（调用方转 kf）; 模式外不受影响
    mP = v.MouseMode()
    check("模式关时电源不触发放行", mP.handle(116, 1, "mac", now=5000.0), [])
    mP.toggle()
    check("放行键集合", v.MOUSE_PASSTHROUGH_CODES, {116, 102})
    check("模式内电源 down 放行", mP.handle(116, 1, "mac", now=5001.0), None)
    check("模式内电源 up 放行", mP.handle(116, 0, "mac", now=5001.2), None)
    check("模式内主页 down 放行", mP.handle(102, 1, "mac", now=5002.0), None)
    check("模式内主页 up 放行", mP.handle(102, 0, "mac", now=5002.2), None)
    check("放行不污染按住态", (mP.moves, mP.ok_down), ({}, False))

    # 16b. main 路由语义还原: outs is None -> 转 kf 正常路径（含长按, 行为与模式外一致）
    kfP = v.KeyForwarder()
    kfP.set_cfg(CFG)
    mI = v.MouseMode()
    mI.toggle()

    def route(code, val, tgt, now):
        """还原 main(): mode.on 时先问 mode; None=放行 -> kf(target 用实时目标)"""
        o = mI.handle(code, val, tgt, now)
        return kfP.handle(code, val, tgt, now) if o is None else o

    check("模式内主页放行: down 不即时发(长按键)", route(102, 1, "mac", now=5100.0), [])
    check("模式内主页放行: 长按挂起", 102 in kfP.pending_long, True)
    check("模式内主页放行: 长按满阈值 -> APP:PICK",
          kfP.tick(now=5100.7), [("long", "mac", "APP:PICK", 102)])
    check("模式内主页放行: UP 配对", route(102, 0, "mac", now=5101.0), [("mac", "APP:PICK", "up")])
    check("模式内主页放行: 短按成对(新按)", (
        route(102, 1, "mac", now=5110.0) or route(102, 0, "mac", now=5110.3)),
        [("mac", "APP:CYCLE", "down"), ("mac", "APP:CYCLE", "up")])

    # 16c. send_mode_hint: 目标分派与报文格式（假 socket 捕获, 零网络）
    class _FakeSock:
        def __init__(self):
            self.sent = []

        def sendto(self, msg, addr):
            self.sent.append((msg, addr))

    fs = _FakeSock()
    check("MODE 提示 mac: 发出", v.send_mode_hint(fs, True, "mac"), True)
    check("MODE 提示 mac: 报文", fs.sent[-1][0], b"KEY MOUSE:MODE:ON DOWN")
    check("MODE 提示 mac: 端口", fs.sent[-1][1], (v.MAC_IP, v.MAC_KEY_PORT))
    check("MODE 提示 win: 发出", v.send_mode_hint(fs, False, "win"), True)
    check("MODE 提示 win: 报文", fs.sent[-1][0], b"KEY MOUSE:MODE:OFF DOWN")
    check("MODE 提示 win: 端口", fs.sent[-1][1], (v.WIN_IP, v.WIN_KEY_PORT))
    n0 = len(fs.sent)
    check("MODE 提示 atv: 不发", v.send_mode_hint(fs, True, "atv"), False)
    check("MODE 提示 atv: 无报文", len(fs.sent), n0)

    # 16d. 现网 keymap: 放行键在 mac/win 有实义动作（"跳走打开应用"依赖它）
    live3 = v.load_cfg()
    mk3 = live3["targets"]["mac"]["keys"]
    check("现网 mac 电源 single=TARGET:SWITCH(v2.7)", mk3.get("116", {}).get("single"), "TARGET:SWITCH")
    check("现网 mac 电源 long=APP:CLOSE", mk3.get("116", {}).get("long"), "APP:CLOSE")
    check("现网 mac 主页 single=APP:CYCLE", mk3.get("102", {}).get("single"), "APP:CYCLE")
    check("现网 mac 主页 long=APP:PICK", mk3.get("102", {}).get("long"), "APP:PICK")
    check("现网 win 电源=mac 同款", live3["targets"]["win"]["keys"].get("116"), mk3.get("116"))

    # 16e. v2.8 模式内 #41 放行（短按=聚焦输入框直发实时目标; 长按仍=MOUSE:TOGGLE 关模式）
    live4 = v.load_cfg()
    kfE = v.KeyForwarder()
    kfE.set_cfg(live4)
    mE = v.MouseMode()
    mE.toggle()                                    # 模式开（复刻 main: 模式内 #41 不拦截）

    def route41(val, tgt, now):
        """复刻 main() v2.8: 模式内 #41 不进 mode.handle, 直接喂 kf(实时目标)"""
        return kfE.handle(41, val, tgt, now)

    check("模式内 #41 短按成对 -> win FOCUS_INPUT",
          (route41(1, "win", now=5400.0) or route41(0, "win", now=5400.3)),
          [("win", "FOCUS_INPUT", "down"), ("win", "FOCUS_INPUT", "up")])
    check("模式内 #41 短按成对 -> mac FOCUS_INPUT",
          (route41(1, "mac", now=5401.0) or route41(0, "mac", now=5401.3)),
          [("mac", "FOCUS_INPUT", "down"), ("mac", "FOCUS_INPUT", "up")])
    check("模式内 #41 长按挂起", route41(1, "mac", now=5402.0), [])
    check("模式内 #41 长按满阈值 -> MOUSE:TOGGLE",
          kfE.tick(now=5402.7), [("long", "mac", "MOUSE:TOGGLE", 41)])
    check("模式内 #41 长按 UP 配对", route41(0, "mac", now=5403.0), [("mac", "MOUSE:TOGGLE", "up")])

    # 17. v2.7 电源连击切换（TargetSwitcher 状态机）
    check("连击: 常量", (v.TARGET_SWITCH_ACTION, v.TARGET_SWITCH_WINDOW, v.TARGET_SWITCH_MAX, v.TARGET_ORDER),
          ("TARGET:SWITCH", 0.5, 3, ("atv", "mac", "win")))
    check("连击: 电源键码", v.POWER_KEY_CODE, 116)

    # 17a. 单击: DOWN/UP 不即时; 窗口期满提交 1
    ts = v.TargetSwitcher()
    check("连击 单击 down 无输出", ts.handle(116, 1, 100.0, "mac"), [])
    check("连击 单击 up 无输出(未到期)", ts.handle(116, 0, 100.1, "mac"), [])
    check("连击 窗口未满 tick 不提交", ts.tick(100.4, 0.6), [])
    check("连击 期满提交=1", ts.tick(100.55, 0.6), [("commit", 1)])

    # 17b. 双击(快): 第 2 击刷新窗口; 期满提交 2
    ts = v.TargetSwitcher()
    ts.handle(116, 1, 200.0, "mac")
    ts.handle(116, 0, 200.1, "mac")
    check("连击 二击 down 无输出", ts.handle(116, 1, 200.2, "mac"), [])
    check("连击 二击 up 无输出", ts.handle(116, 0, 200.3, "mac"), [])
    check("连击 二击窗口未满不提交", ts.tick(200.6, 0.6), [])
    check("连击 二击期满提交=2", ts.tick(200.75, 0.6), [("commit", 2)])

    # 17c. 三击: 第 3 击按下立即提交 3（免等窗口）
    ts = v.TargetSwitcher()
    ts.handle(116, 1, 300.0, "mac")
    ts.handle(116, 0, 300.05, "mac")
    ts.handle(116, 1, 300.1, "mac")
    ts.handle(116, 0, 300.15, "mac")
    check("连击 三击立即提交=3", ts.handle(116, 1, 300.2, "mac"), [("commit", 3)])

    # 17d. 提交后吞键期: 跟随的第 4 击被吞（连敲续期 = 整串吞完）
    check("连击 吞键期三击UP(吞)", ts.handle(116, 0, 300.25, "mac"), [])
    check("连击 吞键期第4击 down(吞)", ts.handle(116, 1, 300.4, "mac"), [])
    check("连击 吞键期第4击 up(吞)", ts.handle(116, 0, 300.5, "mac"), [])
    check("连击 吞键期 tick 空", ts.tick(300.55, 0.6), [])
    check("连击 吞键期过期后新序列可用", ts.handle(116, 1, 301.1, "mac"), [])
    check("连击 新序列 up", ts.handle(116, 0, 301.2, "mac"), [])
    check("连击 新序列提交=1", ts.tick(301.65, 0.6), [("commit", 1)])

    # 17e. 长按: 满阈值中止计数 -> long（含 DOWN 时目标快照）; UP 收尾 long_end
    ts = v.TargetSwitcher()
    check("连击 长按 down", ts.handle(116, 1, 400.0, "win"), [])
    check("连击 长按未满阈值不触发", ts.tick(400.5, 0.6), [])
    check("连击 长按满阈值 -> long(win)", ts.tick(400.65, 0.6), [("long", "win")])
    check("连击 长按只触发一次", ts.tick(401.0, 0.6), [])
    check("连击 长按 UP -> long_end", ts.handle(116, 0, 401.2, "win"), [("long_end", None)])
    check("连击 长按计数已清零", ts.count, 0)

    # 17f. 窗口期满但按住（deadline<按住<阈值 之间松开）: 松开即成
    ts = v.TargetSwitcher()
    ts.handle(116, 1, 500.0, "mac")
    check("连击 按住中 tick 不提交(defer)", ts.tick(500.55, 0.6), [])
    check("连击 慢松(未满阈值)松开即提交=1", ts.handle(116, 0, 500.58, "mac"), [("commit", 1)])

    # 17g. 长按优先于提交: 按住跨过窗口与阈值 -> long, 绝不提交
    ts = v.TargetSwitcher()
    ts.handle(116, 1, 600.0, "mac")
    check("连击 跨窗口长按=long", ts.tick(600.61, 0.6), [("long", "mac")])
    check("连击 长按后窗口不提交", ts.tick(601.2, 0.6), [])
    ts.handle(116, 0, 601.3, "mac")

    # 17h. val==2 忽略 / 非 116 忽略 / reset 清会话
    ts = v.TargetSwitcher()
    check("连击 val2 忽略", ts.handle(116, 2, 700.0, "mac"), [])
    check("连击 非116忽略", ts.handle(102, 1, 700.0, "mac"), [])
    ts.handle(116, 1, 700.1, "mac")
    ts.reset()
    check("连击 reset 清会话", ts.tick(700.7, 0.6), [])

    # 17i. 自定义窗口（离线参数化）
    ts2 = v.TargetSwitcher(window=0.3)
    check("连击 自定义窗口: up 未到期不提交", (ts2.handle(116, 1, 800.0, "mac"),
                                              ts2.handle(116, 0, 800.2, "mac")), ([], []))
    check("连击 自定义窗口: 期满 tick 提交", ts2.tick(800.35, 0.6), [("commit", 1)])

    # 17j. send_target_hint: 分派规则与报文（假 socket 捕获, 零网络）
    fs2 = _FakeSock()
    check("HUD 切到 atv -> 发旧目标(mac)", v.send_target_hint(fs2, "atv", "mac"), True)
    check("HUD 报文(atv)", fs2.sent[-1][0], b"KEY TARGET:SWITCH:ATV DOWN")
    check("HUD 端口(mac)", fs2.sent[-1][1], (v.MAC_IP, v.MAC_KEY_PORT))
    check("HUD 切到 win -> 发新目标(win)", v.send_target_hint(fs2, "win", "mac"), True)
    check("HUD 报文(win)", fs2.sent[-1][0], b"KEY TARGET:SWITCH:WIN DOWN")
    check("HUD 切到 mac(同目标也发确认)", v.send_target_hint(fs2, "mac", "win"), True)
    check("HUD 报文(mac)", fs2.sent[-1][0], b"KEY TARGET:SWITCH:MAC DOWN")
    n1 = len(fs2.sent)
    check("HUD 无旧目标(atv->atv)不发", v.send_target_hint(fs2, "atv", "atv"), False)
    check("HUD 无旧目标: 无报文", len(fs2.sent), n1)

    # 17k. 现网 keymap 网关（三份均就位 —— voice_fwd 用 mac/win, relay 用 atv）
    live4 = v.load_cfg()
    for t in ("atv", "mac", "win"):
        check(f"现网 {t} 电源 single=TARGET:SWITCH",
              live4["targets"][t]["keys"].get("116", {}).get("single"), "TARGET:SWITCH")

    # 18. v2.9 presence 投递闸门（stub 读端注入多态; 零网络）
    class _StubPV:
        def __init__(self, table):
            self.table = table            # role -> (state, ip)

        def device_state(self, role):
            return self.table.get(role, ("unknown", None))[0]

        def ip_of(self, role):
            return self.table.get(role, ("unknown", None))[1]

    def _with_pv(table):
        v._pv = _StubPV(table)
        v._pv_offline.clear()
        v._pv_noaddr_t.clear()
        return _FakeSock()

    # 18a. 降级: unknown（守护未就绪/过期）-> 照旧投递 + 地址回退常量
    fs3 = _with_pv({})
    check("闸门 unknown: 照旧投递", v.send_voice(fs3, True, "mac"), True)
    check("闸门 unknown: 地址回退常量", fs3.sent[-1][1], (v.MAC_IP, v.MAC_PORT))

    # 18b. online + 心跳学到新 IP -> 发到新 IP（去硬编码核心）
    fs3 = _with_pv({"mac": ("online", "LAN_IP"), "win": ("online", "LAN_IP")})
    check("闸门 online 漂移: VOICE -> 心跳 IP",
          (v.send_voice(fs3, True, "mac"), fs3.sent[-1][1]), (True, ("LAN_IP", v.MAC_PORT)))
    check("闸门 online 漂移: KEY -> 心跳 IP",
          (v.send_key(fs3, "win", "ENTER", "down"), fs3.sent[-1][1]),
          (True, ("LAN_IP", v.WIN_KEY_PORT)))

    # 18c. offline -> 跳过 + 零报文（体面断开核心）
    fs3 = _with_pv({"mac": ("offline", "LAN_IP")})
    n2 = len(fs3.sent)
    check("闸门 offline: VOICE 跳过", v.send_voice(fs3, True, "mac"), False)
    check("闸门 offline: KEY 跳过", v.send_key(fs3, "mac", "ENTER", "down"), False)
    check("闸门 offline: 零报文", len(fs3.sent), n2)

    # 18d. 离线->恢复: 同一 stub 翻转状态 -> 恢复投递（边沿: _pv_offline 已含 mac）
    v._pv.table["mac"] = ("online", "LAN_IP")
    fs3b = _FakeSock()
    check("闸门 恢复: 继续投递", v.send_key(fs3b, "mac", "ENTER", "down"), True)
    check("闸门 恢复: 报文落新 IP", fs3b.sent[-1][1], ("LAN_IP", v.MAC_KEY_PORT))

    # 18e. 无地址: 常量空 + 无心跳 IP -> 丢弃（节流日志; 地址双保险皆空）
    _mac_bak = v.MAC_IP
    v.MAC_IP = ""
    fs3c = _with_pv({"mac": ("online", None)})
    n3 = len(fs3c.sent)
    check("闸门 无地址: 丢弃", v.send_key(fs3c, "mac", "ENTER", "down"), False)
    check("闸门 无地址: 零报文", len(fs3c.sent), n3)
    v.MAC_IP = _mac_bak

    # 收尾: 恢复测试环境（闸门退出, 防后段/复跑受影响）
    v._pv = None
    v._pv_offline.clear()
    v._pv_noaddr_t.clear()

    print(f"\n== 结果: {ok[0]} PASS / {fail[0]} FAIL ==")
    return 0 if fail[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
