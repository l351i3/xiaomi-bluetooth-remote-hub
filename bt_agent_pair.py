#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小米 RC003 蓝牙语音遥控器配对 —— Python dbus 全控 agent (BlueZ 5.66)

背景 (2026-10-08 实证):
  bluetoothctl 的 agent 注册在本机不可靠 (交互模式报 Failed to register
  agent object; 单命令模式静默失效), 导致 bluetoothd 在 LESC 确认环节
  "No agent available" -> 自动 Negative Reply -> SMP Pairing Failed。
  本脚本显式 RegisterAgent + RequestDefaultAgent, 并在全部 agent 回调上
  自动确认, 绕开 bluetoothctl 的全部问题。

对齐源码 (bluez 5.66 src/device.c device_confirm_passkey):
  confirm_hint=1 且 device->bonding!=NULL 时 bluetoothd 会 auto-accept,
  唯一前提是 new_auth() 能拿到默认 agent —— 本脚本保证这一点。

用法: bt_agent_pair.py [MAC] [CAP]
  CAP: NoInputNoOutput (默认) / DisplayYesNo / KeyboardDisplay
"""
import sys
import time

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

MAC = (sys.argv[1] if len(sys.argv) > 1 else "C0:5D:39:XX:XX:XX").upper()
CAP = sys.argv[2] if len(sys.argv) > 2 else "NoInputNoOutput"
AGENT_PATH = "/remotehub/agent"

BLUEZ = "org.bluez"
OM = "org.freedesktop.DBus.ObjectManager"
PROPS = "org.freedesktop.DBus.Properties"
ADAPTER = BLUEZ + ".Adapter1"
DEVICE = BLUEZ + ".Device1"
AGENT_MGR = BLUEZ + ".AgentManager1"
AGENT1 = BLUEZ + ".Agent1"


def log(*a):
    print("[pair]", *a, flush=True)


class Agent(dbus.service.Object):
    """org.bluez.Agent1 全回调实现, 一律自动确认。"""

    def __init__(self, bus):
        super(Agent, self).__init__(bus, AGENT_PATH)

    @dbus.service.method(AGENT1, in_signature="", out_signature="")
    def Release(self):
        log("agent回调: Release")

    @dbus.service.method(AGENT1, in_signature="os", out_signature="")
    def RequestPinCode(self, device, pincode):
        log("agent回调: RequestPinCode -> '0000'")
        return "0000"

    @dbus.service.method(AGENT1, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        log("agent回调: RequestPasskey -> 0")
        return dbus.UInt32(0)

    @dbus.service.method(AGENT1, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        log("agent回调: DisplayPasskey %06d entered=%d" % (passkey, entered))

    @dbus.service.method(AGENT1, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        log("agent回调: DisplayPinCode", pincode)

    @dbus.service.method(AGENT1, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log("agent回调: RequestConfirmation passkey=%06d -> 自动 YES" % passkey)

    @dbus.service.method(AGENT1, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        log("agent回调: RequestAuthorization -> 自动 YES")

    @dbus.service.method(AGENT1, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        log("agent回调: AuthorizeService", uuid, "-> 自动 YES")

    @dbus.service.method(AGENT1, in_signature="", out_signature="")
    def Cancel(self):
        log("agent回调: Cancel")


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    t0 = time.time()

    # --- 1. 定位 adapter 与目标设备 ---
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), OM)
    adapter_path = None
    dev_path = None
    for path, ifaces in om.GetManagedObjects().items():
        if ADAPTER in ifaces and adapter_path is None:
            adapter_path = path
        if DEVICE in ifaces:
            if str(ifaces[DEVICE].get("Address", "")).upper() == MAC:
                dev_path = path
    log("adapter =", adapter_path, " device =", dev_path)
    if not adapter_path:
        log("找不到蓝牙 adapter, 退出")
        return 2

    # --- 2. 不在缓存则扫描发现 ---
    if not dev_path:
        log("设备不在缓存, 扫描发现 (最多 20s)...")
        ad = dbus.Interface(bus.get_object(BLUEZ, adapter_path), ADAPTER)
        try:
            ad.StartDiscovery()
        except Exception as e:
            log("StartDiscovery 异常:", e)
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.5)
            for path, ifaces in om.GetManagedObjects().items():
                if DEVICE in ifaces:
                    if str(ifaces[DEVICE].get("Address", "")).upper() == MAC:
                        dev_path = path
                        break
            if dev_path:
                break
        try:
            ad.StopDiscovery()
        except Exception:
            pass
        log("扫描结果 dev_path =", dev_path)
    if not dev_path:
        log("未发现目标设备 %s —— 请确认遥控器处于配对模式 (指示灯快闪)" % MAC)
        return 3

    # --- 3. 注册 agent + 设为默认 (本次修复的核心) ---
    # 注意: AgentManager1 在根路径 /org/bluez, 不在 adapter 路径上
    agent = Agent(bus)
    am = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), AGENT_MGR)
    try:
        am.RegisterAgent(dbus.ObjectPath(AGENT_PATH), CAP)
        log("RegisterAgent OK, capability =", CAP)
    except dbus.exceptions.DBusException as e:
        log("RegisterAgent 失败:", e.get_dbus_name(), e.get_dbus_message())
        return 4
    try:
        am.RequestDefaultAgent(dbus.ObjectPath(AGENT_PATH))
        log("RequestDefaultAgent OK")
    except dbus.exceptions.DBusException as e:
        log("RequestDefaultAgent 失败:", e.get_dbus_name(), e.get_dbus_message())

    # --- 4. 监听目标设备属性变化 ---
    def on_props(interface, changed, invalidated):
        if interface != DEVICE:
            return
        for k in ("Paired", "Bonded", "Trusted", "Connected", "ServicesResolved"):
            if k in changed:
                log("   [属性]", k, "=", changed[k])

    bus.add_signal_receiver(on_props, dbus_interface=PROPS,
                            signal_name="PropertiesChanged", path=dev_path)

    dev_iface = dbus.Interface(bus.get_object(BLUEZ, dev_path), DEVICE)

    # --- 5. 异步 Pair() ---
    result = {"done": False, "err": None}

    def ok_cb():
        log(">>> Pair() 成功返回")
        result["done"] = True

    def err_cb(e):
        log(">>> Pair() 失败:", e.get_dbus_name(), e.get_dbus_message())
        result["err"] = e
        result["done"] = True

    log(">>> 发起 Pair() (异步, 90s 超时) ...")
    dev_iface.Pair(reply_handler=ok_cb, error_handler=err_cb, timeout=90)

    loop = GLib.MainLoop()
    state = {"t_end": None}

    def tick():
        if result["done"] and state["t_end"] is None:
            state["t_end"] = time.time()
        if state["t_end"] is not None and time.time() - state["t_end"] > 5:
            loop.quit()
            return False
        if time.time() - t0 > 160:
            log("总超时 160s, 退出")
            loop.quit()
            return False
        return True

    GLib.timeout_add(500, tick)
    loop.run()

    # --- 6. 结果与 Trusted ---
    rc = 1
    try:
        props = dbus.Interface(bus.get_object(BLUEZ, dev_path), PROPS)
        d = props.GetAll(DEVICE)
        log("最终: Paired=%s Bonded=%s Trusted=%s Connected=%s" % (
            d.get("Paired"), d.get("Bonded"), d.get("Trusted"), d.get("Connected")))
        if d.get("Paired") or d.get("Bonded"):
            rc = 0
            if not d.get("Trusted"):
                try:
                    props.Set(DEVICE, "Trusted", dbus.Boolean(True))
                    log("已设置 Trusted = true")
                except Exception as e:
                    log("设置 Trusted 失败:", e)
    except Exception as e:
        log("读取最终状态失败:", e)

    try:
        am.UnregisterAgent(dbus.ObjectPath(AGENT_PATH))
    except Exception:
        pass
    log("结束 rc =", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
