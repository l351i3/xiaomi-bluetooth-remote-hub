#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offline_test.py —— win_receiver.py 的离线逻辑测试（macOS/Linux 可跑，Windows 亦可）
v1.1 版（适配异步日志改造）：把 SendInput 打桩、端口改为 18788/18791 后真实运行：
  1) 消息解析（KEY/VOICE、大小写、DOWN/UP、未知动作）
  2) 语音按住/松开序列与去重
  3) 真实 UDP 收发 + PING/PONG
  4) 异步日志（处理记录入盘 / RX 明细静默 / 队列溢出保护）
  5) 语音兜底释放（超时自动松开 / 未超时不误触发）
用法：python3 offline_test.py   （在 remote-hub/windows/ 目录下跑）
"""
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "win_receiver.py"), encoding="utf-8").read()
src = src.replace("VOICE_PORT = 8788", "VOICE_PORT = 18788")
src = src.replace("KEY_PORT = 8791", "KEY_PORT = 18791")

ns = {"__file__": os.path.join(HERE, "win_receiver.py"), "__name__": "win_receiver_test"}
exec(compile(src, "win_receiver.py", "exec"), ns)

sent = []


def fake_send_vk(vk, up=False, extended=False):
    sent.append((vk, up, extended))
    return True


ns["send_vk"] = fake_send_vk

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, "| got =", got, "| want =", want)


def drain():
    sent.clear()


# ---- 1) 纯逻辑（直接调 handler）----
print("== 1) 解析/去重逻辑 ==")
hv, hk = ns["handle_voice"], ns["handle_key"]

drain(); hk("KEY PAGEDOWN down"); check("PAGEDOWN down", sent, [(0x22, False, True)])
drain(); hk("KEY pagedown up");   check("PAGEDOWN up",   sent, [(0x22, True, True)])
drain(); hk("KEY ENTER down");    check("ENTER down",    sent, [(0x0D, False, False)])
drain(); hk("KEY LEFT up");       check("LEFT up",       sent, [(0x25, True, True)])
drain(); hk("KEY FOO down");      check("未知动作忽略",   sent, [])
drain(); hk("KEK");               check("坏消息忽略",     sent, [])

drain()
hv("VOICE down")
check("voice down 按住 Ctrl+Win", sent, [(0x11, False, False), (0x5B, False, False)])
drain(); hv("VOICE down"); check("重复 down 忽略", sent, [])
drain(); hv("VOICE up")
check("voice up 松开（逆序）", sent, [(0x5B, True, False), (0x11, True, False)])
drain(); hv("VOICE up"); check("重复 up 忽略", sent, [])

# ---- 2) 真实 UDP 收发 + PING/PONG ----
print("== 2) UDP 收发 + PING/PONG ==")
t1 = threading.Thread(target=ns["listen_udp"], args=(ns["VOICE_PORT"], ns["handle_voice"]), daemon=True)
t2 = threading.Thread(target=ns["listen_udp"], args=(ns["KEY_PORT"], ns["handle_key"]), daemon=True)
t1.start(); t2.start()
time.sleep(0.4)


def send(port, msg):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(msg.encode(), ("127.0.0.1", port))
    finally:
        s.close()


drain()
send(18791, "KEY SPACE down")
time.sleep(0.25)
check("UDP 收到并注入 SPACE", sent, [(0x20, False, False)])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(b"PING", ("127.0.0.1", 18791))
try:
    r, _ = s.recvfrom(64)
except socket.timeout:
    r = b"<timeout>"
finally:
    s.close()
check("PING -> PONG", r, b"PONG")

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(b"PING", ("127.0.0.1", 18788))
try:
    r, _ = s.recvfrom(64)
except socket.timeout:
    r = b"<timeout>"
finally:
    s.close()
check("PING -> PONG（语音口同样支持）", r, b"PONG")

# ---- 3) 异步日志（v1.1）----
print("== 3) 异步日志 ==")
LOGP = os.path.join(HERE, "receiver.log")
open(LOGP, "w").close()          # 清空，只看本次新写入
drain()
send(18791, "KEY ENTER down")
time.sleep(0.4)                  # 等异步日志线程落盘
logtxt = open(LOGP, encoding="utf-8").read()
check("日志含按键处理记录（异步落盘）", "KEY ENTER down -> vk=0x0D ok=True" in logtxt, True)
check("RX 明细默认静默（v1.1）", "[PING]" not in logtxt and "RX " not in logtxt, True)

# ---- 4) v1.1 队列溢出保护 + 兜底释放 ----
print("== 4) 队列溢出 / 语音兜底 ==")
import queue as _q
q_bak = ns["_LOGQ"]
ns["_LOGQ"] = _q.Queue(maxsize=1)
ok_flag = True
try:
    for i in range(50):
        ns["log"]("flood %d" % i)
except Exception:
    ok_flag = False
check("日志队列满不抛异常", ok_flag, True)
ns["_LOGQ"] = q_bak

drain()
send(18791, "KEY ESC down")
time.sleep(0.25)
check("日志风暴后 UDP 注入仍正常", sent, [(0x1B, False, False)])

drain()
hv("VOICE down")
check("兜底前置：voice 已按住", ns["_voice_held"], True)
drain()                                     # 清掉 down 注入记录，只看释放序列
ns["_voice_down_at"] = time.monotonic() - 61
r = ns["check_voice_hold"]()
check("兜底释放触发（超 60s）", r, True)
check("兜底释放序列（逆序）", sent, [(0x5B, True, False), (0x11, True, False)])
check("兜底后状态复位", ns["_voice_held"], False)

hv("VOICE down"); drain()
ns["_voice_down_at"] = time.monotonic() - 5
check("未超时不误触发", ns["check_voice_hold"](), False)
hv("VOICE up")

print("")
print("== 结果: %d PASS / %d FAIL ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
