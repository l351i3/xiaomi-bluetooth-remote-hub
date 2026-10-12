#!/usr/bin/env python3
# bh_stream_rec.py — 分段连续录 BlackHole（每段20s存一个wav，随时kill不丢已完成段）
# 用法: python bh_stream_rec.py [每段秒数] [输出目录]
import os
import sys
import time
import wave

import numpy as np
import sounddevice as sd

seg = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/bh_seg"
os.makedirs(outdir, exist_ok=True)

devs = sd.query_devices()
idx = None
for i, d in enumerate(devs):
    if "blackhole" in d["name"].lower() and d["max_input_channels"] > 0:
        idx = i
        break
if idx is None:
    print("!! 找不到 BlackHole 输入设备")
    sys.exit(1)

sr = 48000
print(f"开始分段录制 BlackHole: 每段{seg:.0f}s -> {outdir}", flush=True)
n = 0
while True:
    rec = sd.rec(int(seg * sr), samplerate=sr, channels=1, device=idx, dtype="float32")
    sd.wait()
    n += 1
    f = f"{outdir}/seg_{n:03d}.wav"
    pcm = (np.clip(rec[:, 0], -1, 1) * 32767).astype(np.int16)
    with wave.open(f, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    print(f"{time.strftime('%H:%M:%S')} wrote {f} peak={np.abs(rec).max():.4f} rms={np.sqrt((rec**2).mean()):.5f}", flush=True)
