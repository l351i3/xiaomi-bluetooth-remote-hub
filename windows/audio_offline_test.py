#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audio_offline_test.py — win_audio_receiver.py 离线逻辑测试（macOS/Linux 可跑）

不依赖 sounddevice / 声卡（sounddevice 在 win_audio_receiver 里为惰性导入）：
  1) IMA ADPCM 解码（手工推算用例 + 状态连续性 + 输出长度）
  2) 上采样（长度 / 线性插值 / 直流保持 / 48k & 44.1k 比率）
  3) HPF（直流抑制 / 1kHz 通带保留）
  4) AGC（小声增益提升 / 不超上限 / 0.95 限幅）
  5) Chain 整体（长度 / 限幅 / 无 NaN）
  6) serve() UDP 端到端 dry-run（PING/PONG + 会话流统计 + 未知包容错）
用法：python3 audio_offline_test.py   （需 numpy；在 remote-hub/windows/ 目录下跑）
"""
import os
import socket
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "win_audio_receiver.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(HERE, "win_audio_receiver.py"),
      "__name__": "win_audio_receiver_test"}
exec(compile(src, "win_audio_receiver.py", "exec"), ns)

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, "| got =", repr(got), "| want =", repr(want))


Adpcm = ns["Adpcm"]
upsample = ns["upsample"]
HPF = ns["HPF"]
AGC = ns["AGC"]
Chain = ns["Chain"]

# ---- 1) IMA ADPCM 解码 ----
print("== 1) IMA ADPCM 解码 ==")
check("0x00 -> [0,0]", Adpcm().decode(b"\x00").tolist(), [0, 0])
check("0x07 -> [0,11]（正向增长）", Adpcm().decode(b"\x07").tolist(), [0, 11])
check("0xF0 -> [-11,-9]（负向再回升）", Adpcm().decode(b"\xF0").tolist(), [-11, -9])
check("输出长度 = 2x字节数", len(Adpcm().decode(b"\x00" * 120)), 240)
d1 = Adpcm()
a = d1.decode(b"\x07")
b = d1.decode(b"\x07")
check("状态跨帧连续（第二帧 != 第一帧）", b.tolist() != a.tolist(), True)

# ---- 2) 上采样 ----
print("== 2) 上采样 ==")
r3 = upsample(np.array([0, 3], dtype=np.int16), 3.0)
check("长度 = int(n*ratio)", len(r3), 6)
check("线性插值 [0,1,2,3,3,3]", bool(np.allclose(r3, [0, 1, 2, 3, 3, 3], atol=1e-4)), True)
dc = upsample(np.full(16, 100, dtype=np.int16), 3.0)
check("直流保持", bool(np.allclose(dc, 100.0, atol=1e-3)), True)
check("48000 比率: 240 -> 720", len(upsample(np.zeros(240, dtype=np.int16), 3.0)), 720)
check("44100 比率: 240 -> 661", len(upsample(np.zeros(240, dtype=np.int16), 44100 / 16000.0)), 661)

# ---- 3) HPF（80Hz） ----
print("== 3) HPF（80Hz） ==")
h = HPF(48000, 80.0)
y = h.process(np.ones(48000, dtype=np.float32))
check("直流 50ms 后 <0.05", abs(float(y[2400])) < 0.05, True)
check("直流 1s 后 <0.01", abs(float(y[-1])) < 0.01, True)
h2 = HPF(48000, 80.0)
t = np.arange(4800, dtype=np.float32) / 48000.0
s = np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)
y2 = h2.process(s)
amp = float(np.max(np.abs(y2[2400:])))
check("1kHz 通带保留（amp≈1, ±6%）", abs(amp - 1.0) < 0.06, True)

# ---- 4) AGC ----
print("== 4) AGC ==")
quiet = (np.random.RandomState(7).randn(720) * 0.01).astype(np.float32)
ag = AGC(target=0.2, max_gain=24.0)
yr = None
for _ in range(200):
    yr = ag.process(quiet)
check("小声(0.01 rms)提升后 rms > 0.05", float(np.sqrt(np.mean(yr * yr))) > 0.05, True)
check("增益不超上限 24", ag.gain <= 24.0 + 1e-6, True)
loud = (np.random.RandomState(8).randn(720) * 0.5).astype(np.float32)
ag2 = AGC(target=0.2, max_gain=24.0)
yl = None
for _ in range(100):
    yl = ag2.process(loud)
check("响信号输出峰值 <= 0.95", float(np.max(np.abs(yl))) <= 0.95 + 1e-6, True)
check("增益不低于下限 0.5", ag2.gain >= 0.5 - 1e-6, True)

# ---- 5) Chain 整体 ----
print("== 5) Chain 整体 ==")
c = Chain(48000)
frame = bytes([0x07, 0x87]) * 60          # 上下交替，产生有效交变信号
out = c.feed(frame)
check("输出长度 = 720", len(out), 720)
check("输出范围 [-0.95, 0.95]", bool(np.all(np.abs(out) <= 0.95 + 1e-6)), True)
check("输出无 NaN/Inf", bool(np.all(np.isfinite(out))), True)

# ---- 6) serve() UDP 端到端（dry-run） ----
print("== 6) serve() UDP 端到端（dry-run） ==")
PortT = 18889
chain = Chain(48000)
th = threading.Thread(target=ns["serve"], args=(PortT, True, chain), daemon=True)
th.start()
time.sleep(0.4)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)

s.sendto(b"PING", ("127.0.0.1", PortT))
try:
    r, _ = s.recvfrom(64)
except socket.timeout:
    r = b"<timeout>"
check("PING -> PONG", r, b"PONG")

s.sendto(bytes([0x02, 5]), ("127.0.0.1", PortT))
for _ in range(30):
    s.sendto(bytes([0x01]) + frame, ("127.0.0.1", PortT))
s.sendto(bytes([0x03]), ("127.0.0.1", PortT))
time.sleep(0.6)
st = ns["STATS"]
check("会话计数 = 1", st["sessions"], 1)
check("会话帧数 = 30", st["last_frames"], 30)
check("输出电平 peak > 0", st["last_peak"] > 0.0, True)

s.sendto(b"\x77" * 33, ("127.0.0.1", PortT))   # 未知类型
s.sendto(b"", ("127.0.0.1", PortT))            # 空包
time.sleep(0.2)
s.sendto(b"PING", ("127.0.0.1", PortT))
try:
    r2, _ = s.recvfrom(64)
except socket.timeout:
    r2 = b"<timeout>"
check("未知包/空包后仍存活（PING 通）", r2, b"PONG")
check("未知类型包计数 = 1", ns["STATS"]["fake_frames"], 1)

s.close()
print("")
print("== 结果: %d PASS / %d FAIL ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
