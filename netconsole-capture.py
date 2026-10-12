#!/usr/bin/env python3
"""netconsole 抓包监听（EXP-19 补丁打印采集）
监听 UDP 6666，把内核 netconsole 发来的消息写入日志文件。
自动退出：无包超时 180s 或总时长 15 分钟。
"""
import socket
import time
import sys

PORT = 6666
LIMIT_TOTAL = 900      # 总时长上限（秒）
LIMIT_IDLE = 180       # 空闲超时（秒）

out = f"netconsole-capture-{time.strftime('%m%d-%H%M%S')}.log"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", PORT))
s.settimeout(5)

with open(out, "w") as f:
    f.write(f"# netconsole capture start {time.strftime('%F %T')}\n")
    f.flush()
    t0 = time.time()
    last = time.time()
    while True:
        try:
            data, addr = s.recvfrom(65535)
            line = data.decode("utf-8", "replace").rstrip()
            ts = time.strftime("%F %T")
            f.write(f"{ts} [{addr[0]}:{addr[1]}] {line}\n")
            f.flush()
            last = time.time()
        except socket.timeout:
            now = time.time()
            if now - last > LIMIT_IDLE or now - t0 > LIMIT_TOTAL:
                break
        except KeyboardInterrupt:
            break
    f.write(f"# netconsole capture end {time.strftime('%F %T')}\n")
print(f"capture finished -> {out}")
