#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audio_switch_offline_test.py — win_audio_switch.py 离线逻辑测试（macOS/Linux 可跑）
================================================================================
打桩法：exec 加载源码到独立命名空间，替换 IS_WIN / list_capture / get_default_capture /
set_default_capture 为假实现，STATE_DIR 隔离到临时目录；find_virtual 与全部状态机逻辑
跑真实代码；「延迟切回」调度用真实 threading.Timer（测试用短延迟）。
覆盖:
  1) find_virtual 匹配（大小写 / 多设备 / 负例）
  2) switch_to_virtual 状态机（正常 / 幂等 / 无设备 / 无虚拟 / set 失败 / 初始即虚拟）
  3) restore_original（正常 / 无会话 / 已恢复 / set 失败 / 内存丢失从 state 恢复）
  4) recover_if_needed 崩溃自愈（残留 / 无残留 / 设备消失 / 无记录 / 已在原设备 / set 失败）
  5) schedule_restore / cancel_pending_restore（到点执行 / 取消 / 连按作废 / supersede /
     慢 set 竞态：timer 执行中新会话开始 → 净结果正确）
  6) 状态文件读写与防御（roundtrip / 损坏 / 路径）
  7) status() 诊断输出（计数 / [VIRTUAL] / [DEFAULT] 标记）
  8) 非 Windows 短路与 _device_name 退化 / init 日志容错
用法：python3 audio_switch_offline_test.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "win_audio_switch.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(HERE, "win_audio_switch.py"), "__name__": "was_test"}
exec(compile(src, "win_audio_switch.py", "exec"), ns)

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


# ---------------------------------------------------------------- 打桩环境
TMP = tempfile.mkdtemp(prefix="was_test_")
ns["STATE_DIR"] = TMP
ns["IS_WIN"] = True

CABLE = ("cable-1", "CABLE Output (VB-Audio Virtual Cable)")
MIC = ("mic-1", "麦克风阵列 (Realtek Audio)")


class FakeAudio:
    devices = [MIC, CABLE]
    default = "mic-1"
    set_calls = []
    set_result = True
    set_delay = 0.0
    list_calls = 0


FAKE = FakeAudio()


def fake_list():
    FAKE.list_calls += 1
    return list(FAKE.devices)


def fake_get_default():
    return FAKE.default


def fake_set(did):
    FAKE.set_calls.append(did)
    if FAKE.set_delay:
        time.sleep(FAKE.set_delay)
    if FAKE.set_result:
        FAKE.default = did
        return True
    return False


ns["list_capture"] = fake_list
ns["get_default_capture"] = fake_get_default
ns["set_default_capture"] = fake_set
# find_virtual 保持真实（纯逻辑，应被测试）


def reset_env(devices=None, default="mic-1"):
    FAKE.devices = list(devices) if devices is not None else [MIC, CABLE]
    FAKE.default = default
    FAKE.set_calls = []
    FAKE.set_result = True
    FAKE.set_delay = 0.0
    FAKE.list_calls = 0
    ns["_rt_original"]["id"] = None
    ns["_cancel_restore_locked"]()          # 作废一切待调度（防串测）
    st = os.path.join(TMP, "audio_switch.json")
    if os.path.exists(st):
        os.remove(st)


print("== 0) 常量 ==")
check("VIRTUAL_MATCH", ns["VIRTUAL_MATCH"], "cable output")
check("VERSION v1.2", ns["VERSION"], "1.2")
check("RESTORE_DELAY 默认 2s", ns["RESTORE_DELAY"], 2.0)

# ---------------------------------------------------------------- 1) find_virtual
print("== 1) find_virtual 匹配 ==")
fv = ns["find_virtual"]
check("CABLE Output 命中", fv([("a", "麦克风"), CABLE]), CABLE)
check("大小写不敏感", fv([("b", "cable OUTPUT (x)")])[0], "b")
check("VoiceMeeter 不误配", fv([("v", "VoiceMeeter Output (VB-Audio VoiceMeeter)")]), (None, None))
check("CABLE Input 不命中", fv([("i", "CABLE Input (VB-Audio Virtual Cable)")]), (None, None))
check("空列表", fv([]), (None, None))
check("多候选取首个", fv([("1", "X CABLE Output"), ("2", "Y cable output")])[0], "1")

# ---------------------------------------------------------------- 2) switch_to_virtual
print("== 2) switch_to_virtual 状态机 ==")
sw = ns["switch_to_virtual"]

reset_env()
ok, det = sw()
check("正常切换 ok", ok, True)
check("正常切换 detail", det, "switched -> CABLE Output (VB-Audio Virtual Cable)")
check("默认已切到 cable", FAKE.default, "cable-1")
check("set 调用一次", FAKE.set_calls, ["cable-1"])
check("内存记忆 = mic-1", ns["_rt_original"]["id"], "mic-1")
st = ns["_load_state"]()
check("state phase=switched", st.get("phase"), "switched")
check("state original=mic-1", st.get("original"), "mic-1")

ok, det = sw()
check("幂等 already-virtual", (ok, det), (True, "already-virtual"))
check("幂等不再 set", FAKE.set_calls, ["cable-1"])

reset_env(devices=[])
check("无录音设备", sw(), (False, "no-capture-devices"))

reset_env(devices=[MIC])
check("无虚拟设备", sw(), (False, "virtual-not-found (match='cable output')"))

reset_env()
FAKE.set_result = False
ok, det = sw()
check("set 失败返回", (ok, det), (False, "set-default-failed"))
check("set 失败仍留自愈记录", ns["_load_state"]().get("phase"), "switched")
check("set 失败默认未变", FAKE.default, "mic-1")

reset_env(default="cable-1")
ok, det = sw()
check("初始即虚拟", (ok, det), (True, "already-virtual"))
check("初始即虚拟不 set", FAKE.set_calls, [])
check("初始即虚拟 记录=当前(保守)", ns["_rt_original"]["id"], "cable-1")

# ---------------------------------------------------------------- 3) restore_original
print("== 3) restore_original ==")
ro = ns["restore_original"]

reset_env()
sw()
ok, det = ro()
check("恢复 ok", (ok, det), (True, "restored"))
check("默认切回 mic-1", FAKE.default, "mic-1")
check("恢复后清记忆", ns["_rt_original"]["id"], None)
check("恢复后 state idle", ns["_load_state"]().get("phase"), "idle")

reset_env()
check("无会话 no-op", ro(), (False, "no-session"))

reset_env()
ns["_rt_original"]["id"] = "mic-1"
ok, det = ro()
check("已在原设备", (ok, det), (True, "already-original"))
check("已在原设备不 set", FAKE.set_calls, [])

reset_env()
sw()
FAKE.set_result = False
ok, det = ro()
check("恢复 set 失败", (ok, det), (False, "restore-set-failed"))
check("失败保留记忆(可重试)", ns["_rt_original"]["id"], "mic-1")
check("失败 state 仍 switched", ns["_load_state"]().get("phase"), "switched")

reset_env()
sw()
ns["_rt_original"]["id"] = None                 # 模拟内存丢失（进程重启）
ok, det = ro()
check("内存丢失从 state 恢复", (ok, det), (True, "restored"))

# ---------------------------------------------------------------- 4) recover_if_needed
print("== 4) recover_if_needed 崩溃自愈 ==")
rec = ns["recover_if_needed"]

reset_env()
check("无残留", rec(), (False, "no-recovery-needed"))

reset_env()
sw()
ns["_rt_original"]["id"] = None                 # 模拟进程重启
ok, det = rec()
check("残留恢复", (ok, det), (True, "recovered -> original"))
check("恢复后默认=mic-1", FAKE.default, "mic-1")
check("恢复后 state idle", ns["_load_state"]().get("phase"), "idle")

reset_env()
ns["_save_state"]({"phase": "switched", "original": None})
check("无 original 记录", rec(), (False, "no-original-recorded"))
check("无 original 清理 state", ns["_load_state"]().get("phase"), "idle")

reset_env()
ns["_save_state"]({"phase": "switched", "original": "gone-dev"})
FAKE.default = "cable-1"
ok, det = rec()
check("原设备消失 ok=False", ok, False)
check("原设备消失 detail 前缀", det.startswith("original-device-gone"), True)
check("设备消失清理 state", ns["_load_state"]().get("phase"), "idle")

reset_env()                                      # default=mic-1
ns["_save_state"]({"phase": "switched", "original": "mic-1"})
ok, det = rec()
check("已在原设备 cleanup", (ok, det), (True, "already-original (cleanup)"))
check("已在原设备不 set", FAKE.set_calls, [])

reset_env()
ns["_save_state"]({"phase": "switched", "original": "mic-1"})
FAKE.default = "cable-1"
FAKE.set_result = False
ok, det = rec()
check("自愈 set 失败", (ok, det), (False, "recover-set-failed"))
check("自愈失败保留 state(下次再试)", ns["_load_state"]().get("phase"), "switched")

# ---------------------------------------------------------------- 5) 调度
print("== 5) schedule_restore / cancel_pending_restore ==")
sched = ns["schedule_restore"]
cancel = ns["cancel_pending_restore"]

reset_env()
sw()
sched(0.05)
time.sleep(0.30)
check("定时到点切回", FAKE.default, "mic-1")
check("定时后 state idle", ns["_load_state"]().get("phase"), "idle")

reset_env()
sw()
sched(0.15)
sw()                                             # 连按：switch 自动取消
time.sleep(0.40)
check("连按取消: 仍在 cable", FAKE.default, "cable-1")

reset_env()
sw()
sched(0.15)
cancel()
time.sleep(0.40)
check("手动取消", FAKE.default, "cable-1")

reset_env()
sw()
sched(0.50)
sched(0.05)                                      # supersede：新调度覆盖旧
time.sleep(0.30)
check("新调度生效", FAKE.default, "mic-1")
time.sleep(0.45)                                 # 旧调度(0.5s)已过点，应 skip
check("stale 不二次动作", FAKE.set_calls.count("mic-1"), 1)

reset_env()
sw()                                             # cable
FAKE.set_delay = 0.25
sched(0.05)                                      # timer 到点 → 持锁慢 set(mic-1)
time.sleep(0.10)                                 # 此刻 timer 正在执行
sw()                                             # 新会话：等锁 → 随后重切 cable
FAKE.set_delay = 0.0
time.sleep(0.35)
check("慢 set 竞态: 净结果=cable", FAKE.default, "cable-1")
check("慢 set 竞态: 记忆=mic-1", ns["_rt_original"]["id"], "mic-1")
ok, det = ro()                                   # 收尾恢复
check("竞态收尾恢复", (ok, det), (True, "restored"))

# ---------------------------------------------------------------- 6) 状态文件
print("== 6) 状态文件读写与防御 ==")
reset_env()
ns["_save_state"]({"phase": "x", "n": 1})
check("state roundtrip", ns["_load_state"]()["phase"], "x")
with open(os.path.join(TMP, "audio_switch.json"), "w", encoding="utf-8") as f:
    f.write("{broken")
check("损坏 state -> {}", ns["_load_state"](), {})
check("state 路径", ns["_state_path"](), os.path.join(TMP, "audio_switch.json"))

# ---------------------------------------------------------------- 7) status
print("== 7) status() 诊断输出 ==")
reset_env()
out = ns["status"]()
check("含设备计数", "capture devices (2):" in out, True)
check("标 [VIRTUAL]", "[VIRTUAL]" in out, True)
check("标 [DEFAULT]", "[DEFAULT]" in out, True)
check("含 virtual match 行", "virtual match 'cable output':" in out, True)

# ---------------------------------------------------------------- 8) 非 Windows / 防御
print("== 8) 非 Windows 短路 / _device_name / 日志容错 ==")
ns["IS_WIN"] = False
check("switch 非 win", ns["switch_to_virtual"](), (False, "not-windows"))
check("restore 非 win", ns["restore_original"](), (False, "not-windows"))
check("recover 非 win", ns["recover_if_needed"](), (False, "not-windows"))
check("_device_name 非 win 原样", ns["_device_name"]("abc.def"), "abc.def")
check("_device_name None", ns["_device_name"](None), "")
ns["IS_WIN"] = True

msgs = []
ns["init"](lambda m: msgs.append(m))
ns["_logv"]("hello")
check("init 注入生效", msgs[-1], "hello")
ns["init"](lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
ns["_logv"]("x")                                 # 不应抛出
check("_logv 容错异常", True, True)

# v1.2 约定: CoInit 走裸 Win32（comtypes>=1.4 兼容; 防回改）
check("约定 CoInit 裸 Win32 调用", "ctypes.windll.ole32.CoInitializeEx(None, 0x0)" in src, True)

print("")
print("== 结果: %d PASS / %d FAIL ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
