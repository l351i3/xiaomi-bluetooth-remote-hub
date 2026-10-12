#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATVV 接收端 v1.2 (Mac) — 遥控器语音流 → 高通+AGC → BlackHole 虚拟麦克风

v1.2 (2026-10-10 下午) 小声识别增强【依据: 用户实测"小声识别率低 / 开始不行后来可以"】:
  - AGC 增益上限 12 → 24: 实测小声会话峰值增益反复顶满 12（放大被截断、达不到目标电平）;
  - AGC release 0.50s → 0.30s: 起音段收敛更快（改善弱起音/短句）。

v1.1 (2026-10-10) 关键修复【诊断依据: remote-hub/voice-diagnosis-2026-10-10.md】:
  - 80Hz 二阶高通(DC-block): 实测部分会话带巨大直流/低频偏置(最高达满幅50%)，
    把有效语音淹没 → 高通后还原出真实语音(0.02~0.06 rms)
  - 自适应增益 AGC: 目标 RMS 0.2 / 增益上限 12 / 平滑 attack-release + 0.95 限幅,
    解决"有效语音普遍音量偏低(~0.01~0.06 rms)导致识别不稳"
  - --gain 选项已废弃(由 AGC 取代), 仅为兼容旧 plist 保留

链路: T1 atvv_service → UDP :8789 → 本服务 → IMA ADPCM 解码 → 16k→48k
      → HPF(80Hz) → AGC → BlackHole（此后系统"输入设备"=BlackHole）
用法: python3 atvv_receiver.py [--port 8789] [--device blackhole] [--target 0.2] [--hpf 80]
协议: [1B type][payload]: 01=audio帧(120B ADPCM) / 02=会话开始(1B sid) / 03=会话结束
"""
import argparse
import collections
import math
import socket
import threading
import time

import numpy as np
import sounddevice as sd

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
    """有状态 IMA ADPCM 解码器（跨帧连续；会话开始时 reset）"""

    def __init__(self):
        self.reset()

    def reset(self):
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
    """16k -> 48k 线性插值"""
    n = len(x)
    tgt = np.arange(n * RATIO, dtype=np.float32) / RATIO
    return np.interp(tgt, np.arange(n, dtype=np.float32), x.astype(np.float32))


class HPF:
    """二阶 RBJ 高通（Butterworth Q=1/sqrt(2)），状态跨包保持"""

    def __init__(self, sr, fc):
        w0 = 2.0 * math.pi * fc / sr
        cw = math.cos(w0)
        sw = math.sin(w0)
        alpha = sw / (2.0 * 0.70710678)
        b0 = (1.0 + cw) / 2.0
        b1 = -(1.0 + cw)
        b2 = (1.0 + cw) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cw
        a2 = 1.0 - alpha
        self.b0, self.b1, self.b2 = b0 / a0, b1 / a0, b2 / a0
        self.a1, self.a2 = a1 / a0, a2 / a0
        self.reset()

    def reset(self):
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process(self, x):
        out = np.empty(len(x), dtype=np.float32)
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            out[i] = yi
            x2 = x1
            x1 = xi
            y2 = y1
            y1 = yi
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return out


class AGC:
    """按包自适应增益：向目标 RMS 收敛；attack 快 / release 慢，末级 0.95 限幅"""

    def __init__(self, target=0.2, max_gain=24.0, min_gain=0.5, dt=0.015,
                 attack=0.030, release=0.300, smooth=0.150):
        self.target = target
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.a_att = 1.0 - math.exp(-dt / attack)
        self.a_rel = 1.0 - math.exp(-dt / release)
        self.a_sm = 1.0 - math.exp(-dt / smooth)
        self.reset()

    def reset(self):
        self.env = 0.05
        self.gain = 1.0
        self.peak_gain = 1.0

    def process(self, x):
        r = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        a = self.a_att if r > self.env else self.a_rel
        self.env += (r - self.env) * a
        g = self.target / (self.env + 1e-6)
        g = min(max(g, self.min_gain), self.max_gain)
        self.gain += (g - self.gain) * self.a_sm
        self.peak_gain = max(self.peak_gain, self.gain)
        return np.clip(x * self.gain, -0.95, 0.95)


def ts():
    return time.strftime("%H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8789)
    ap.add_argument("--device", default="blackhole")
    ap.add_argument("--gain", type=float, default=None,
                    help="[已废弃] 旧版固定增益；现由 AGC 取代，保留仅为兼容旧 plist")
    ap.add_argument("--target", type=float, default=0.2, help="AGC 目标 RMS")
    ap.add_argument("--hpf", type=float, default=80.0, help="高通截止频率 Hz")
    ap.add_argument("--maxgain", type=float, default=24.0, help="AGC 增益上限")
    args = ap.parse_args()

    devs = sd.query_devices()
    dev_idx = None
    for i, d in enumerate(devs):
        if args.device.lower() in d["name"].lower() and d["max_output_channels"] > 0:
            dev_idx = i
            break
    if dev_idx is None:
        print("!! 找不到输出设备:", args.device)
        for i, d in enumerate(devs):
            print("  [%d] %s  in=%d out=%d" % (i, d["name"], d["max_input_channels"], d["max_output_channels"]))
        return 1
    if args.gain is not None:
        print("[%s] [warn] --gain %.1f 已废弃（由 AGC 取代），本参数被忽略" % (ts(), args.gain))
    print("[%s] 输出设备: [%d] %s (48k, v1.2 HPF=%.0fHz AGC target=%.2f max=%.1f)"
          % (ts(), dev_idx, devs[dev_idx]["name"], args.hpf, args.target, args.maxgain))

    hpf = HPF(SR_OUT, args.hpf)
    agc = AGC(target=args.target, max_gain=args.maxgain)

    lock = threading.Lock()
    q = collections.deque()
    MAXLEN = SR_OUT * 10

    def callback(outdata, frames, tinfo, status):
        with lock:
            take = min(len(q), frames)
            if take:
                chunk = [q.popleft() for _ in range(take)]
                outdata[:take, 0] = np.asarray(chunk, dtype=np.float32)
            if take < frames:
                outdata[take:, 0] = 0.0

    stream = sd.OutputStream(device=dev_idx, samplerate=SR_OUT, channels=1,
                             dtype="float32", blocksize=1024, callback=callback)
    stream.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(0.5)
    print("[%s] 监听 UDP :%d 等待 T1 音频流..." % (ts(), args.port))

    dec = Adpcm()
    streaming = False
    nf = 0
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        if not data:
            continue
        t, payload = data[0], data[1:]
        if t == 0x01:
            if not streaming:
                streaming = True
                dec.reset()
                hpf.reset()
                agc.reset()
                print("[%s] (隐式会话开始)" % ts())
            pcm = dec.decode(payload)
            up = upsample(pcm) / 32768.0
            up = agc.process(hpf.process(up))
            with lock:
                q.extend(up.tolist())
                excess = len(q) - MAXLEN
                if excess > 0:
                    for _ in range(excess):
                        q.popleft()
            nf += 1
        elif t == 0x02:
            streaming = True
            nf = 0
            dec.reset()
            hpf.reset()
            agc.reset()
            print("[%s] 会话开始 sid=%s" % (ts(), payload[0] if payload else "?"))
        elif t == 0x03:
            print("[%s] 会话结束 (%d 帧, AGC峰值增益=%.1f)" % (ts(), nf, agc.peak_gain))
            streaming = False


if __name__ == "__main__":
    main()
