#!/usr/bin/env python3
# cgpost serve 诊断客户端（UNIX dgram；显式 bind 自己的接收路径——macOS 必须，勿简化）
# 配套文档: remote-hub/mac-key-bridge.md「诊断」节
# 用法: python3 cgpost_cli.py PING | STATUS | "KEY 107 1" | "KEY 107 0"
import os
import socket
import sys

msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "PING"
mypath = f"/tmp/cgpost_cli_{os.getpid()}.sock"
try:
    os.unlink(mypath)
except OSError:
    pass

s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.settimeout(3.0)
try:
    s.bind(mypath)                       # 显式命名 -> 服务端 sendto 能回包
    s.sendto(msg.encode(), "/tmp/cgpost.sock")
    print("RX:", s.recv(512).decode().strip())
except socket.timeout:
    print("TIMEOUT (3s 无应答)")
except Exception as e:
    print(f"ERR: {e}")
finally:
    s.close()
    try:
        os.unlink(mypath)
    except OSError:
        pass
