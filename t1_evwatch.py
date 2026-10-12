#!/usr/bin/env python3
# t1_evwatch.py - T1 输入设备按键观测器（只读，不 grab）
#
# 用途: 电源键来源判定实验。记录所有 input 设备的按键事件（含设备名归属），
#       让"哪个设备发出了 KEY_POWER"可判定。
# 设计:
#   - 只读打开 /dev/input/event*（不 EVIOCGRAB），不干扰系统正常处理 —— 测真实行为
#   - 动态发现新设备（遥控器回连时 uhid 会新建 event 节点）
#   - 每条事件立即 flush 落盘；优先写 /var/log.hdd/（物理盘，断电不丢），
#     不可写时退回 /var/log/（tmpfs，靠 armbian-ramlog 关机会同步）
#   - 记录除 EV_SYN 外所有事件类型（EV_KEY/EV_MSC 等），KEY 类附键名
import glob, os, select, struct, sys, time

CAND_OUT = ['/var/log.hdd/t1-evwatch.log', '/var/log/t1-evwatch.log']
KEY_NAMES = {
    116: 'KEY_POWER', 142: 'KEY_SLEEP', 143: 'KEY_WAKEUP', 152: 'KEY_COFFEE',
    102: 'KEY_HOME', 158: 'KEY_BACK', 139: 'KEY_MENU', 172: 'KEY_HOMEPAGE',
    115: 'KEY_VOLUMEUP', 114: 'KEY_VOLUMEDOWN', 113: 'KEY_MUTE',
    217: 'KEY_SEARCH', 240: 'KEY_UNKNOWN240', 28: 'KEY_ENTER',
}

def pick_out():
    for p in CAND_OUT:
        try:
            with open(p, 'a') as f:
                f.write('')
            return p
        except Exception:
            continue
    return '/dev/null'

OUT = pick_out()

def log(msg):
    line = time.strftime('%F %T') + ' ' + msg
    try:
        with open(OUT, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass
    print(line, flush=True)

def dev_name(ev):
    try:
        with open('/sys/class/input/' + os.path.basename(ev) + '/device/name') as f:
            return f.read().strip()
    except Exception:
        return '?'

def main():
    log(f'=== evwatch START (out={OUT}) ===')
    fds = {}
    def refresh():
        for ev in sorted(glob.glob('/dev/input/event*')):
            if ev in fds:
                continue
            try:
                fds[ev] = open(ev, 'rb', buffering=0)
                log(f'open {ev} [{dev_name(ev)}]')
            except Exception as e:
                log(f'open-fail {ev}: {e}')
    refresh()
    last_refresh = time.time()
    while True:
        try:
            r, _, _ = select.select(list(fds.values()), [], [], 2.0)
            for f in r:
                ev = f.name
                data = f.read(24)
                if not data or len(data) < 24:
                    continue
                _sec, _usec, etype, code, val = struct.unpack('llHHi', data[:24])
                if etype == 0:  # EV_SYN skip
                    continue
                if etype == 1:
                    kn = KEY_NAMES.get(code, f'key{code}')
                    log(f'KEY {ev} [{dev_name(ev)}] code={code}({kn}) value={val}')
                else:
                    log(f'EVT {ev} [{dev_name(ev)}] type={etype} code={code} value={val}')
        except Exception as e:
            # v2: HOG 设备重建（节点日志里 event2 被删除后同名重建）会让旧 fd
            # 永久失效；原版只 log 不清 fd -> 死循环报错。改为全量重开。
            log(f'ERR loop: {e} -> reopen all fds')
            for f in list(fds.values()):
                try:
                    f.close()
                except Exception:
                    pass
            fds.clear()
            refresh()
            last_refresh = time.time()
            time.sleep(0.5)
        if time.time() - last_refresh > 2:
            refresh()
            last_refresh = time.time()

if __name__ == '__main__':
    main()
