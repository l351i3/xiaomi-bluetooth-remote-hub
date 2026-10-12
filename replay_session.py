#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_session.py — 把 T1 抓包文件中的某个会话（sid）原样重放给接收端

用途: 故障复现 / 修复验证（不经过遥控器与 T1，直接喂 UDP:8789）
用法: python replay_session.py <sid> [--file /tmp/atvv_frames.bin] [--host 127.0.0.1]
      [--port 8789] [--fps 64.5]
协议: 每包 = [1B type][payload]；02=会话开始(1B sid) / 01=音频(120B) / 03=结束
"""
import argparse
import socket
import struct
import sys
import time


def load_sessions(path):
    data = open(path, "rb").read()
    if data[:8] != b"T1SNIFF1":
        raise SystemExit("bad sniff file")
    off = 16
    sessions = []
    cur = None
    while off + 6 <= len(data):
        ms, ln = struct.unpack(">IH", data[off:off + 6])
        off += 6
        pl = data[off:off + ln]
        off += ln
        if not pl:
            continue
        t, b = pl[0], pl[1:]
        if t == 0x02:
            cur = {"sid": b[0] if b else -1, "frames": []}
            sessions.append(cur)
        elif t == 0x01 and cur is not None:
            cur["frames"].append(b)
        elif t == 0x03:
            cur = None
    return sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sid", type=int)
    ap.add_argument("--file", default="/tmp/atvv_frames.bin")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8789)
    ap.add_argument("--fps", type=float, default=64.5)
    args = ap.parse_args()

    sessions = load_sessions(args.file)
    target = None
    for s in sessions:
        if s["sid"] == args.sid and s["frames"]:
            target = s
            break
    if target is None:
        print("!! 未找到 sid=%d 的会话" % args.sid)
        sys.exit(1)

    fr = target["frames"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dst = (args.host, args.port)
    dt = 1.0 / args.fps
    t0 = time.time()
    sock.sendto(bytes([0x02, args.sid & 0xFF]), dst)
    nxt = time.time()
    for f in fr:
        sock.sendto(bytes([0x01]) + f, dst)
        nxt += dt
        s = nxt - time.time()
        if s > 0:
            time.sleep(s)
    sock.sendto(bytes([0x03]), dst)
    dur = time.time() - t0
    print("重放完成: sid=%d %d 帧 用时 %.2fs (目标时长 %.2fs)" % (args.sid, len(fr), dur, len(fr) * dt))


if __name__ == "__main__":
    main()
