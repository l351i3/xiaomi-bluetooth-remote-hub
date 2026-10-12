#!/usr/bin/env python3
"""BLE 被动侦听（只扫描，不连接、不配对）——观察 RC003 遥控器是否在 Mac 附近广播。
用法: python3 ble_scan.py [持续秒数, 默认 300]
识别线索: 遥控器 MAC C0:5D:39:XX:XX:XX（macOS 只给 UUID）；特征 = 无名但 RSSI 强、
        可能带 0xFE59 (Nordic) / 小米厂商标识；物理贴近时 RSSI 应 >= -60。
"""
import asyncio
import sys
import time

from bleak import BleakScanner

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 300


async def main():
    seen = {}
    t0 = time.monotonic()

    def cb(device, adv):
        key = device.address
        is_new = key not in seen
        seen[key] = (device.name, adv.rssi)
        if is_new:
            mfg = ",".join(f"0x{k:04X}" for k in adv.manufacturer_data) if getattr(adv, "manufacturer_data", None) else ""
            svc = ",".join(u for u in (adv.service_uuids or [])[:4])
            t = time.monotonic() - t0
            print(f"+{t:6.1f}s  {device.address}  name={device.name!r}  rssi={adv.rssi}  mfg=[{mfg}]  svc=[{svc}]", flush=True)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    print(f"SCAN-STARTED duration={DURATION}s", flush=True)
    await asyncio.sleep(DURATION)
    await scanner.stop()
    print(f"SCAN-DONE total_unique={len(seen)}", flush=True)


asyncio.run(main())
