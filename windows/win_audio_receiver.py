#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""remotehub-win audio receiver v1.0 — Windows 遥控器语音 → 虚拟声卡（Windows）

链路: RC003 遥控器 MIC → (BLE/ATVV) → T1 atvv_service → UDP:8789 → 本服务
      → IMA ADPCM 解码 → 16k→设备采样率 上采样 → HPF(80Hz) → AGC → "CABLE Input"
      （微信输入法从 "CABLE Output" 读：把输入法麦克风设为 CABLE Output 即可）

配套: T1 侧 atvv_service v1.1 双目标发送（Mac MACOS_IP + Windows WINDOWS_IP）

依赖:
  pip install numpy sounddevice
  + 虚拟声卡 VB-Audio Virtual Cable（免费, https://vb-audio.com/Cable/）:
    安装后出现 "CABLE Input"（播放端, 本服务往里写）/ "CABLE Output"（录音端, 输入法读）

用法（Windows 上）:
  python  win_audio_receiver.py              # 默认: 输出到 CABLE Input, 端口 8789
  python  win_audio_receiver.py --list       # 列出所有音频设备后退出
  python  win_audio_receiver.py --dry-run    # 不开声卡, 只验证收包+解码（链路诊断, 需先停正常实例）
  python  win_audio_receiver.py --debug      # 控制台打印收包明细
  pythonw win_audio_receiver.py              # 后台无窗口运行（开机自启用这个）

协议 (T1 -> 本机, [1B type][payload], 与 Mac 端 atvv_receiver.py 完全一致):
  0x01 音频帧(120B IMA ADPCM) / 0x02 会话开始(1B sid) / 0x03 会话结束
  "PING" -> 回 "PONG"（连通性自检）
"""
import argparse
import collections
import math
import os
import queue
import socket
import sys
import threading
import time

try:
    import numpy as np
except ImportError:
    print("FATAL: numpy is required.  Please run:  pip install numpy sounddevice")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "audio_receiver.log")
DEBUG = "--debug" in sys.argv

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
FRAME_MS = 0.015          # 每帧 240 样本 @16k = 15ms（AGC 时间常数以此为基准）

# 会话统计（离线测试可读）
STATS = {"sessions": 0, "fake_frames": 0, "last_frames": 0, "last_peak": 0.0}


# ---------------- 日志（异步队列 + 句柄常开，与 win_receiver v1.1 同款） ----------------
_LOGQ = queue.Queue(maxsize=4000)


def _log_worker():
    """独立线程消费日志队列；文件句柄常开（行缓冲）。写失败自动重开。"""
    f = None
    while True:
        line = _LOGQ.get()
        if f is None:
            try:
                f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
            except Exception:
                f = None
                time.sleep(0.5)
                continue          # 本次消息丢弃，下次再试
        try:
            f.write(line + "\n")
        except Exception:
            try:
                f.close()
            except Exception:
                pass
            f = None


threading.Thread(target=_log_worker, daemon=True, name="log-worker").start()


def log(msg, also_console=False):
    """只做入队（µs 级返回），绝不阻塞调用线程。"""
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    if DEBUG or also_console:
        try:
            print(line, flush=True)
        except Exception:
            pass
    try:
        _LOGQ.put_nowait(line)
    except queue.Full:
        pass                      # 保链路优先：日志可丢弃


# ---------------- 解码链（自 Mac 端 atvv_receiver.py v1.2 移植） ----------------
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


def upsample(x, ratio):
    """16k -> 设备采样率 线性插值（输出长度 = int(len(x) * ratio)）"""
    n = len(x)
    m = int(n * ratio)
    tgt = np.arange(m, dtype=np.float32) / ratio
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

    def __init__(self, target=0.2, max_gain=24.0, min_gain=0.5, dt=FRAME_MS,
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


class Chain:
    """解码链打包: decode -> upsample -> HPF -> AGC（状态跨帧保持；测试友好）"""

    def __init__(self, rate, hpf_fc=80.0, agc_target=0.2, agc_max=24.0):
        self.rate = rate
        self.ratio = rate / float(SR_IN)
        self.dec = Adpcm()
        self.hpf = HPF(rate, hpf_fc)
        self.agc = AGC(target=agc_target, max_gain=agc_max)

    def reset(self):
        self.dec.reset()
        self.hpf.reset()
        self.agc.reset()

    def feed(self, payload):
        pcm = self.dec.decode(payload)
        up = upsample(pcm, self.ratio) / 32768.0
        return self.agc.process(self.hpf.process(up))


# ---------------- UDP 收包主循环（dry-run 与生产共用；测试可直接调） ----------------
def serve(port, dry, chain, q=None, lock=None, dev_name="?"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
    except Exception:
        pass
    try:
        # 不设 SO_REUSEADDR：防止双实例同时绑定造成"幽灵双收"，
        # 第二个实例会 bind 失败并明确退出（日志 FATAL，属正常保护）。
        sock.bind(("0.0.0.0", port))
    except OSError as e:
        log("FATAL bind udp :%d failed: %s (another instance running?)" % (port, e),
            also_console=True)
        os._exit(1)
    sock.settimeout(0.5)
    log("listening udp :%d (dry_run=%s, out=%s)" % (port, dry, dev_name), also_console=True)

    streaming = False
    nf = 0
    peak = 0.0
    sid = "?"
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError as e:
            log("recv error: %s" % e)
            continue
        if not data:
            continue
        if data == b"PING":
            try:
                sock.sendto(b"PONG", addr)
            except OSError as e:
                log("PONG send error: %s" % e)
            continue
        if DEBUG:
            log("RX %s:%d len=%d type=0x%02X" % (addr[0], addr[1], len(data), data[0]))
        t, payload = data[0], data[1:]
        if t == 0x01:
            if not streaming:              # 隐式会话开始（0x02 丢失兜底）
                streaming = True
                sid = "?"
                nf = 0
                peak = 0.0
                chain.reset()
                STATS["sessions"] += 1
            out = chain.feed(payload)
            if dry:
                r = float(np.sqrt(np.mean(out * out))) if len(out) else 0.0
                if r > peak:
                    peak = r
            elif q is not None:
                with lock:
                    q.extend(out.tolist())
            nf += 1
        elif t == 0x02:
            streaming = True
            sid = payload[0] if payload else "?"
            nf = 0
            peak = 0.0
            chain.reset()
            STATS["sessions"] += 1
            log("session start sid=%s" % sid)
        elif t == 0x03:
            STATS["last_frames"] = nf
            STATS["last_peak"] = peak if dry else chain.agc.peak_gain
            log("session end sid=%s frames=%d %s" % (
                sid, nf,
                ("out_rms_peak=%.3f" % peak) if dry
                else ("agc_peak_gain=%.1f" % chain.agc.peak_gain)))
            streaming = False
        else:
            STATS["fake_frames"] += 1


# ---------------- sounddevice 辅助 ----------------
def _import_sd():
    try:
        import sounddevice as sd
    except Exception as e:
        print("FATAL: sounddevice not available (%s)." % e)
        print("Please run:  pip install numpy sounddevice")
        sys.exit(1)
    return sd


def list_devices(sd):
    try:
        devs = sd.query_devices()
    except Exception as e:
        print("query devices failed: %s" % e)
        return 1
    print("idx  name                                             out  in  default_rate")
    for i, d in enumerate(devs):
        if d["max_output_channels"] > 0 or d["max_input_channels"] > 0:
            print("%3d  %-48s %3d %3d  %.0f" % (
                i, d["name"][:48], d["max_output_channels"],
                d["max_input_channels"], d["default_samplerate"]))
    return 0


def find_output(sd, key):
    for i, d in enumerate(sd.query_devices()):
        if key.lower() in d["name"].lower() and d["max_output_channels"] > 0:
            return i, d
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8789)
    ap.add_argument("--device", default="cable input",
                    help="输出设备名（模糊匹配; 默认 cable input = VB-Cable 虚拟声卡）")
    ap.add_argument("--rate", type=int, default=0, help="输出采样率（0=跟随设备默认）")
    ap.add_argument("--target", type=float, default=0.2, help="AGC 目标 RMS")
    ap.add_argument("--hpf", type=float, default=80.0, help="高通截止频率 Hz")
    ap.add_argument("--maxgain", type=float, default=24.0, help="AGC 增益上限")
    ap.add_argument("--dry-run", action="store_true",
                    help="不开声卡，只验证收包+解码链（链路诊断）")
    ap.add_argument("--list", action="store_true", help="列出所有音频设备后退出")
    args = ap.parse_args()

    log("=== remotehub-win audio receiver v1.0 starting ===", also_console=True)
    log("python=%s user=%s host=%s dir=%s" % (
        sys.version.split()[0], os.environ.get("USERNAME", "?"),
        socket.gethostname(), HERE), also_console=True)

    if args.list:
        sd = _import_sd()
        return list_devices(sd)

    if not args.dry_run:
        sd = _import_sd()
        dev_idx, dev = find_output(sd, args.device)
        if dev_idx is None:
            log("!! output device not found: %r" % args.device, also_console=True)
            log("   install VB-Audio Virtual Cable first: https://vb-audio.com/Cable/",
                also_console=True)
            list_devices(sd)
            return 1
        rate = args.rate or int(round(dev["default_samplerate"]))
        log("output device: [%d] %s rate=%dHz" % (dev_idx, dev["name"], rate),
            also_console=True)
    else:
        rate = args.rate or 48000
        log("dry-run mode: no audio output (rate=%d for stats only)" % rate,
            also_console=True)

    chain = Chain(rate, hpf_fc=args.hpf, agc_target=args.target, agc_max=args.maxgain)

    if args.dry_run:
        try:
            serve(args.port, True, chain)
        except KeyboardInterrupt:
            log("stopped by user (dry-run)")

        return 0

    q = collections.deque(maxlen=rate * 10)      # 最多缓存 10 秒音频
    lock = threading.Lock()

    def callback(outdata, frames, tinfo, status):
        with lock:
            take = min(len(q), frames)
            if take:
                chunk = [q.popleft() for _ in range(take)]
                outdata[:take, 0] = np.asarray(chunk, dtype=np.float32)
            if take < frames:
                outdata[take:, 0] = 0.0

    try:
        stream = sd.OutputStream(device=dev_idx, samplerate=rate, channels=1,
                                 dtype="float32", blocksize=1024, callback=callback)
        stream.start()
    except Exception as e:
        log("FATAL cannot open output device [%d] %s @%dHz: %s"
            % (dev_idx, dev["name"], rate, e), also_console=True)
        return 1

    try:
        serve(args.port, False, chain, q=q, lock=lock, dev_name=dev["name"])
    except KeyboardInterrupt:
        log("stopped by user")

    return 0


if __name__ == "__main__":
    sys.exit(main())
