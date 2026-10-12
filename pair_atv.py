#!/usr/bin/env python3
"""T1 上 ATV4K 配对脚本 (Companion + AirPlay)

流程:
  1. 扫描发现 ATV4K (identifier F6AF...)
  2. 配对 Companion (电视屏幕显示 PIN -> 从 FIFO 读入)
  3. 配对 AirPlay (同上)
  4. 凭据写入 /root/remote-hub/atv-credentials.json (chmod 600)

PIN 交互: 外部通过 `echo <PIN> > /tmp/atv_pin.fifo` 注入
"""
import asyncio
import json
import os
import sys

from pyatv import pair, scan
from pyatv.const import Protocol

ATV_ID = "F6AFC21D-9D6A-4505-B0FC-4E84E9D4D2FF"  # ATV4K @LAN_IP
PIN_FIFO = "/tmp/atv_pin.fifo"
OUT = "/root/remote-hub/atv-credentials.json"
PAIR_PROTOS = (Protocol.Companion, Protocol.AirPlay)


def log(*a):
    print(*a, flush=True)


def read_pin(proto_name):
    """从 FIFO 读一个 PIN (阻塞等待外部注入)"""
    log(f"[{proto_name}] 等待 PIN 注入 ({PIN_FIFO}) ...")
    while True:
        with open(PIN_FIFO) as f:
            line = f.readline().strip()
        if line:
            log(f"[{proto_name}] 收到 PIN: {line}")
            return line


async def main():
    if not os.path.exists(PIN_FIFO):
        os.mkfifo(PIN_FIFO, 0o600)

    loop = asyncio.get_event_loop()
    atvs = await scan(loop, timeout=8, identifier=ATV_ID)
    if not atvs:
        log("!! 未发现 ATV4K")
        return 2
    conf = atvs[0]
    log(f"发现: {conf.name} @ {conf.address}")

    results = {}
    for proto in PAIR_PROTOS:
        if conf.get_service(proto) is None:
            log(f"[{proto.name}] 无此服务, 跳过")
            continue
        log(f"===== 配对 {proto.name} =====")
        handler = None
        try:
            handler = await pair(conf, proto, loop)
            await handler.begin()
            if handler.device_provides_pin:
                log(">>> 请查看电视屏幕上的 PIN 码 <<<")
                pin = read_pin(proto.name)
                handler.pin(pin)
            else:
                log("设备不显示 PIN, 使用 1234")
                handler.pin(1234)
            await handler.finish()
            if handler.has_paired:
                creds = handler.service.credentials
                results[proto.name] = creds
                conf.set_credentials(proto, creds)
                log(f"[{proto.name}] OK 配对成功")
            else:
                log(f"[{proto.name}] FAIL 配对失败")
        except Exception as e:  # noqa: BLE001
            log(f"[{proto.name}] 异常: {e!r}")
        finally:
            if handler:
                await handler.close()

    if results:
        with open(OUT, "w") as f:
            json.dump(results, f, indent=2)
        os.chmod(OUT, 0o600)
        log(f"凭据已保存: {OUT}")
        for k, v in results.items():
            log(f"  {k}: {str(v)[:24]}...")
    else:
        log("!! 没有任何协议配对成功")
    return 0 if results else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
