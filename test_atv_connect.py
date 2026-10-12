#!/usr/bin/env python3
"""M2 验证: 用配对凭据连接 ATV4K, 读设备信息与电源状态"""
import asyncio
import json
import sys

import pyatv
from pyatv.const import Protocol

ATV_ID = "F6AFC21D-9D6A-4505-B0FC-4E84E9D4D2FF"
CREDS = "/root/remote-hub/atv-credentials.json"


async def main():
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, timeout=8, identifier=ATV_ID)
    if not atvs:
        print("!! 未发现 ATV")
        return 2
    conf = atvs[0]
    creds = json.load(open(CREDS))
    for name, proto in (("Companion", Protocol.Companion), ("AirPlay", Protocol.AirPlay)):
        if name in creds:
            conf.set_credentials(proto, creds[name])
    print("connecting...")
    atv = await pyatv.connect(conf, loop)
    try:
        print("device_info:", atv.device_info)
        try:
            ps = atv.power.power_state
            print("power_state:", ps)
        except Exception as e:  # noqa: BLE001
            print("power_state 读取失败:", repr(e))
    finally:
        atv.close()
    print("OK: 凭据连接验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
