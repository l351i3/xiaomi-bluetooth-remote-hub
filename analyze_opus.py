#!/usr/bin/env python3
# analyze_opus.py — 解码 opus 录音并输出电平画像（区分"真语音" vs "静音/极低电平"）
# 用法: python analyze_opus.py <file1.opus> [file2.opus ...]
import sys

import numpy as np
import soundfile as sf

for f in sys.argv[1:]:
    try:
        d, sr = sf.read(f, dtype="float32")
        if d.ndim > 1:
            d = d.mean(axis=1)
        n = len(d)
        dur = n / sr if sr else 0
        peak = float(np.abs(d).max()) if n else 0
        rms = float(np.sqrt((d ** 2).mean())) if n else 0
        # 每 0.5s 一段 RMS，看能量结构
        seg = int(sr * 0.5)
        segs = [float(np.sqrt((d[i:i + seg] ** 2).mean())) for i in range(0, n, seg)] if seg else []
        loud = sum(1 for x in segs if x > 0.01)
        segs_s = " ".join(f"{x:.3f}" for x in segs[:16])
        print(f"== {f.split('/')[-1]}")
        print(f"   sr={sr} dur={dur:.2f}s peak={peak:.4f} rms={rms:.5f}")
        print(f"   0.5s段RMS(前16段): {segs_s}")
        print(f"   >0.01的段: {loud}/{len(segs)}")
    except Exception as e:
        print(f"== {f.split('/')[-1]}  ERR: {e}")
