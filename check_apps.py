#!/usr/bin/env python3
"""只读探针: 列出 ATV 上已安装的 app（名称 + bundle ID），用于给键位找准确标识符。
用法: /opt/pyatv/bin/python3 /root/remote-hub/check_apps.py
"""
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
        print("ATV NOT FOUND (scan 为空)")
        return
    conf = atvs[0]
    creds = json.load(open(CREDS))
    conf.set_credentials(Protocol.Companion, creds.get("Companion"))
    conf.set_credentials(Protocol.AirPlay, creds.get("AirPlay"))
    atv = await pyatv.connect(conf, loop)
    print("connected:", atv.device_info)
    try:
        apps = await atv.apps.app_list()
        print(f"total apps: {len(apps)}")
        for app in apps:
            try:
                name = str(app.name)
                ident = str(app.identifier)
            except Exception:
                name, ident = repr(app), "?"
            hit = "youtube" in name.lower() or "youtube" in ident.lower() or "tube" in ident.lower()
            mark = "   <== YOUTUBE?" if hit else ""
            print(f"- {name!r} | {ident}{mark}")
    except Exception as e:  # noqa: BLE001
        print("app_list failed:", repr(e))
    try:
        res = atv.close()
        if asyncio.iscoroutine(res):
            await res
    except Exception as e:  # noqa: BLE001
        print("close warn:", repr(e))


asyncio.run(main())
