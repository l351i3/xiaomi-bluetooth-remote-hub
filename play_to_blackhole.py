#!/usr/bin/env python3
# play_to_blackhole.py — 把音频文件播放进 BlackHole（虚拟麦），供 App 录音
# 用法: python play_to_blackhole.py <audiofile> [device_substr]
import sys

import numpy as np
import soundfile as sf
import sounddevice as sd

f = sys.argv[1]
want = sys.argv[2] if len(sys.argv) > 2 else "blackhole"

d, sr = sf.read(f, dtype="float32")
if d.ndim > 1:
    d = d.mean(axis=1)

devs = sd.query_devices()
idx = None
for i, x in enumerate(devs):
    if want.lower() in x["name"].lower() and x["max_output_channels"] > 0:
        idx = i
        break
if idx is None:
    print("!! 找不到输出设备:", want)
    sys.exit(1)

print(f"play {f}  sr={sr}  dur={len(d)/sr:.2f}s  -> [{idx}] {devs[idx]['name']}")
sd.play(d, sr, device=idx)
sd.wait()
print("play done")
