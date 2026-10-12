#!/usr/bin/env python3
# voice_bridge.py — Mac 端「语音键」桥接服务 v0.9
# ---------------------------------------------------------------
# 监听 UDP :8788, 收到 "VOICE down" / "VOICE up" 指令后, 经 launchctl
# submit 提交「一次性注入 job」(唯一 label) 完成 HID 事件注入,
# 唤起 Chatterfly 语音输入。
#
# v0.9 变更（2026-10-10）: 录音状态闭环（补发 + 低频自愈）。
#   【背景】实测发现 Chatterfly 会把"间隔过近的注入 tap"静默丢弃（0.15s 间隔
#   丢弃, ≥3s 稳定生效），导致 ①误点一下 → 其"收尾 tap"被丢 → 录音悬挂、
#   下一次长按被反相（不出字）; ②快速连按 → 开始 tap 被丢 → 本次按压无声失败。
#   【信号】实测: 录音开始即创建 audio_<起始ms>_*.opus 并持续写入, 停止即冻结
#   → 用"最新文件 mtime 新鲜 / 体积增长"实时判断录音是否开着 (FSTracker)。
#   【闭环】每 ≤0.5s 比对"期望状态"(按压中=应录 / 空闲=应停) 与 FS 实测:
#     · 按压中却没录 → 每 ≥2.5s 补发『开始』(至多 2 次)
#     · 空闲却还在录 → 每 ≥3.5s 补发『结束』(至多 3 次; 仍不收敛则 6s/次
#       低频自愈, 且仅限最近 60s 内有过按压, 防误伤外部会话)
#   【日志】FS: 录音活动 ▶/■ 与全部补发/自愈过程留痕。
#
# v0.8 变更（2026-10-10）: 「点按」退役 → 纯长按（用户裁决，10-10 00:46）。
#   背景实证（桥接日志/接收端/输入法库 三源对账）：遥控器麦克风只在按住
#   期间送音频——纯点按会话仅带来 0~1 帧（≈15ms）音频（sid80/81），
#   "点一下、松着手说话"物理上收不到声音；v0.7 的「点按=多段合并」只在
#   刻意按序列操作时才有意义，且误点一次会让后续长按"哑火"（松开不出字）。
#   用户选择最简形态：
#     · 任何一次松开(up) = 提交识别（点按/长按不再分流）
#     · 点按 = 一条可忽略的极短空录音（失败记录），不影响后续按压
#     · 「多段合并」玩法移除；要长口述请直接单次长按
#
# v0.6 变更（2026-10-09）: 新增「点按开关」模式（智能分流）。
#   需求: 用户要两种用法并存——
#     A. 长按说话: 按住 → 说 → 松开 (与原装遥控器一致, 主力用法)
#     B. 点按开关: 点一下开始录音 → 说 → 再点一下结束 (适合长口述)
#   实现 (基于"每次 down 立即响应, 由 up 早晚决定是否补发"的状态机):
#     · down 到达: 依当前状态发一次切换点击 (idle→发『开始』/ open→发『结束』)
#       —— 按下瞬间即生效, 长按启动零延迟
#     · up 到达: 若"本次 down 发的开始"且按住 ≥ --short-press 秒(默认0.35)
#       → 补发『结束』(= 长按说话语义)
#       否则 (短按) → 不再发送 (切换已在 down 完成 = 点按开关语义)
#     · 兜底: 收听状态持续 --auto-close 秒(默认300)无操作 → 自动补发结束
#   行为对照: 长按(idle起)=开始...结束 ✓ 点按(idle起)=开始 ✓
#             点按(open起)=结束 ✓ 长按(open起)=结束 ✓
#
# v0.7 变更（2026-10-10）: 修复「点按开关」的物理缺陷 → 升级为「累积听写」。
#   【缺陷】遥控器麦克风只在按住期间送音频（实测：会话时长=按住时长；纯点按仅 2 帧）。
#   旧 v0.6 在 open 态"按下瞬间即发『结束』"→ 用户按住续说时录音已被关闭、
#   所说内容全部丢失（实测记录 362/363 全空）。
#   改为：open 态 down 不动作，由 up 判定 ——
#     · 松开 < 短按阈值 → 点按『结束』（识别出场）
#     · 松开 ≥ 短按阈值 → 视为一个"续说段"，不打断，保持收听
#   用法：点一下开始 → 按住说（可多段、段间松手不回字）→ 再点一下结束统一识别。
#
# v0.5 变更（2026-10-09）: ⚠️ 修复 submit 的「幽灵重启」缺陷。
#   【教训】launchctl submit 创建的 job 是"持续服务"语义, 不是"一次性":
#   程序退出后 launchd 会把它重新排入启动队列（state=spawn scheduled,
#   minimum runtime=10s）, 即每 ~10s 自动重跑一次 → 无限循环注入!
#   （实测: 10 个测试 job 错峰重启, 注入率 ~1 次/s, Chatterfly 计数疯涨）
#   修复三层: ① 每次 submit 后 1 秒后主动 remove ② 启动时清扫历史残留
#   ③ 主循环兜底清扫。另修复护栏: down 到达即武装, 不再因 submit 失败
#   而丢弃配对的 up。submit 失败仅告警, up 到来时仍会补发结束点击。
#
# v0.4 变更（2026-10-09）: "kickstart 固定 job" → "submit 唯一 label"。
#   原因: launchd 对同一 job 有硬性 ~10s 启动节流（SpawnThrottleInterval
#   无法放宽），密集按键时 kickstart 阻塞 >5s、job 迟到 ~9s（用户实测
#   "按下去没反应/松开还转圈"）。
#
# v0.3 变更（2026-10-09）: 注入出口从 "subprocess 直调 iohid_post" 改为
#   "launchd 直跑 job"。原因: launchd 上下文里 python3 子进程链的
#   TCC 授权被判 denied（事件静默丢弃）; 而 launchd 直跑 iohid_post 的
#   形态已实测可注入。
#
# 典型链路:  RC003 遥控器语音键 → T1 检测 down/up → UDP → 本服务
#            → launchctl submit(唯一 label) → iohid_post(直跑) → 注入
#            → 1s 后 remove job（防幽灵重启）
#
# 用法:
#   python3 voice_bridge.py                 # 默认 udp:8788 + ropt + 纯长按 + FS闭环
#   python3 voice_bridge.py --no-watch      # 关闭 FS 监看闭环(退化为纯转发)
#   python3 voice_bridge.py --watch-dir <path>  # 自定义 Chatterfly 录音目录
#   python3 voice_bridge.py --auto-close 300    # 兜底卡死自愈(0=关闭)
#
# 自测(本机模拟 T1):
#   长按: down → 1s → up         (开始 + 结束, 一条记录)
#   点按: down → 0.15s → up      (开始 + 结束, 一条极短空录音, 可忽略)
#   连点×2: down→0.15s→up 两次   (两条独立空录音, 互不影响)
#   查询: sendto b'status'       (回状态行)
# ---------------------------------------------------------------

import argparse
import itertools
import os
import re
import socket
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "iohid_post")   # 已授权的注入二进制（勿改名/移动！TCC 按路径授权）
REMOVE_DELAY = 1.0                       # v0.5: submit 后延迟 N 秒 remove（注入程序 <0.2s）
UID = os.getuid()

def log(msg: str):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)

_label_seq = itertools.count(1)
_pending_removals = {}   # label -> (due_ts, attempts)
_last_tap = 0.0          # v0.9: 最近一次成功发出的 tap 注入时间

FIX_START_GAP = 2.5      # v0.9: 开始补发最小间隔(秒)
FIX_STOP_GAP = 3.5       # v0.9: 结束补发最小间隔(秒)
FIX_START_MAX = 2        # v0.9: 每轮按压开始补发上限
FIX_STOP_MAX = 3         # v0.9: 每轮收尾结束补发上限
FIX_HEAL_GAP = 6.0       # v0.9: 超限后低频自愈间隔(秒)
FIX_HEAL_RECENT = 60.0   # v0.9: 仅最近该秒数内有过按压才自愈(防误伤外部会话)
FIX_HEAL_MAX = 6         # v0.9: 自愈次数硬上限

def _remove_job(label):
    """执行一次 launchctl remove; 返回 True=目标达成(job 已不存在)"""
    try:
        r = subprocess.run(["launchctl", "remove", label],
                           capture_output=True, text=True, timeout=5)
        err = (r.stderr or "").strip()
        missing = "Could not find" in err
        ok = (r.returncode == 0) or missing
        tag = " # 已不存在" if (missing and r.returncode != 0) else ""
        log(f"  <- remove {label} rc={r.returncode}{tag}")
        return ok
    except Exception as e:
        log(f"  !! remove {label} 异常: {e}")
        return False

def process_removals():
    """主循环兜底清扫: 到期则移除, 失败延迟重试, 至多 3 次放弃"""
    now = time.time()
    for label, (due, att) in list(_pending_removals.items()):
        if now < due:
            continue
        if _remove_job(label):
            del _pending_removals[label]
        elif att + 1 >= 3:
            log(f"  !! {label} 移除连续失败, 放弃 (残余 job 由下次启动清扫兜底)")
            del _pending_removals[label]
        else:
            _pending_removals[label] = (now + 2.0, att + 1)

def schedule_removal(label, delay=REMOVE_DELAY):
    _pending_removals[label] = (time.time() + delay, 0)

def cleanup_stale_jobs():
    """v0.5 启动清理: 移除域中全部历史 com.remotehub.tap.* job (防幽灵注入)"""
    try:
        r = subprocess.run(["launchctl", "print", f"gui/{UID}"],
                           capture_output=True, text=True, timeout=15)
        labels = sorted(set(re.findall(r"com\.remotehub\.tap\.\d+\.\d+", r.stdout or "")))
        if not labels:
            log("启动清理: 无历史 tap job 残留")
            return
        n_ok = 0
        for lb in labels:
            try:
                rr = subprocess.run(["launchctl", "remove", lb],
                                    capture_output=True, text=True, timeout=5)
                n_ok += (rr.returncode == 0)
            except Exception:
                pass
        log(f"启动清理: 已移除 {n_ok}/{len(labels)} 个历史 tap job")
    except Exception as e:
        log(f"!! 启动清理异常: {e}")

def fire(extra_args, tag=""):
    global _last_tap
    mode = extra_args[0] if extra_args else ""
    seq = next(_label_seq)
    label = f"com.remotehub.tap.{int(time.time())}.{seq}"
    try:
        r = subprocess.run(["launchctl", "submit", "-l", label, "--", BIN, mode],
                           capture_output=True, text=True, timeout=5)
        ok = r.returncode == 0
        out0 = (r.stdout or r.stderr or "").strip().splitlines()
        out0 = out0[0] if out0 else ""
        extra = f" | {out0}" if out0 else ""
        log(f"  -> submit {mode} #{seq} rc={r.returncode}{(' # ' + tag) if tag else ''}{extra}")
        if ok:
            _last_tap = time.time()
            schedule_removal(label)   # v0.5 关键: 防 submit-job 幽灵重启
        return ok
    except Exception as e:
        log(f"  !! submit 调用异常: {e}")
        return False


class FSTracker:
    """v0.9: 观察 Chatterfly 录音目录, 判断"录音是否进行中"。
    实测: 录音一开始就创建 audio_<起始ms>_*.opus 并持续写入, 停止后冻结。"""
    def __init__(self, watch_dir, stale=1.5):
        self.dir = watch_dir
        self.stale = stale       # mtime 新鲜阈值(秒) —— 必须 < FIX_STOP_GAP, 否则
                                 # "刚停止后的 mtime 新鲜残留" 会被误判为仍在录音
        self.ok = True           # False = 目录不可读, 自动退化为纯转发
        self.active = False
        self._newest = None      # (name, size, mtime)

    def poll(self, now):
        prev = self.active
        try:
            names = sorted(n for n in os.listdir(self.dir) if n.endswith(".opus"))
            if not names:
                active = False
            else:
                name = names[-1]
                stt = os.stat(os.path.join(self.dir, name))
                age = now - stt.st_mtime
                grew = (self._newest is not None and self._newest[0] == name
                        and stt.st_size > self._newest[1])
                fresh = age < self.stale
                active = grew or fresh
                if self._newest is None or self._newest[0] != name:
                    log(f"FS: 新录音文件 {name}")
                self._newest = (name, stt.st_size, stt.st_mtime)
        except Exception as e:
            if self.ok:
                self.ok = False
                log(f"!! FS 监看不可用: {e} (闭环退化为纯转发)")
            active = self.active
        self.active = active
        if active != prev:
            log(f"FS: 录音活动 {'▶ 开始' if active else '■ 结束'}")
        return active

def main():
    ap = argparse.ArgumentParser(description="Mac 端语音键桥 (UDP -> IOHIDPostEvent 注入) v0.8")
    ap.add_argument("--port", type=int, default=8788, help="UDP 监听端口 (默认 8788)")
    ap.add_argument("--key", choices=["ropt", "rcmd"], default="ropt",
                    help="ropt=右⌥点按式(语音输入, 默认) / rcmd=右⌘按住式")
    ap.add_argument("--short-press", type=float, default=0.35,
                    help="短按/长按 日志标签阈值(秒): 不影响行为, 仅区分日志措辞 (默认0.35)")
    ap.add_argument("--auto-close", type=float, default=300.0,
                    help="卡死自愈: 录音状态持续该秒数无事件则补发结束 (默认300, 0=关闭)")
    ap.add_argument("--watch-dir",
                    default=os.path.expanduser(
                        "~/Library/Application Support/Chatterfly/"
                        "InputMethod/ChatterflyPY.users/00000001/speech_data/speech_audio_file"),
                    help="Chatterfly 录音文件目录 (FS 闭环监看)")
    ap.add_argument("--no-watch", action="store_true", help="关闭 FS 监看闭环")
    args = ap.parse_args()

    cleanup_stale_jobs()   # v0.5: 启动清理

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", args.port))
    s.settimeout(0.5)
    log(f"voice_bridge v0.9 已启动: UDP :{args.port} | key={args.key} | 纯长按 + 录音状态闭环")
    log(f"  按住说话 → 松开出字 | 点按=自动收尾的空录音 (阈值{args.short_press:.2f}s仅日志用)"
        f" | FS监看={'off' if args.no_watch else 'on'} | 卡死自愈 {args.auto_close:.0f}s")
    log(f"  submit-job {REMOVE_DELAY:.0f}s 即时回收 | 启动清扫已启用")

    # ---- v0.9 状态机（每次松开=提交识别 + FS 闭环补发） ----
    st = {
        "state": "idle",      # idle / open(收音中)
        "down_at": 0.0,       # 本次 down 的时间戳
        "down_action": "",    # 本次 down 实际发了什么: start / stop / fail / ""
        "last_event": time.time(),
        "last_press": 0.0,    # v0.9: 最近一次 down/up 事件时间
        "start_fix": 0,       # v0.9: 本轮按压已补发开始次数
        "stop_fix": 0,        # v0.9: 本轮收尾已补发结束次数
    }
    fs = None if args.no_watch else FSTracker(args.watch_dir)

    def tick(now):
        """v0.9: FS 闭环 —— 比对期望状态与实测, 按安全间隔补发"""
        if not (fs and fs.ok):
            return
        obs = fs.poll(now)
        tgt_active = (st["down_action"] != "")   # 按压期间期望在录
        since = now - _last_tap
        if tgt_active and not obs:
            if st["start_fix"] < FIX_START_MAX and since >= FIX_START_GAP:
                st["start_fix"] += 1
                log(f"  !! 开始未生效(录音未启动) → 补发『开始』#{st['start_fix']}")
                fire([f"{args.key}-tap1"], f"fix-start{st['start_fix']}")
        elif (not tgt_active) and obs:
            if st["stop_fix"] < FIX_STOP_MAX and since >= FIX_STOP_GAP:
                st["stop_fix"] += 1
                log(f"  !! 结束未生效(录音仍开着) → 补发『结束』#{st['stop_fix']}")
                fire([f"{args.key}-tap1"], f"fix-stop{st['stop_fix']}")
            elif (st["stop_fix"] >= FIX_STOP_MAX and st["stop_fix"] < FIX_STOP_MAX + FIX_HEAL_MAX
                  and since >= FIX_HEAL_GAP and (now - st["last_press"]) < FIX_HEAL_RECENT):
                st["stop_fix"] += 1
                log(f"  !! 多次补发仍未见效 → 低频自愈 (第{st['stop_fix'] - FIX_STOP_MAX}次)")
                fire([f"{args.key}-tap1"], "heal")

    def do_down(t):
        st["down_at"] = t
        st["last_event"] = t
        st["last_press"] = t
        st["start_fix"] = 0
        st["stop_fix"] = 0
        tap = f"{args.key}-tap1"
        if st["state"] == "idle":
            log("  [状态机] down@idle → 发『开始』")
            if fire([tap], "start"):
                st["state"] = "open"
                st["down_action"] = "start"
            else:
                st["down_action"] = "fail"
                log("  !! 开始注入失败 (状态保持 idle)")
        else:
            log("  [状态机] down@open（罕见: 前次『结束』未生效）→ 等本次 up 收拢")
            st["down_action"] = "wait"

    def do_up(t):
        st["last_event"] = t
        st["last_press"] = t
        dur = t - st["down_at"]
        act = st["down_action"]
        if act == "start":
            kind = "长按" if dur >= args.short_press else "点按"
            log(f"  [状态机] up: {kind} {dur:.2f}s → 发『结束』, 识别出场")
            if fire([f"{args.key}-tap1"], "stop"):
                st["state"] = "idle"
        elif act == "wait":
            log(f"  [状态机] up@恢复态: {dur:.2f}s → 补发『结束』收拢")
            if fire([f"{args.key}-tap1"], "stop"):
                st["state"] = "idle"
        # down_action == fail / "" → up 无动作
        st["down_action"] = ""

    while True:
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            # 卡死自愈: 录音中且无进行中的按压 → 长时间无操作则补发结束
            now = time.time()
            if (args.auto_close > 0 and st["state"] == "open"
                    and st["down_action"] == ""
                    and (now - st["last_event"]) > args.auto_close):
                log(f"!! 卡死自愈: 录音已持续 {args.auto_close:.0f}s, 补发结束点击")
                fire([f"{args.key}-tap1"], "timeout-close")
                st["state"] = "idle"
            tick(now)
            process_removals()
            continue
        except KeyboardInterrupt:
            log("收到 Ctrl-C, 退出")
            return
        text = data.decode("utf-8", "replace").strip()
        peer = f"{addr[0]}:{addr[1]}"
        low = text.lower()
        now = time.time()

        if low == "voice down":
            if st["down_action"] != "":
                log(f"RX {peer} -> VOICE down (护栏: 上一次按压未见 up, 忽略)")
            else:
                log(f"RX {peer} -> VOICE down")
                do_down(now)
        elif low == "voice up":
            if st["down_action"] == "":
                log(f"RX {peer} -> VOICE up (护栏: 无对应 down, 忽略)")
            else:
                log(f"RX {peer} -> VOICE up")
                do_up(now)
        elif low == "ping":
            s.sendto(b"pong", addr)
            log(f"RX {peer} -> ping (已回 pong)")
        elif low == "status":
            fs_s = "na" if not fs else ("on" if fs.ok and fs.active else "off")
            msg = (f"STATUS state={st['state']} down_action={st['down_action'] or '-'} "
                   f"fs={fs_s} last_event={int(st['last_event'])}")
            s.sendto(msg.encode(), addr)
            log(f"RX {peer} -> status ({st['state']}, fs={fs_s})")
        else:
            log(f"RX {peer} -> {text!r} (未知指令, 忽略)")

        tick(now)             # v0.9: 每轮消息后推进 FS 闭环
        process_removals()   # 每轮消息后兜底清扫

if __name__ == "__main__":
    main()
