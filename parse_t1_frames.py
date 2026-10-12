#!/usr/bin/env python3
# parse_t1_frames.py — 解析 t1_sniff.py 输出：会话重组 + IMA ADPCM 解码 + 电平画像
# 用法: python parse_t1_frames.py /tmp/atvv_frames.bin
import struct
import sys
import time as _t

import numpy as np
import soundfile as sf

STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
]
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8]
SR_OUT = 48000
RATIO = 3


class Adpcm:
    def __init__(self):
        self.pred = 0
        self.idx = 0

    def decode(self, data):
        out = np.empty(len(data) * 2, dtype=np.int16)
        k = 0
        pred, idx = self.pred, self.idx
        for b in data:
            for nib in (b >> 4, b & 0x0F):
                step = STEP_TABLE[idx]
                diff = step >> 3
                if nib & 4:
                    diff += step
                if nib & 2:
                    diff += step >> 1
                if nib & 1:
                    diff += step >> 2
                if nib & 8:
                    pred -= diff
                else:
                    pred += diff
                if pred > 32767:
                    pred = 32767
                elif pred < -32768:
                    pred = -32768
                idx += INDEX_TABLE[nib & 7]
                if idx < 0:
                    idx = 0
                elif idx > 88:
                    idx = 88
                out[k] = pred
                k += 1
        self.pred, self.idx = pred, idx
        return out


def upsample(x):
    n = len(x)
    tgt = np.arange(n * RATIO, dtype=np.float32) / RATIO
    return np.interp(tgt, np.arange(n, dtype=np.float32), x)


def main():
    path = sys.argv[1]
    data = open(path, "rb").read()
    if len(data) < 16 or data[:8] != b"T1SNIFF1":
        raise SystemExit("bad sniff file")
    epoch, = struct.unpack(">d", data[8:16])
    off = 16
    recs = []
    while off + 6 <= len(data):
        ms, ln = struct.unpack(">IH", data[off:off + 6])
        off += 6
        recs.append((ms, data[off:off + ln]))
        off += ln
    print(f"记录数: {len(recs)}  (抓包起点 epoch={epoch:.0f} {_t.strftime('%m-%d %H:%M:%S', _t.localtime(epoch))})")

    sessions = []
    cur = None
    for ms, pl in recs:
        if not pl:
            continue
        t, b = pl[0], pl[1:]
        if t == 0x02:
            cur = {"sid": b[0] if b else -1, "t0": epoch + ms / 1000, "frames": []}
            sessions.append(cur)
        elif t == 0x01 and cur is not None:
            cur["frames"].append(b)
        elif t == 0x03:
            if cur is not None:
                cur["t1"] = epoch + ms / 1000
            cur = None

    print(f"会话数: {len(sessions)}")
    for i, s in enumerate(sessions):
        tstr = _t.strftime("%H:%M:%S", _t.localtime(s["t0"]))
        if not s["frames"]:
            print(f"[{i:02d}] sid={s['sid']} {tstr} — 0 帧")
            continue
        dec = Adpcm()
        pcm = np.concatenate([dec.decode(f) for f in s["frames"]])
        fl = pcm.astype(np.float32) / 32768.0
        up = upsample(fl)
        fn = f"/tmp/t1_sess_{i:02d}_sid{s['sid']}.wav"
        sf.write(fn, up, SR_OUT)
        seg = SR_OUT // 2
        segs = [float(np.sqrt((up[j:j + seg] ** 2).mean())) for j in range(0, len(up), seg)]
        print(f"[{i:02d}] sid={s['sid']} {tstr} frames={len(s['frames'])} dur={len(up)/SR_OUT:.2f}s "
              f"peak={float(np.abs(up).max()):.3f} rms={float(np.sqrt((up**2).mean())):.4f} -> {fn}")
        print("     segs:", " ".join(f"{x:.3f}" for x in segs[:16]))


if __name__ == "__main__":
    main()
