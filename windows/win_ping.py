#!/usr/bin/env python3
"""win_ping.py — Windows 接收端连通性自检（从 T1 / Mac 发起）

用法: python3 win_ping.py [host]        # 默认 WINDOWS_IP
原理: 向 8788 / 8791（win_receiver: 语音触发+按键）/ 8789（win_audio_receiver: 音频）各发 "PING"，等 "PONG"。
退出码: 0=至少一个端口 PONG；1=全部无响应（检查接收端是否在跑 / 防火墙）。
"""
import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "WINDOWS_IP"
PORTS = (8788, 8791, 8789)

ok = False
for port in PORTS:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        t0 = time.time()
        s.sendto(b"PING", (HOST, port))
        data, addr = s.recvfrom(256)
        dt = (time.time() - t0) * 1000
        print("Port %d: PONG from %s:%d in %.0f ms  (%r)" % (port, addr[0], addr[1], dt, data))
        ok = True
    except socket.timeout:
        print("Port %d: 超时（3s 无 PONG）" % port)
    except Exception as e:
        print("Port %d: 错误 %s" % (port, e))
    finally:
        s.close()

print("== 结果: %s ==" % ("可达 ✅" if ok else "不可达 ❌（检查接收端进程 / Windows 防火墙入站 UDP 规则）"))
sys.exit(0 if ok else 1)
