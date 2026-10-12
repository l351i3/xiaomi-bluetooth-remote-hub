#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATVV 抓流日志 → IMA ADPCM 解码 → WAV（Mac 本地）
格式依据: 16kHz mono 16-bit, IMA ADPCM 4-bit, 每帧120B=240样本, 高nibble先
用法: python3 atvv_decode.py [日志文件=atvv-probe-2026-10-09.log]
输出: atvv-voice-1.wav / 2 / 3 ... + .raw (原始拼接)
"""
import re
import sys
import wave

STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
]
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8]


def decode_ima_adpcm(data: bytes) -> list:
    """标准 IMA ADPCM 解码; 每会话从 predictor=0/index=0 起步(遥控器会重置)"""
    out = []
    predictor = 0
    index = 0
    for b in data:
        for nibble in (b >> 4, b & 0x0F):          # 高 4 位先
            step = STEP_TABLE[index]
            diff = step >> 3
            if nibble & 4:
                diff += step
            if nibble & 2:
                diff += step >> 1
            if nibble & 1:
                diff += step >> 2
            if nibble & 8:
                predictor -= diff
            else:
                predictor += diff
            if predictor > 32767:
                predictor = 32767
            elif predictor < -32768:
                predictor = -32768
            index += INDEX_TABLE[nibble & 7]
            if index < 0:
                index = 0
            elif index > 88:
                index = 88
            out.append(predictor)
    return out


def parse_log(path):
    """解析探针日志 → [(sid, t_start, [pkt,...]), ...]"""
    re_audio = re.compile(r"\[\s*([\d.]+)s\] AUDIO \((\d+)B\): ([0-9a-f ]+)")
    re_start = re.compile(r"\[\s*([\d.]+)s\] CTRL \(4B\): 04 03 02 ([0-9a-f]{2})")
    re_stop = re.compile(r"\[\s*([\d.]+)s\] CTRL \(2B\): 00 02")

    sessions = []
    cur = None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re_start.search(line)
        if m:
            cur = {"sid": int(m.group(2), 16), "t0": float(m.group(1)), "pkts": [], "t_end": None}
            sessions.append(cur)
            continue
        m = re_audio.search(line)
        if m and cur is not None:
            cur["pkts"].append(bytes.fromhex(m.group(3).replace(" ", "")))
            continue
        m = re_stop.search(line)
        if m and cur is not None:
            cur["t_end"] = float(m.group(1))
            cur = None
    return sessions


def rms(samples):
    if not samples:
        return 0.0
    s = sum(x * x for x in samples)
    return (s / len(samples)) ** 0.5


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "atvv-probe-2026-10-09.log"
    sessions = parse_log(path)
    if not sessions:
        print("!! 未解析到任何会话（检查日志格式）")
        return 1

    print(f"共 {len(sessions)} 个会话:")
    for i, s in enumerate(sessions, 1):
        raw = b"".join(s["pkts"])
        open(f"atvv-voice-{i}.raw", "wb").write(raw)
        pcm = decode_ima_adpcm(raw)
        dur = len(pcm) / 16000.0
        r = rms(pcm)
        t_end = s["t_end"] if s["t_end"] else 0
        wall = t_end - s["t0"]
        print(f"  会话{i}: SID={s['sid']} 包数={len(s['pkts'])} raw={len(raw)}B "
              f"→ PCM={len(pcm)}样本（{dur:.2f}s @16k） wall={wall:.2f}s "
              f"帧间隔≈{wall/max(len(s['pkts']),1)*1000:.1f}ms RMS={r:.0f}")
        with wave.open(f"atvv-voice-{i}.wav", "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"".join(int(x).to_bytes(2, "little", signed=True) for x in pcm))
    print("已输出:", ", ".join(f"atvv-voice-{i}.wav" for i in range(1, len(sessions) + 1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
