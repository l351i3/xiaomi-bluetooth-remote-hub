#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_send.py —— remotehub-win receiver 的本机自测脚本
=========================================================
用法：先启动 win_receiver.py，再运行本脚本。
它会模拟 T1 的发包（共 9 个测试包 + 1 个 PING），并打印 PONG 结果。

预期：
  - receiver 的控制台与 receiver.log 出现 9 条 "RX 127.0.0.1 ... [KEY/VOICE ...]"
  - PING 收到 "PONG"
  - （可眼见）若先点开记事本/浏览器，能看到 PageDown 滚动、回车换行等注入效果。
    注意：注入会进入"当前焦点窗口"，测试前请把焦点放好（最好是记事本等无害窗口）。
"""
import socket
import time


def send(port, msg, host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(msg.encode("utf-8"), (host, port))
    finally:
        s.close()


def main():
    n = 0
    print("== 1) 按键序列（模拟连发 + 短按）==")
    seq = [
        ("PAGEDOWN", ["down", "down", "up"]),   # 翻页（连发两次）
        ("UP", ["down", "up"]),                 # 方向键短按
        ("ENTER", ["down", "up"]),              # 回车（OK 键）
    ]
    for action, phases in seq:
        for phase in phases:
            send(8791, "KEY %s %s" % (action, phase))
            print("  -> KEY %s %s" % (action, phase))
            n += 1
            time.sleep(0.15)

    print("== 2) 语音按住/松开（按住 Ctrl+Win 约 0.8s）==")
    send(8788, "VOICE down")
    print("  -> VOICE down")
    n += 1
    time.sleep(0.8)
    send(8788, "VOICE up")
    print("  -> VOICE up")
    n += 1

    print("== 3) PING/PONG 连通性 ==")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    try:
        s.sendto(b"PING", ("127.0.0.1", 8791))
        r, addr = s.recvfrom(128)
        print("  PONG:", r.decode("ascii", "replace"), "| from", addr[0])
    except socket.timeout:
        print("  PONG: TIMEOUT —— receiver 没在跑？或端口被占用/防火墙拦截")
    finally:
        s.close()

    print("")
    print("共发送 %d 个测试包（receiver.log 应有 %d 条 RX + 1 条 PING 的 RX）" % (n, n))
    print("检查 receiver.log 确认后，本机自测即通过。")


if __name__ == "__main__":
    main()
