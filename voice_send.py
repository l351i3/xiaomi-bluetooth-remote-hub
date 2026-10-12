#!/usr/bin/env python3
# voice_send.py — 向 voice_bridge (UDP :8788) 发送语音事件，模拟 T1 按键链路
# 用法: python voice_send.py "VOICE down" | "VOICE up" | "status" | "ping"
import socket
import sys

msg = sys.argv[1] if len(sys.argv) > 1 else "ping"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(msg.encode(), ("127.0.0.1", 8788))
print("sent:", msg)
