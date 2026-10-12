#!/usr/bin/env python3
# t1_sniff.py — T1 侧 AF_PACKET 抓 UDP:8789 原始负载（无 libpcap/tcpdump 环境）
# 输出格式: [16B 头: magic"T1SNIFF1"+起始epoch(8B double 大端)] + 循环记录 [4B ms偏移][2B 长度][负载]
# 用法: python3 t1_sniff.py [输出文件] [持续秒数]
import socket
import struct
import sys
import time

iface = "eth0"
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/atvv_frames.bin"
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 900.0

print(f"T1 sniffer 启动 iface={iface} out={out} dur={dur:.0f}s", flush=True)
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
s.bind((iface, 0))
s.settimeout(1.0)
t0 = time.time()
n = 0
with open(out, "wb") as f:
    f.write(struct.pack(">8sd", b"T1SNIFF1", time.time()))
    while time.time() - t0 < dur:
        try:
            pkt = s.recv(65535)
        except socket.timeout:
            continue
        except Exception:
            continue
        if len(pkt) < 42:
            continue
        eth_type = struct.unpack("!H", pkt[12:14])[0]
        o = 14
        if eth_type == 0x8100 and len(pkt) >= o + 4:
            eth_type = struct.unpack("!H", pkt[o + 2:o + 4])[0]
            o += 4
        if eth_type != 0x0800:
            continue
        ip = pkt[o:]
        if len(ip) < 20 or ip[9] != 17:
            continue
        ihl = (ip[0] & 0x0F) * 4
        udp = ip[ihl:]
        if len(udp) < 8:
            continue
        dport = struct.unpack("!H", udp[2:4])[0]
        if dport != 8789:
            continue
        ulen = struct.unpack("!H", udp[4:6])[0]
        payload = udp[8:ulen]
        f.write(struct.pack(">IH", int((time.time() - t0) * 1000) & 0xFFFFFFFF, len(payload)) + payload)
        f.flush()
        n += 1
print(f"sniff 结束: 共 {n} 个 UDP 包", flush=True)
