#!/usr/bin/env python3
# mouse_channel_test.py — remotehub_focus.lua v1.4 鼠标通道实机冒烟（Mac 本地）
#
# 覆盖: ① 模块可用/mouseStatus ② 右移真实位移 ③ 停止即停 + 定时器关闭
#       ④ 看门狗（对向抵消=零净位移, 1.2s 无刷新自动停） ⑤ 归位还原
#       ⑥ v1.3 mouseHud 模式提示（on/off 应答; 会弹浮层+提示音） ⑦ v1.3 回归
#       ⑧ v1.4 switchHud 设备切换提示（含 key_bridge _mouse_cmd 映射离线校验）
# 运行: python3 mouse_channel_test.py   （会短暂移动光标并还原）
import os
import re
import subprocess
import sys
import time

HS = "/opt/homebrew/bin/hs"
LOAD = 'dofile(os.getenv("HOME").."/.hammerspoon/remotehub_focus.lua")'

pass_n = fail_n = 0


def check(name, cond, detail=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  [PASS] {name} {detail}")
    else:
        fail_n += 1
        print(f"  [FAIL] {name} {detail}")


def hs(code, timeout=10):
    r = subprocess.run([HS, "-c", code], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "").strip().splitlines()
    err = (r.stderr or "").strip().splitlines()
    return (out[-1] if out else (err[0] if err else "")), r.returncode


def call(expr):
    """调 remotehub_focus 模块函数（单表达式）"""
    return hs(f"return {LOAD}.{expr}")


def status():
    s, _ = call("mouseStatus()")
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+) v=(-?[\d.]+) move=\[([^\]]*)\]", s)
    if not m:
        return None
    return {"x": float(m.group(1)), "y": float(m.group(2)), "raw": s}


print("== 0. 基线 ==")
st0 = status()
check("模块可用（mouseStatus）", st0 is not None, st0["raw"] if st0 else "(无输出)")
if not st0:
    print("FAIL: Hammerspoon/hs 通道不可用, 终止")
    sys.exit(1)
x0, y0 = st0["x"], st0["y"]

print("== 0b. key_bridge _mouse_cmd 映射（v1.15 TARGET:SWITCH, 纯离线） ==")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import key_bridge as kb  # noqa: E402

m1 = kb._mouse_cmd("TARGET:SWITCH:ATV", "DOWN")
check("映射 switchHud atv", m1 == 'switchHud("atv")', repr(m1))
m2 = kb._mouse_cmd("TARGET:SWITCH:WIN", "DOWN")
check("映射 switchHud win", m2 == 'switchHud("win")', repr(m2))
m3 = kb._mouse_cmd("TARGET:SWITCH:MAC", "UP")
check("映射 switchHud UP 忽略", m3 is None, repr(m3))
m4 = kb._mouse_cmd("TARGET:SWITCH:BOGUS", "DOWN")
check("映射 非法目标忽略", m4 is None, repr(m4))
m5 = kb._mouse_cmd("TARGET:SWITCHX", "DOWN")
check("映射 缺冒号前缀不误判", m5 is None, repr(m5))
m6 = kb._mouse_cmd("MOUSE:MODE:ON", "DOWN")
check("映射 MOUSE 既有无回归", m6 == 'mouseHud("on")', repr(m6))
check("映射 版本=v1.15", kb.VERSION == "1.15", kb.VERSION)

print("== 1. 右移 0.3s -> 停止 ==")
r, _ = call("mouseStart('right')")
check("mouseStart 应答", r.startswith("OK"), r)
time.sleep(0.3)
r, _ = call("mouseStop('right')")
check("mouseStop 应答", r.startswith("OK"), r)
st1 = status()
check("光标向右位移 >20px", st1["x"] > x0 + 20, f"dx={st1['x'] - x0:.0f}px")
check("停止后定时器关闭", "timer=off" in st1["raw"], st1["raw"])

print("== 2. 看门狗（对向抵消零位移 + 1.2s 无刷新自动停） ==")
code = (f'local M={LOAD}; M.mouseStart("left"); M.mouseStart("right"); '
        'return "OK both"')
r, _ = hs(code)
check("双方向同时启动", r.startswith("OK"), r)
time.sleep(1.5)
st2 = status()
check("超时自动停（timer=off）", "timer=off" in st2["raw"], st2["raw"])
check("对向抵消无净位移 <6px", abs(st2["x"] - st1["x"]) < 6, f"dx={st2['x'] - st1['x']:.0f}px")

print("== 3. 归位 ==")
hs(f"hs.mouse.absolutePosition({{x={x0}, y={y0}}})")
time.sleep(0.1)
st3 = status()
ok_pos = st3 and abs(st3["x"] - x0) < 2 and abs(st3["y"] - y0) < 2
check("位置已还原", bool(ok_pos), f"({st3['x']:.0f},{st3['y']:.0f}) vs 原({x0:.0f},{y0:.0f})")

print("== 4. v1.3 mouseHud 模式提示（会弹浮层+提示音） ==")
r, _ = call('mouseHud("on")')
check("mouseHud on 应答", r.startswith("OK hud on"), r)
time.sleep(0.3)
r, _ = call('mouseHud("off")')
check("mouseHud off 应答", r.startswith("OK hud off"), r)
time.sleep(1.2)   # 等浮层自然消失, 收尾干净
st4 = status()
check("HUD 不影响执行器（timer 仍 off）", "timer=off" in st4["raw"], st4["raw"])

print("== 5. v1.4 switchHud 设备切换提示（会弹浮层+提示音） ==")
r, _ = call('switchHud("atv")')
check("switchHud atv 应答", r.startswith("OK hud switch:atv"), r)
time.sleep(0.3)
r, _ = call('switchHud("mac")')
check("switchHud mac 应答", r.startswith("OK hud switch:mac"), r)
time.sleep(0.3)
r, _ = call('switchHud("win")')
check("switchHud win 应答", r.startswith("OK hud switch:win"), r)
time.sleep(0.3)
r, _ = call('switchHud("bogus")')
check("switchHud 未知名回显（不炸）", r.startswith("OK hud switch:bogus"), r)
time.sleep(1.2)   # 等浮层自然消失
st5 = status()
check("切换 HUD 不影响执行器（timer 仍 off）", "timer=off" in st5["raw"], st5["raw"])

print(f"\nmouse_channel_test: {pass_n} PASS / {fail_n} FAIL")
sys.exit(0 if fail_n == 0 else 1)
