#!/usr/bin/env python3
"""cg_state_probe.py — 查询 HID 系统事件源的修饰键 flags 与按键状态（纯查询，无 TCC 权限要求）。
用途：组合键注入实验（Task#30）/ 排查修饰键悬挂（stuck modifier）。

用法：
  python3 cg_state_probe.py            # 单次采样
  python3 cg_state_probe.py watch 5    # 5 秒内每 0.25s 连续采样

flags 位：SHIFT=1<<17  CTRL=1<<18  OPT=1<<19  CMD=1<<20
"""
import ctypes
import sys
import time

cgh = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
cgh.CGEventSourceFlagsState.restype = ctypes.c_uint64
cgh.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
cgh.CGEventSourceKeyState.restype = ctypes.c_bool
cgh.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]

HID = 1  # kCGEventSourceStateHIDSystemState
_FLAGS = ((1 << 17, 'SHIFT'), (1 << 18, 'CTRL'), (1 << 19, 'OPT'), (1 << 20, 'CMD'))
_KEYS = ((55, 'Cmd_L'), (56, 'Shift_L'), (59, 'Ctrl_L'), (61, 'Opt_R'), (0, 'A'), (8, 'C'))


def sample() -> str:
    f = int(cgh.CGEventSourceFlagsState(HID))
    names = '|'.join(n for m, n in _FLAGS if f & m) or 'none'
    ks = ' '.join(f"{n}={int(cgh.CGEventSourceKeyState(HID, c))}" for c, n in _KEYS)
    return f"flags=0x{f:05x}({names})  {ks}"


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == 'watch':
        dur, t0 = float(sys.argv[2]), time.time()
        while time.time() - t0 < dur:
            print(f"{time.time() - t0:5.2f}s  {sample()}", flush=True)
            time.sleep(0.25)
    else:
        print(sample())


if __name__ == '__main__':
    main()
