#!/usr/bin/env python3
# record_blackhole.py — 录 BlackHole 虚拟麦信号到 WAV（验证音频通路用）
# 用法: python record_blackhole.py [秒数] [输出wav]
import sys
import wave

import numpy as np
import sounddevice as sd

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/blackhole_rec.wav"

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
print(f"录制 {secs:.0f}s -> {out} (dev[{idx}] {devs[idx]['name']})")
rec = sd.rec(int(secs * sr), samplerate=sr, channels=1, device=idx, dtype="float32")
sd.wait()
peak = float(np.max(np.abs(rec))) if rec.size else 0.0
rms = float(np.sqrt(np.mean(rec.astype(np.float64) ** 2))) if rec.size else 0.0
with wave.open(out, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((np.clip(rec, -1, 1) * 32767).astype("<i2").tobytes())
print(f"峰值 {peak:.4f} / RMS {rms:.5f} -> {out}")
if peak > 0.001:
    print(">> 有信号!")
else:
    print(">> 近乎静音")
