#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
win_audio_switch.py — Windows 默认录音设备按需切换 v1.2 (2026-10-11)
====================================================================
用途（方案 V，2026-10-11 定案）：遥控器语音键**按下** → 把系统「默认录音设备」切到
VB-Cable 虚拟录音端（"CABLE Output"）→ **松开后延迟 ~2s 切回**原设备。
配合微信输入法「麦克风 = 默认设备」使用：平时录真麦不受影响，遥控会话自动让位。

链路:
  遥控 MIC → T1 atvv_service → win_audio_receiver → CABLE Input（播放端）
        →（虚拟线）→ CABLE Output（录音端）
  微信输入法读「默认设备」 → 会话期间 = CABLE Output ✅ / 平时 = 真麦 ✅

v1.2 变更（2026-10-11，CoInit 修复正式合入 —— Windows 真机回传补丁）：
  · ★ _ensure_com 原调 comtypes.CoInitializeEx(None, 0x2)：comtypes>=1.4 的封装只接受
    1 个参数 → TypeError 被 except 吞掉 → 本线程 COM 从未初始化 → 计划任务(pythonw)
    实例下 list_capture 报 CO_E_NOTINITIALIZED，麦克风切换恒失败（fail-open 静默）。
    改用裸 Win32: ctypes.windll.ole32.CoInitializeEx(None, 0x0)（COINIT_MULTITHREADED,
    与 comtypes 版本无关, 显式 MTA）。—— Windows 侧 20261011 定位, 两轮施工保留本地
    修复版, 本次正式合入上游（避免每次全量替换退回）。

v1.1 变更（2026-10-11）：内置「延迟切回」调度 —— schedule_restore / cancel_pending_restore。
  · 松开 → schedule_restore(2s)；连按（新会话开始）→ switch_to_virtual 自动取消旧调度；
  · 竞态防护：代（gen）计数双重检查（拿锁后复核）——stale 定时器绝不会切掉新会话；
  · win_receiver 只管调用以下 API，不自行维护定时器。

实现（comtypes；与 uiautomation 同依赖，无需新包）:
  · IMMDeviceEnumerator / IMMDevice: 枚举录音设备（eCapture）、读当前默认（eConsole）
  · IPolicyConfig.SetDefaultEndpoint: 设置默认 —— Console/Multimedia/Communications 三 role 同切
  · 设备 FriendlyName 经注册表 MMDevices\\Audio\\Capture\\...\\Properties 读取（避开 PROPVARIANT）

状态: state/audio_switch.json —— 防中途崩溃残留（phase=switched 时启动自愈切回）
API（供 win_receiver）:
  init(log_fn)            注入日志
  switch_to_virtual()     -> (ok, detail)  按下时调用（幂等, fail-open, 先切后注入; 自动取消待切回）
  schedule_restore(delay)              松开时调用 → 延迟切回（delay=None 用默认 2s）
  cancel_pending_restore()             取消待切回（switch_to_virtual 已自动调用）
  restore_original()      -> (ok, detail)  立即切回（同步 API; 测试/手动用）
  recover_if_needed()     -> (ok, detail)  进程启动时调用（崩溃自愈）
  list_capture() / find_virtual() / get_default_capture() / status()  诊断与自检
线程: 各调用线程独立 CoInitializeEx(MTA)；本模块不跨线程共享 COM 接口对象。
"""

import json
import os
import threading
import time

VERSION = "1.2"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
IS_WIN = (os.name == "nt")

VIRTUAL_MATCH = "cable output"     # 虚拟录音设备名匹配（不区分大小写）

_log = print


def init(log_fn):
    """由主程序注入日志函数（win_receiver 的异步 log）。"""
    global _log
    _log = log_fn


def _logv(msg):
    try:
        _log(msg)
    except Exception:
        pass


# ================================================================
# COM 定义（Windows only；非 Windows 下整体跳过, 纯逻辑可用可测）
# ================================================================
if IS_WIN:
    import ctypes
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from ctypes import POINTER, c_int, c_void_p, c_wchar_p

    CLSID_MM_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
    CLSID_POLICY_CONFIG = "{870af99c-171d-4f9e-af0d-e63df40c2bc9}"

    E_CAPTURE = 1                  # EDataFlow::eCapture
    DEVICE_STATE_ACTIVE = 0x1
    ROLE_ALL = (0, 1, 2)           # eConsole / eMultimedia / eCommunications

    class IPolicyConfig(IUnknown):
        _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
        _methods_ = (
            COMMETHOD([], HRESULT, "GetMixFormat",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["out"], POINTER(c_void_p), "ppFormat")),
            COMMETHOD([], HRESULT, "GetDeviceFormat",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_int, "bDefault"),
                      (["out"], POINTER(c_void_p), "ppFormat")),
            COMMETHOD([], HRESULT, "ResetDeviceFormat",
                      (["in"], c_wchar_p, "wszDeviceName")),
            COMMETHOD([], HRESULT, "SetDeviceFormat",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_void_p, "pEndpointFormat"),
                      (["in"], c_void_p, "pMixFormat")),
            COMMETHOD([], HRESULT, "GetProcessingPeriod",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_int, "bDefault"),
                      (["out"], POINTER(c_int), "pmftDefaultPeriod"),
                      (["out"], POINTER(c_int), "pmftMinimumPeriod")),
            COMMETHOD([], HRESULT, "SetProcessingPeriod",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], POINTER(c_int), "pmftPeriod")),
            COMMETHOD([], HRESULT, "GetShareMode",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["out"], POINTER(c_void_p), "pMode")),
            COMMETHOD([], HRESULT, "SetShareMode",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_void_p, "mode")),
            COMMETHOD([], HRESULT, "GetPropertyValue",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_void_p, "key"),
                      (["out"], POINTER(c_void_p), "pv")),
            COMMETHOD([], HRESULT, "SetPropertyValue",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_void_p, "key"),
                      (["in"], c_void_p, "pv")),
            COMMETHOD([], HRESULT, "SetDefaultEndpoint",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_int, "eRole")),
            COMMETHOD([], HRESULT, "SetEndpointVisibility",
                      (["in"], c_wchar_p, "wszDeviceName"),
                      (["in"], c_int, "bVisible")),
        )

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = (
            COMMETHOD([], HRESULT, "Activate",
                      (["in"], POINTER(GUID), "iid"),
                      (["in"], c_int, "dwClsCtx"),
                      (["in"], c_void_p, "pActivationParams"),
                      (["out"], POINTER(POINTER(IUnknown)), "ppInterface")),
            COMMETHOD([], HRESULT, "OpenPropertyStore",
                      (["in"], c_int, "stgmAccess"),
                      (["out"], POINTER(POINTER(IUnknown)), "ppProperties")),
            COMMETHOD([], HRESULT, "GetId",
                      (["out"], POINTER(c_wchar_p), "ppstrId")),
            COMMETHOD([], HRESULT, "GetState",
                      (["out"], POINTER(c_int), "pdwState")),
        )

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = (
            COMMETHOD([], HRESULT, "GetCount",
                      (["out"], POINTER(c_int), "pcDevices")),
            COMMETHOD([], HRESULT, "Item",
                      (["in"], c_int, "nDevice"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
        )

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = (
            COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                      (["in"], c_int, "dataFlow"),
                      (["in"], c_int, "dwStateMask"),
                      (["out"], POINTER(POINTER(IMMDeviceCollection)), "ppDevices")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                      (["in"], c_int, "dataFlow"),
                      (["in"], c_int, "role"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
            COMMETHOD([], HRESULT, "GetDevice",
                      (["in"], c_wchar_p, "pwstrId"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
            COMMETHOD([], HRESULT, "RegisterEndpointNotificationCallback",
                      (["in"], c_void_p, "pClient")),
            COMMETHOD([], HRESULT, "UnregisterEndpointNotificationCallback",
                      (["in"], c_void_p, "pClient")),
        )

    _com_ready = threading.local()

    def _ensure_com():
        """当前线程 CoInitializeEx(MTA)。已初始化/异模式均容忍。

        v1.2: 原写法 comtypes.CoInitializeEx(None, 0x2) 在 comtypes>=1.4 抛
        TypeError（只接受 1 个 flags 参数）→ 被 except 吞掉 → 线程 COM 从未
        初始化 → 计划任务实例下麦克风切换恒失败。改裸 Win32, 版本无关。"""
        if getattr(_com_ready, "ok", False):
            return
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)   # COINIT_MULTITHREADED
        except Exception:
            pass
        _com_ready.ok = True


# ================================================================
# 平台层（Windows COM；非 Windows 空实现——纯逻辑可测）
# ================================================================
def _device_name(device_id):
    """device_id -> FriendlyName（注册表; 失败返回尾部片段）。"""
    if not IS_WIN:
        return device_id or ""
    try:
        import winreg
        guid = device_id.rsplit(".", 1)[-1]         # "{0.0.0.00000000}.{GUID}" -> "{GUID}"
        path = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
                "\\" + guid + r"\Properties")
        for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
            for valname in ("{a45c254e-df1c-4efd-8020-67d146a850e0},2",     # PKEY_Device_FriendlyName
                            "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"):   # PKEY_Device_DeviceDesc
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, access) as k:
                        name, _ = winreg.QueryValueEx(k, valname)
                        if name:
                            return str(name)
                except OSError:
                    continue
    except Exception:
        pass
    return (device_id or "")[-40:]


def list_capture():
    """所有活动录音设备 [ (device_id, friendly_name) ]；失败 []。"""
    if not IS_WIN:
        return []
    try:
        _ensure_com()
        de = comtypes.CoCreateInstance(GUID(CLSID_MM_ENUMERATOR),
                                       interface=IMMDeviceEnumerator)
        coll = de.EnumAudioEndpoints(E_CAPTURE, DEVICE_STATE_ACTIVE)
        out = []
        for i in range(coll.GetCount()):
            try:
                did = coll.Item(i).GetId()
                out.append((str(did), _device_name(str(did))))
            except Exception:
                continue
        return out
    except Exception as e:
        _logv("list_capture error: %s" % e)
        return []


def get_default_capture():
    """当前默认录音设备 id（eConsole role）；失败 None。"""
    if not IS_WIN:
        return None
    try:
        _ensure_com()
        de = comtypes.CoCreateInstance(GUID(CLSID_MM_ENUMERATOR),
                                       interface=IMMDeviceEnumerator)
        return str(de.GetDefaultAudioEndpoint(E_CAPTURE, 0).GetId())
    except Exception as e:
        _logv("get_default_capture error: %s" % e)
        return None


def set_default_capture(device_id):
    """把默认录音设备设为 device_id（三 role 同切）。返回是否成功。"""
    if not IS_WIN or not device_id:
        return False
    try:
        _ensure_com()
        pc = comtypes.CoCreateInstance(GUID(CLSID_POLICY_CONFIG),
                                       interface=IPolicyConfig)
        for role in ROLE_ALL:
            pc.SetDefaultEndpoint(device_id, role)
        return True
    except Exception as e:
        _logv("set_default_capture error: %s" % e)
        return False


def find_virtual(devices=None):
    """在录音设备列表中找虚拟设备。返回 (id, name) 或 (None, None)。"""
    devs = devices if devices is not None else list_capture()
    for did, name in devs:
        if VIRTUAL_MATCH in (name or "").lower():
            return (did, name)
    return (None, None)


# ================================================================
# 状态文件（防崩溃残留）
# ================================================================
def _state_path():
    return os.path.join(STATE_DIR, "audio_switch.json")


def _load_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(d):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _state_path())
    except Exception as e:
        _logv("state save error: %s" % e)


# ================================================================
# 状态机（高层 API）
# ================================================================
_switch_lock = threading.Lock()
_rt_original = {"id": None}          # 内存态：本次会话保存的原设备

RESTORE_DELAY = 2.0                  # 松开后延迟切回（秒）；输入法收尾需要缓冲
_restore_gen = 0                     # 调度代计数：自增即作废旧定时器
_restore_timer = None


def _cancel_restore_locked():
    """（调用方持 _switch_lock 或不需要时）使当前待切回作废。"""
    global _restore_gen
    _restore_gen += 1
    t = _restore_timer
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def cancel_pending_restore():
    """取消待切回（连按保护；switch_to_virtual 已自动调用）。"""
    _cancel_restore_locked()


def schedule_restore(delay=None):
    """松开语音键后调用：延迟 delay 秒切回原设备（默认 RESTORE_DELAY）。
    期间若新会话开始（switch_to_virtual）→ 本调度自动作废。
    返回本次调度代（测试用）。"""
    global _restore_gen, _restore_timer
    _cancel_restore_locked()
    gen = _restore_gen
    t = threading.Timer(RESTORE_DELAY if delay is None else float(delay),
                        _do_restore, args=(gen,))
    t.daemon = True
    _restore_timer = t
    t.start()
    _logv("restore scheduled in %.2fs (gen=%d)" %
          (RESTORE_DELAY if delay is None else float(delay), gen))
    return gen


def _do_restore(gen):
    """定时器线程：到期执行切回；拿锁后复核代（防 stale 定时器切掉新会话）。"""
    if not IS_WIN:
        return
    with _switch_lock:
        if gen != _restore_gen:
            _logv("pending restore skipped (stale gen %d != %d)" % (gen, _restore_gen))
            return
        ok, detail = _restore_locked()
        _logv("delayed restore -> ok=%s [%s]" % (ok, detail))


def switch_to_virtual():
    """语音按下：保存当前默认 → 切到虚拟设备。幂等；fail-open。
    自动取消「待切回」调度（连按保护）。返回 (ok, detail)。"""
    if not IS_WIN:
        return (False, "not-windows")
    with _switch_lock:
        _cancel_restore_locked()
        devices = list_capture()
        if not devices:
            return (False, "no-capture-devices")
        vid, vname = find_virtual(devices)
        if vid is None:
            return (False, "virtual-not-found (match='%s')" % VIRTUAL_MATCH)
        cur = get_default_capture()
        if _rt_original["id"] is None:
            _rt_original["id"] = cur
            _save_state({"phase": "switched", "original": cur, "cable": vid,
                         "ts": time.time()})
        if cur == vid:
            return (True, "already-virtual")
        if not set_default_capture(vid):
            return (False, "set-default-failed")
        return (True, "switched -> %s" % vname)


def _restore_locked():
    """（调用方持 _switch_lock）切回保存的原设备。"""
    orig = _rt_original["id"] or _load_state().get("original")
    if not orig:
        return (False, "no-session")
    cur = get_default_capture()
    if cur == orig:
        _rt_original["id"] = None
        _save_state({"phase": "idle"})
        return (True, "already-original")
    if not set_default_capture(orig):
        return (False, "restore-set-failed")
    _rt_original["id"] = None
    _save_state({"phase": "idle"})
    return (True, "restored")


def restore_original():
    """立即切回保存的原设备（同步 API）。无会话记录则 no-op。返回 (ok, detail)。"""
    if not IS_WIN:
        return (False, "not-windows")
    with _switch_lock:
        return _restore_locked()


def recover_if_needed():
    """进程启动自愈：状态文件 phase=switched（上次会话未恢复）→ 切回原设备。
    返回 (ok, detail)。"""
    if not IS_WIN:
        return (False, "not-windows")
    with _switch_lock:
        st = _load_state()
        if st.get("phase") != "switched":
            return (False, "no-recovery-needed")
        orig = st.get("original")
        if not orig:
            _save_state({"phase": "idle"})
            return (False, "no-original-recorded")
        devices = list_capture()
        if devices and orig not in [d[0] for d in devices]:
            _save_state({"phase": "idle"})
            return (False, "original-device-gone (%s)" % str(orig)[-24:])
        cur = get_default_capture()
        if cur == orig:
            _save_state({"phase": "idle"})
            return (True, "already-original (cleanup)")
        if not set_default_capture(orig):
            return (False, "recover-set-failed")
        _save_state({"phase": "idle"})
        return (True, "recovered -> original")


def status():
    """诊断文本（selftest / 日志用；打印感知原始值供人工确认）。"""
    devs = list_capture()
    vid, vname = find_virtual(devs)
    cur = get_default_capture()
    lines = ["capture devices (%d):" % len(devs)]
    for did, name in devs:
        tag = ""
        if vid is not None and did == vid:
            tag = "  [VIRTUAL]"
        if did == cur:
            tag += "  [DEFAULT]"
        lines.append("  %-52s%s" % ((name or "?")[:52], tag))
    lines.append("virtual match '%s': %s" % (VIRTUAL_MATCH, vname or "(not found)"))
    return "\n".join(lines)
