#!/usr/bin/env python3
"""只读探针: 检查 ATV 连接后的协议栈组成（不发送任何按键）"""
import asyncio
import json

import pyatv
from pyatv.const import Protocol

ATV_ID = "F6AFC21D-9D6A-4505-B0FC-4E84E9D4D2FF"
CREDS = "/root/remote-hub/atv-credentials.json"


async def main():
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, timeout=8, identifier=ATV_ID)
    if not atvs:
        print("ATV 未发现!")
        return
    conf = atvs[0]
    print("=== SCAN SERVICES ===")
    for svc in conf.services:
        has = "YES" if svc.credentials else "no"
        print(f"  {svc.protocol!s:12s} port={svc.port} creds={has}")

    creds = json.load(open(CREDS))
    conf.set_credentials(Protocol.Companion, creds.get("Companion"))
    conf.set_credentials(Protocol.AirPlay, creds.get("AirPlay"))

    atv = await pyatv.connect(conf, loop)
    rc = atv.remote_control
    print("=== CONNECTED ===")
    print("rc type:", type(rc).__name__)
    if hasattr(rc, "main_protocol"):
        print("main_protocol:", rc.main_protocol)
    if hasattr(rc, "_interfaces"):
        for proto, inst in rc._interfaces.items():
            mod = type(inst).__module__
            print(f"  registered: {proto!s:12s} <- {mod}")

    # 验证各关键命令由哪个协议提供（仅解析, 不调用）
    for target in ("top_menu", "home", "menu", "volume_up", "up"):
        try:
            inst = rc._find_instance(target, rc._priorities)
            print(f"  relay {target:10s} -> {type(inst).__module__}")
        except Exception as e:  # noqa: BLE001
            print(f"  relay {target:10s} -> NOT SUPPORTED ({e})")

    await atv.close()


asyncio.run(main())
