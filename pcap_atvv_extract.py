#!/usr/bin/env python3
# pcap_atvv_extract.py — 从 pcap 提取 ATVV UDP(:8789) 流，按会话重组 + IMA ADPCM 解码成 wav
# 用法: python pcap_atvv_extract.py <file.pcap>
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
SR_IN = 16000
SR_OUT = 48000
RATIO = SR_OUT // SR_IN


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


def read_pcap(path):
    data = open(path, "rb").read()
    if len(data) < 24:
        raise SystemExit("文件太小")
    b = data[:4]
    if b == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif b == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    else:
        raise SystemExit(f"unexpected pcap magic: {b.hex()}")
    off = 24
    pkts = []
    while off + 16 <= len(data):
        ts, tu, incl, _orig = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        pkts.append((ts + tu / 1e6, data[off:off + incl]))
        off += incl
    return pkts


def extract_udp8789(pkt):
    if len(pkt) < 14:
        return None
    eth_type = struct.unpack("!H", pkt[12:14])[0]
    o = 14
    while eth_type == 0x8100 and len(pkt) >= o + 4:
        eth_type = struct.unpack("!H", pkt[o + 2:o + 4])[0]
        o += 4
    if eth_type != 0x0800:
        return None
    ip = pkt[o:]
    if len(ip) < 20 or ip[9] != 17:
        return None
    ihl = (ip[0] & 0x0F) * 4
    udp = ip[ihl:]
    if len(udp) < 8:
        return None
    dport = struct.unpack("!H", udp[2:4])[0]
    if dport != 8789:
        return None
    ulen = struct.unpack("!H", udp[4:6])[0]
    return udp[8:ulen]


def main():
    path = sys.argv[1]
    sessions = []
    cur = None
    n_pkt = 0
    for ts, pkt in read_pcap(path):
        pl = extract_udp8789(pkt)
        if not pl:
            continue
        n_pkt += 1
        t, body = pl[0], pl[1:]
        if t == 0x02:
            cur = {"sid": body[0] if body else -1, "t0": ts, "frames": []}
            sessions.append(cur)
        elif t == 0x01 and cur is not None:
            cur["frames"].append(body)
        elif t == 0x03:
            if cur is not None:
                cur["t1"] = ts
            cur = None
    print(f"pcap 包数(8789): {n_pkt}, 会话数: {len(sessions)}")
    for i, s in enumerate(sessions):
        tstr = _t.strftime("%H:%M:%S", _t.localtime(s["t0"]))
        if not s["frames"]:
            print(f"[{i:02d}] sid={s['sid']} {tstr} — 0 帧")
            continue
        dec = Adpcm()
        pcm = np.concatenate([dec.decode(f) for f in s["frames"]])
        fl = pcm.astype(np.float32) / 32768.0
        up = upsample(fl)
        fn = f"/tmp/atvv_sess_{i:02d}_sid{s['sid']}.wav"
        sf.write(fn, up, SR_OUT)
        seg = int(SR_OUT * 0.5)
        segs = [float(np.sqrt((up[j:j + seg] ** 2).mean())) for j in range(0, len(up), seg)]
        print(f"[{i:02d}] sid={s['sid']} {tstr} dur={len(up)/SR_OUT:.2f}s "
              f"peak={float(np.abs(up).max()):.3f} rms={float(np.sqrt((up**2).mean())):.4f} -> {fn}")
        print("     segs:", " ".join(f"{x:.3f}" for x in segs[:14]))


if __name__ == "__main__":
    main()
