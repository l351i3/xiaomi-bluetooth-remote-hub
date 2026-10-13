#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""presence v1.0 离线测试 —— 状态表 / 超时 / 自动切换 / 回切 / 手动检测 /
读端降级 / 损坏隔离 / 重启恢复 / 心跳退避曲线。

全部注入时钟（now 参数），不碰网络、不依赖真实时间。运行:
    python3 presence_test.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import presence          # noqa: E402
import presence_beat     # noqa: E402

PASS = 0
FAIL = 0
TMP = None


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
        print("  [PASS] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s: got=%r want=%r" % (name, got, want))


def beat(p, role, svc, port, ip, t):
    return p.handle(("PRESENCE %s %s %d" % (role, svc, port)).encode(), ip, t)


def new_presence(sub="t1"):
    d = os.path.join(TMP, sub)
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    tp = os.path.join(d, "voice_target")
    with open(tp, "w") as f:
        f.write("mac\n")
    p = presence.Presence(state_path=os.path.join(d, "state", "presence.json"),
                          target_path=tp, log_fn=lambda m: None)
    p.load()
    return p, d, tp


def read_target(tp):
    with open(tp) as f:
        return f.read().strip()


def external_write(tp, val):
    """模拟 webui/终端的外部写入（原子写, 与 webui 同款）"""
    tmp = tp + ".tmp-ext"
    with open(tmp, "w") as f:
        f.write(val + "\n")
    os.replace(tmp, tp)
    time.sleep(0.02)          # 保证 mtime_ns 与上一版不同


def main():
    global TMP
    TMP = tempfile.mkdtemp(prefix="presence-test-")
    try:
        print("== 1. 心跳解析 / 注册 ==")
        p, d, tp = new_presence()
        check("合法心跳应答", beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0), True)
        check("设备上线", p.devices["mac"]["state"], "online")
        check("IP 学习", p.devices["mac"]["ip"], "MACOS_IP")
        check("首次上线置 dirty", p.dirty, True)
        p.write(0.5, force=True)
        check("写后 dirty 复位", p.dirty, False)
        beat(p, "mac", "key", 8791, "MACOS_IP", 0.5)
        check("新服务触发落盘标记", p.dirty, True)
        check("多服务登记", sorted(p.devices["mac"]["svcs"].keys()), ["key", "voice"])
        check("服务端口", p.devices["mac"]["svcs"]["key"]["port"], 8791)
        check("非法 role 拒绝", p.handle(b"PRESENCE tv voice 8788", "10.0.0.9", 0.1), False)
        check("非法端口拒绝", p.handle(b"PRESENCE mac voice 99999", "10.0.0.9", 0.1), False)
        check("垃圾数据拒绝", p.handle(b"HELLO world", "10.0.0.9", 0.1), False)
        check("缺字段拒绝", p.handle(b"PRESENCE mac voice", "10.0.0.9", 0.1), False)

        print("== 2. 快照 / 原子写 / 读端 ==")
        p.write(1.0, force=True)
        sp = os.path.join(d, "state", "presence.json")
        check("快照文件存在", os.path.exists(sp), True)
        check("无 .tmp 残留", os.path.exists(sp + ".tmp"), False)
        snap = presence.read_state(sp, now=1.5)
        check("read_state 可用", snap["devices"]["mac"]["state"], "online")
        check("快照 ttl", snap["ttl"], 6.0)
        check("快照 target", snap["target"], "mac")
        check("过期快照降级", presence.read_state(sp, now=1.5 + 91.0), None)
        check("未来时钟降级", presence.read_state(sp, now=-1000.0), None)

        print("== 3. 超时离线 ==")
        p.tick(5.0)
        check("5s 仍在线上", p.devices["mac"]["state"], "online")
        p.tick(7.0)
        check("7s 判离线", p.devices["mac"]["state"], "offline")
        check("离线事件留痕", any("离线" in e[2] for e in p.events), True)

        print("== 4. 自动切换（离线 12s 确认 + 优先级） ==")
        p, d, tp = new_presence("switch")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        for t in (0.0, 6.0, 12.0, 18.0):        # 替身持续拍（真实节奏 2s/拍）
            beat(p, "win", "voice", 8788, "WINDOWS_IP", t)
            beat(p, "atv", "relay", 0, "127.0.0.1", t)
        p.tick(1.0)
        check("初始目标", p.target, "mac")
        # mac 停拍: 7s 判离线（since=7）, 19s(+12) 前不切, 19.5s 切
        p.tick(7.0)
        check("7s 判离线", p.devices["mac"]["state"], "offline")
        p.tick(18.9)
        check("12s 确认期内不切", p.target, "mac")
        p.tick(19.5)
        check("确认后切到 win", p.target, "win")
        check("auto=True", p.auto, True)
        check("desired 记忆 mac", p.desired, "mac")
        check("voice_target 文件已写", read_target(tp), "win")
        check("切换事件留痕", any("自动切到" in e[2] for e in p.events), True)

        print("== 5. 回切（desired 连续在线 10s） ==")
        for t in (20.0, 26.0, 32.0, 38.0):      # 替身持续在线
            beat(p, "win", "voice", 8788, "WINDOWS_IP", t)
            beat(p, "atv", "relay", 0, "127.0.0.1", t)
        beat(p, "mac", "voice", 8788, "MACOS_IP", 30.0)   # mac 回归
        beat(p, "mac", "voice", 8788, "MACOS_IP", 36.0)   # 回归后持续拍
        p.tick(39.5)
        check("未满 10s 不回切", p.target, "win")
        p.tick(40.5)
        check("10s 后回切 mac", p.target, "mac")
        check("auto 复位", p.auto, False)

        print("== 6. 手动切换检测 ==")
        p, d, tp = new_presence("manual")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        beat(p, "win", "voice", 8788, "WINDOWS_IP", 0.0)
        p.tick(1.0)
        external_write(tp, "win")
        p.tick(2.0)
        check("外部写入识别为手动", p.target, "win")
        check("desired 更新", p.desired, "win")
        check("auto 清除", p.auto, False)

        print("== 6b. 自动替身 + 用户重申替身 -> 不回切 ==")
        p, d, tp = new_presence("manual2")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        for t in (0.0, 6.0, 12.0, 18.0, 24.0):  # win 持续在线
            beat(p, "win", "voice", 8788, "WINDOWS_IP", t)
        p.tick(1.0)
        p.tick(7.0)                             # mac 离线
        p.tick(19.5)                            # 切到 win
        check("自动切到 win", (p.target, p.auto), ("win", True))
        external_write(tp, "win")               # 用户手动重申 win（同内容）
        p.tick(20.5)
        check("重申后 auto 清除", (p.desired, p.auto), ("win", False))
        beat(p, "mac", "voice", 8788, "MACOS_IP", 30.0)   # mac 回归
        for t in (30.0, 36.0, 42.0):
            beat(p, "win", "voice", 8788, "WINDOWS_IP", t)
        p.tick(41.0)
        check("手动选择后不回切", p.target, "win")

        print("== 7. 无可替代设备时不切 ==")
        p, d, tp = new_presence("nosub")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        p.tick(7.0)
        p.tick(20.0)
        check("无在线设备保持原目标", (p.target, p.auto), ("mac", False))
        check("文件未被改", read_target(tp), "mac")

        print("== 8. 未知设备不切（从未见过） ==")
        p, d, tp = new_presence("unknown")
        p.tick(100.0)
        check("未知目标不触发切换", (p.target, p.auto), ("mac", False))

        print("== 9. IP 漂移（心跳学习） ==")
        p, d, tp = new_presence("ipdrift")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        p.write(1.0, force=True)
        beat(p, "mac", "voice", 8788, "LAN_IP", 2.0)   # DHCP 换地址
        check("IP 更新", p.devices["mac"]["ip"], "LAN_IP")
        check("IP 漂移触发落盘", p.dirty, True)

        print("== 10. StateView / 投递闸门视角 ==")
        p, d, tp = new_presence("view")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        p.write(0.5, force=True)
        sp = os.path.join(d, "state", "presence.json")
        v = presence.StateView(path=sp, refresh=0.0, max_age=presence.STATE_MAX_AGE)
        check("view 在线", v.device_state("mac", now=1.0), "online")
        check("view IP", v.ip_of("mac", now=1.0), "MACOS_IP")
        check("view 未知设备", v.device_state("win", now=1.0), "unknown")
        check("守护失效降级", v.device_state("mac", now=1.0 + 91.0), "unknown")
        check("文件缺失降级", presence.StateView(path=sp + ".nope").device_state("mac"), "unknown")

        print("== 11. 损坏隔离 / 重启恢复 ==")
        p, d, tp = new_presence("resil")
        beat(p, "mac", "voice", 8788, "MACOS_IP", 0.0)
        for t in (0.0, 6.0, 12.0, 18.0):
            beat(p, "win", "voice", 8788, "WINDOWS_IP", t)
        p.tick(1.0)
        p.tick(7.0)
        p.tick(19.5)
        check("切入 win(恢复前)", (p.target, p.auto), ("win", True))
        p.write(20.0, force=True)
        sp = os.path.join(d, "state", "presence.json")
        p2 = presence.Presence(state_path=sp, target_path=tp, log_fn=lambda m: None)
        p2.load()
        check("desired 恢复", p2.desired, "mac")
        check("auto 恢复", p2.auto, True)
        check("设备恢复为先离线", p2.devices["mac"]["state"], "offline")
        check("目标恢复", p2.target, "win")
        # 损坏文件隔离
        with open(sp, "w") as f:
            f.write("{broken json")
        p3 = presence.Presence(state_path=sp, target_path=tp, log_fn=lambda m: None)
        p3.load()
        bads = [x for x in os.listdir(os.path.dirname(sp)) if ".bad-" in x]
        check("损坏文件已隔离", len(bads), 1)
        check("隔离后空表启动", p3.devices, {})

        print("== 12. 心跳退避曲线 ==")
        check("0 拍 -> 2s", presence_beat.next_interval(0), 2.0)
        check("1 拍 -> 4s", presence_beat.next_interval(1), 4.0)
        check("2 拍 -> 8s", presence_beat.next_interval(2), 8.0)
        check("3 拍 -> 15s", presence_beat.next_interval(3), 15.0)
        check("4 拍 -> 15s 封顶", presence_beat.next_interval(4), 15.0)
        check("role 描述", presence_beat.Heartbeat("win", [("voice", 8788)]).role, "win")

        print()
        print("presence_test: %d PASS / %d FAIL" % (PASS, FAIL))
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
