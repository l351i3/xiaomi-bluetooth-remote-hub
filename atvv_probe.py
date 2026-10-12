#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATVV 探针 v0.2（T1 侧）——订阅遥控器语音通道 + 标准握手（无人参与自检）。

v0.2 变更 (2026-10-09):
  - hex 全量记录（v0.1 默认截断 48B，丢了每包 60% 音频数据 → 解码失真）
  - --mic-auto 增加 MIC_EXTEND：流中每 2s 发 [0x0E, sid] 延长会话防遥控器超时断流
  - 记录 SID（AUDIO_START 报文最后一字节，逐次递增）

流程:
  1. 枚举 org.bluez 对象，定位 RC003 (C0:5D:39:XX:XX:XX) 的 ATVV 服务（ab5e0001）
     下三个特征: WRITE=ab5e0002 / AUDIO=ab5e0003(音频) / CTRL=ab5e0004(信令)
  2. AcquireNotify 订阅 AUDIO + CTRL（拿 fd）
  3. 向 WRITE 写 GET_CAPS [0A 01 00 00 03 03]（标准能力协商；字节取自 mi-ao PROTOCOL.md）
  4. 监听 N 秒，打印所有收到的通知（hex）

可选 --mic-auto（用户按键实测用）:
  收到 CTRL 0x04 (AUDIO_START) 时回写 MIC_OPEN [0C 00]（RC003 变体，且仅在非流中）；
  收到 CTRL 0x00 (AUDIO_STOP 且确在流中) 时回写 MIC_CLOSE [0D]（防回显风暴）。

用法: python3 atvv_probe.py [监听秒数=8] [--mic-auto]
"""
import sys, os, time, select, traceback
import dbus

MAC = "C0:5D:39:XX:XX:XX"
SVC_UUID = "ab5e0001"
RX_UUID = "ab5e0002"   # host -> remote（写口）
AU_UUID = "ab5e0003"   # remote -> host 音频（notify）
CT_UUID = "ab5e0004"   # remote -> host 控制（notify）

GET_CAPS  = [0x0A, 0x01, 0x00, 0x00, 0x03, 0x03]
MIC_OPEN  = [0x0C, 0x00]
MIC_CLOSE = [0x0D]


def hx(b, n=4096):
    h = b[:n].hex(" ")
    return h + (" …" if len(b) > n else "")


def main():
    listen_s = 8.0
    mic_auto = False
    for a in sys.argv[1:]:
        if a == "--mic-auto":
            mic_auto = True
        else:
            listen_s = float(a)

    bus = dbus.SystemBus()
    om = dbus.Interface(bus.get_object("org.bluez", "/"),
                        "org.freedesktop.DBus.ObjectManager")
    objs = om.GetManagedObjects()

    dev_frag = MAC.replace(":", "_")
    svc_uuid = {}
    chars = {}
    for path, ifaces in objs.items():
        if "org.bluez.GattService1" in ifaces:
            svc_uuid[str(path)] = str(ifaces["org.bluez.GattService1"].get("UUID", "")).lower()
        if "org.bluez.GattCharacteristic1" in ifaces:
            c = ifaces["org.bluez.GattCharacteristic1"]
            chars[str(path)] = {
                "uuid": str(c.get("UUID", "")).lower(),
                "flags": [str(f) for f in c.get("Flags", [])],
                "service": str(c.get("Service", "")),
            }

    atvv_svc = None
    for p, u in svc_uuid.items():
        if u.startswith(SVC_UUID) and dev_frag in p:
            atvv_svc = p
            break
    if not atvv_svc:
        print("!! ATVV 服务未找到（遥控器是否已连接？）")
        return 1
    print("ATVV service:", atvv_svc)

    found = {}
    for p, c in chars.items():
        if c["service"] != atvv_svc:
            continue
        short = c["uuid"].split("-")[0]
        found[short] = p
        print("  char %-8s uuid=%s flags=%s" % (p.split("/")[-1], short, ",".join(c["flags"])))

    for k in (RX_UUID, AU_UUID, CT_UUID):
        if k not in found:
            print("!! 缺少特征:", k)
            return 1
    wpath, apath, cpath = found[RX_UUID], found[AU_UUID], found[CT_UUID]

    def ciface(p):
        return dbus.Interface(bus.get_object("org.bluez", p),
                              "org.bluez.GattCharacteristic1")

    fd_a, mtu_a = ciface(apath).AcquireNotify(dbus.Dictionary({}, signature="sv"))
    fd_c, mtu_c = ciface(cpath).AcquireNotify(dbus.Dictionary({}, signature="sv"))

    def takefd(fd):
        return fd.take() if hasattr(fd, "take") else int(fd)

    rfd_a, rfd_c = takefd(fd_a), takefd(fd_c)
    print("notify acquired: audio mtu=%s fd=%s / ctrl mtu=%s fd=%s" % (mtu_a, rfd_a, mtu_c, rfd_c))

    w = ciface(wpath)
    w.WriteValue(dbus.Array([dbus.Byte(x) for x in GET_CAPS], signature="y"),
                 dbus.Dictionary({}, signature="sv"))
    print("GET_CAPS sent:", bytes(GET_CAPS).hex(" "))

    streaming = False
    sid = 0
    last_extend = 0.0
    t0 = time.time()
    names = {rfd_a: "AUDIO", rfd_c: "CTRL"}
    while time.time() - t0 < listen_s:
        r, _, _ = select.select([rfd_a, rfd_c], [], [], 0.5)
        for fd in r:
            data = os.read(fd, 1024)
            if not data:
                continue
            print("[%6.2fs] %s (%dB): %s" % (time.time() - t0, names[fd], len(data), hx(data)))
            if mic_auto and fd == rfd_c and data:
                if data[0] == 0x04 and not streaming:
                    streaming = True
                    sid = data[3] if len(data) >= 4 else 0
                    w.WriteValue(dbus.Array([dbus.Byte(x) for x in MIC_OPEN], signature="y"),
                                 dbus.Dictionary({}, signature="sv"))
                    last_extend = time.time()
                    print("   -> MIC_OPEN sent (sid=%s)" % sid)
                elif data[0] == 0x00 and streaming:
                    streaming = False
                    w.WriteValue(dbus.Array([dbus.Byte(x) for x in MIC_CLOSE], signature="y"),
                                 dbus.Dictionary({}, signature="sv"))
                    print("   -> MIC_CLOSE sent")
        # MIC_EXTEND: 流中每 2s 延长会话（防遥控器超时断流）
        if mic_auto and streaming and (time.time() - last_extend) > 2.0:
            w.WriteValue(dbus.Array([dbus.Byte(0x0E), dbus.Byte(sid)], signature="y"),
                         dbus.Dictionary({}, signature="sv"))
            last_extend = time.time()
            print("[%6.2fs]    -> MIC_EXTEND sent (sid=%s)" % (time.time() - t0, sid))
    for fd in (rfd_a, rfd_c):
        try:
            os.close(fd)
        except OSError:
            pass
    print("probe done (%ss)." % listen_s)
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        traceback.print_exc()
        rc = 2
    sys.exit(rc)
