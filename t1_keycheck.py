#!/usr/bin/env python3
# 检查每个输入设备能否发出 KEY_POWER(116) 等电源类按键
# 用途：核查 2026-10-08 12:31:47 "Power key pressed" 事件的候选来源设备
import glob

KEY_CHECK = [116, 142, 143, 152]
NAMES = {
    116: 'KEY_POWER(116)',
    142: 'KEY_SLEEP(142)',
    143: 'KEY_WAKEUP(143)',
    152: 'KEY_COFFEE(152)',
}

for e in sorted(glob.glob('/sys/class/input/event*')):
    devname = '?'
    try:
        with open(e + '/device/name') as f:
            devname = f.read().strip()
    except OSError:
        pass
    bits = set()
    try:
        with open(e + '/device/capabilities/key') as f:
            words = f.read().split()
        words = list(reversed(words))  # 内核从高位字开始打印
        for i, w in enumerate(words):
            v = int(w, 16)
            for b in range(64):
                if (v >> b) & 1:
                    bits.add(i * 64 + b)
    except OSError:
        pass
    hits = [NAMES[k] for k in KEY_CHECK if k in bits]
    print(f"{e} [{devname}] total_keys={len(bits)} -> {', '.join(hits) if hits else '（无电源类键）'}")
