#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""receiver_smoke_test.py — win_receiver.py v1.5 语音链时序冒烟测试（macOS/Linux 可跑）
==================================================================================
打桩法：sys.modules 注入假 win_actions / win_audio_switch（记录调用），exec 加载
win_receiver.py（__file__ 指向临时目录, 不污染真实 receiver.log），再替换 send_vk / log。
不触达任何平台 API；验证 v1.3 麦克风切换的**调用时序**（本测不覆盖 win_audio_switch
内部逻辑——那由 audio_switch_offline_test.py 覆盖）。
覆盖:
  1) VOICE down：先 switch_to_virtual 再注入 Ctrl+Win（顺序断言）
  2) 重复 down：ignored 不重复动作
  3) VOICE up：逆序释放 + schedule_restore 调度
  4) up 无 held：ignored
  5) watchdog 超时释放：同样 schedule_restore
  6) watchdog 未超时：不动作
  7) win_audio_switch 缺失：fail-open 仍注入（链路不受影响）
  8) 键盘动作不受影响（ENTER / PAGEUP extended）
  9) 扩展动作仍入队（CLICK）
 10) picker 直连路由（v1.4：被路由的键不注入 + routed 日志；未路由照常注入）
 11) 扩展动作值大小写保真（v1.5：URL/RUN 原值入队 + 同串防抖 + up 相位忽略）
 12) 防抖首击低时钟语义（v1.6：单调时钟从 0 起时首击不误拦；同刻重复仍防抖）
用法：python3 receiver_smoke_test.py
"""
import os
import shutil
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="wr_smoke_")

calls = []
logs = []


class FakeWAS(object):
    VERSION = "fake"
    RESTORE_DELAY = 2.0

    def init(self, log_fn):
        pass

    def switch_to_virtual(self):
        calls.append("switch")
        return (True, "switched -> CABLE Output")

    def schedule_restore(self, delay=None):
        calls.append(("sched", delay))
        return 1


fake_was = FakeWAS()
fake_wa = types.ModuleType("win_actions")
fake_wa.VERSION = "fake"
fake_wa.is_ext_action = lambda a: a == "CLICK"
fake_wa.debounce_for = lambda a: 0.6
fake_wa.picker_route = lambda a, p: False

sys.modules["win_audio_switch"] = fake_was
sys.modules["win_actions"] = fake_wa

src = open(os.path.join(HERE, "win_receiver.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(TMP, "win_receiver.py"), "__name__": "win_receiver_smoke"}
exec(compile(src, "win_receiver.py", "exec"), ns)


def fake_send_vk(vk, up=False, extended=False):
    calls.append(("vk", hex(vk), "up" if up else "down", extended))
    return True


ns["send_vk"] = fake_send_vk
ns["log"] = lambda msg, also_console=False: logs.append(msg)

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, "| got =", repr(got), "| want =", repr(want))


hv = ns["handle_voice"]
hk = ns["handle_key"]

print("== 1) VOICE down: 先切设备后注入 ==")
calls.clear()
logs.clear()
hv("VOICE down")
check("调用序列 = switch → Ctrl down → Win down", calls, [
    "switch", ("vk", "0x11", "down", False), ("vk", "0x5b", "down", False)])

print("== 2) 重复 down ignored ==")
calls.clear()
logs.clear()
hv("VOICE down")
check("无新动作", calls, [])
check("有 already held 日志", any("already held" in m for m in logs), True)

print("== 3) VOICE up: 逆序释放 + 调度切回 ==")
calls.clear()
logs.clear()
hv("VOICE up")
check("释放逆序 + sched", calls, [
    ("vk", "0x5b", "up", False), ("vk", "0x11", "up", False), ("sched", None)])

print("== 4) up 无 held ignored ==")
calls.clear()
hv("VOICE up")
check("无动作", calls, [])

print("== 5) watchdog 超时释放 + 调度 ==")
calls.clear()
hv("VOICE down")
calls.clear()
did = ns["check_voice_hold"](now=ns["_voice_down_at"] + 61.0)
check("触发释放", did, True)
check("释放后同样 sched", calls, [
    ("vk", "0x5b", "up", False), ("vk", "0x11", "up", False), ("sched", None)])

print("== 6) watchdog 未超时不动作 ==")
calls.clear()
hv("VOICE down")
calls.clear()
did = ns["check_voice_hold"](now=time.monotonic() + 1.0)
check("未触发", did, False)
check("无动作", calls, [])
hv("VOICE up")
calls.clear()

print("== 7) win_audio_switch 缺失: fail-open 仍注入 ==")
ns["win_audio_switch"] = None
logs.clear()
hv("VOICE down")
check("仍注入 Ctrl+Win", calls, [
    ("vk", "0x11", "down", False), ("vk", "0x5b", "down", False)])
check("有 module NOT loaded 日志", any("module NOT loaded" in m for m in logs), True)
calls.clear()
hv("VOICE up")
check("缺失时 up 不崩、无 sched", calls, [
    ("vk", "0x5b", "up", False), ("vk", "0x11", "up", False)])
calls.clear()
ns["win_audio_switch"] = fake_was

print("== 8) 键盘动作不受影响 ==")
calls.clear()
hk("KEY ENTER DOWN")
check("ENTER down", calls, [("vk", "0xd", "down", False)])
calls.clear()
hk("KEY PAGEUP DOWN")
check("PAGEUP extended", calls, [("vk", "0x21", "down", True)])

print("== 9) 扩展动作仍入队 ==")
calls.clear()
hk("KEY CLICK DOWN")
got = None
try:
    got = ns["_action_q"].get_nowait()
except Exception:
    pass
check("CLICK 入队", got, "CLICK")
hk("KEY CLICK UP")
check("ext up ignored(无异常)", True, True)

print("== 10) picker 直连路由（v1.4）==")
calls.clear()
logs.clear()
fake_wa.picker_route = lambda a, p: a in ("UP", "DOWN", "ENTER", "ESC", "BACKSPACE")
hk("KEY UP DOWN")
check("UP 被路由: 不注入", calls, [])
check("有 routed 日志", any("picker" in m for m in logs), True)
hk("KEY ENTER DOWN")
check("ENTER 也不注入", calls, [])
hk("KEY ENTER UP")
check("up 相位同样被消化", calls, [])
fake_wa.picker_route = lambda a, p: False
calls.clear()
hk("KEY SPACE DOWN")
check("未路由照常注入", calls, [("vk", "0x20", "down", False)])

print("== 11) 扩展动作值大小写保真（v1.5: URL/RUN 原值入队）==")
fake_wa.is_ext_action = lambda a: a == "CLICK" or a.startswith(("APP:", "URL:", "RUN:"))


def _drain():
    try:
        return ns["_action_q"].get_nowait()
    except Exception:
        return None


hk("KEY URL:https://Example.COM/Path?q=Aa DOWN")
check("URL 原值入队（大小写保真）", _drain(), "URL:https://Example.COM/Path?q=Aa")
hk("KEY URL:https://Example.COM/Path?q=Aa DOWN")      # 0.6s 内同串重复
check("同串 0.6s 内防抖丢弃", _drain(), None)
hk("KEY URL:https://Example.COM/Path?q=Aa UP")
check("up 相位不产任务", ns["_action_q"].empty(), True)
hk("KEY RUN:MyScript.CMD DOWN")
check("RUN 原值入队（大小写保真）", _drain(), "RUN:MyScript.CMD")
logs.clear()
hk("KEY RUN:MyScript.CMD UP")
check("up 相位有 ignored 日志", any("ignored" in m for m in logs), True)

fake_wa.is_ext_action = lambda a: a == "CLICK"

print("== 12) 防抖首击：低单调时钟不误拦（v1.6）==")
_real_time = ns["time"]
ns["time"] = types.SimpleNamespace(monotonic=lambda: 0.10, time=lambda: 0.10)
ns["_ext_last"].clear()
fake_wa.is_ext_action = lambda a: a in ("CLICK", "FOCUS_INPUT") or a.startswith(("APP:", "URL:", "RUN:"))
hk("KEY FOCUS_INPUT DOWN")
check("低时钟首击入队（哨兵修复）", _drain(), "FOCUS_INPUT")
hk("KEY FOCUS_INPUT DOWN")
check("低时钟同刻重复仍防抖", _drain(), None)
ns["time"] = _real_time
fake_wa.is_ext_action = lambda a: a == "CLICK"

print("")
print("== 结果: %d PASS / %d FAIL ==" % (PASS, FAIL))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
