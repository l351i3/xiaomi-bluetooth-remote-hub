#!/usr/bin/env python3
# key_bridge.py — Mac 端「遥控器按键」注入桥 v1.15 (2026-10-13)
# ------------------------------------------------------------------
# v1.15（10-13 电源键连击切换设备, 承接 voice_fwd v2.7）: 新增设备切换 HUD 动作
#   TARGET:SWITCH:ATV|MAC|WIN（仅 DOWN 触发）—— 调 remotehub_focus.lua v1.4
#   switchHud()（hs.alert 浮层「🎯 已切到 X」+ 提示音）。T1 侧 voice_fwd v2.7
#   在电源键连击提交后发送（切到 atv 发旧目标端 / 切到 mac·win 发新目标端）;
#   路由复用鼠标串行 worker（保序、不阻塞 UDP; 对白名单外目标静默忽略）。
#   Windows 对等 = win_receiver v1.10 + win_actions v1.14（Tk 浮层）。
# ------------------------------------------------------------------
# v1.14（10-13 实测反馈修复轮）: 新增模式提示动作 MOUSE:MODE:ON|OFF —— 调
#   remotehub_focus.lua v1.3 mouseHud()（hs.alert 浮层「🖱 鼠标模式 / ⌨ 键盘模式」+
#   提示音）。治用户反馈「模式切换无提示, 按了不知道生效没有」; T1 侧 voice_fwd v2.6
#   在切换 / 模式内单按 #41 时主动发送。仅 DOWN 触发（对齐 LCLICK 等既有语义）。
#   Windows 对等 = win_receiver v1.8 + win_actions v1.12（Tk HUD）。
# ------------------------------------------------------------------
# v1.13（10-13）: 新增鼠标模式（MOUSE:* 动作 —— 遥控器 dpad 模拟鼠标, 用户需求）:
#   · MOUSE:MOVE:UP|DOWN|LEFT|RIGHT  —— 滑行移动（按住=连续滑, 松开停）
#   · MOUSE:SCROLL:UP|DOWN           —— 连续滚动（按住=连续滚）
#   · MOUSE:LCLICK / MOUSE:RCLICK    —— 当前光标位置点击（仅 DOWN 触发）
#   执行 = Hammerspoon remotehub_focus.lua v1.2 鼠标执行器（mouseStart/Stop/Click/
#   scrollStart/Stop, 状态挂 _G 全局单例跨 hs 调用存活）; 滑行参数两端一致
#   （加速 700px/s² / 上限 1600px/s / 1.2s 无刷新看门狗自停 —— 保活包断流即刹车）。
#   路由: 专用串行 worker（保序: DOWN/保活/UP 依序执行; 队列满丢弃 —— 保活语义天然
#   容丢, UP 丢失由看门狗兜底）。T1 侧 voice_fwd v2.5 模式层产生（0.4s 保活节奏）。
#   Windows 对等 = win_receiver v1.7 + win_actions v1.11。
# ------------------------------------------------------------------
# v1.12（10-12）: 新增 APP:CLOSE ——「关闭当前前台应用」（用户需求: 长按电源键关闭当前应用;
#   keymap #116 long=APP:CLOSE 生产绑定）。实现 = app_switch v1.2 close 子命令
#   （NSWorkspace terminate; 优雅退出等价 Cmd+Q, 非注入无需 TCC）。纵深防护:
#   · CLOSE_DEBOUNCE=2.0s（关闭后前台必变——防重复包二次触发连关两个应用）;
#   · 成功后不调度 focus assist（关闭场景无切换修复需求）。
#   Windows 对等 = win_actions v1.10 do_app_close（WM_CLOSE 路径）。
# ------------------------------------------------------------------
# v1.11（10-11 21:5x）: 新增 URL: / RUN: 动作 —— 遥控一键「打开网页 / 执行命令」
#   · KEY URL:<网址> DOWN → open 打开默认浏览器（per-url 0.6s 防抖）
#   · KEY RUN:<命令> DOWN → /bin/sh 执行（per-cmd 0.6s 防抖; 值不含空格——
#     UDP 协议按空白分词, 含空格命令请写成脚本文件后填脚本路径）
#   · 仅 DOWN 触发、UP 忽略（对齐 APP:/FOCUS_INPUT/CLICK 语义）。
#     T1 侧（t1_webui v2.10）校验: mac/win 前缀放行 / 禁空格 / ≤500 字符 / ATV 拒绝。
# ------------------------------------------------------------------
# v1.10（10-10 21:1x）: 键表扩展 —— 新增 PAGEUP(116) / PAGEDOWN(121)
#   ——「翻页」动作（看长回复/网页翻页；T1 webui v2.8 下拉可选配）。
#   链路无需其他改动（voice_fwd 纯透传 → 本表查得键码直接注入）。
# v1.9（10-10 20:2x）: 新增「点击」动作 ——
#   · CLICK 动作（仅 DOWN）: 经 Hammerspoon 调 remotehub_focus.lua.clickFocused()
#     —— 对「当前键盘焦点元素」执行激活: AXPress（自身或向上 ≤6 层找最近支持者;
#     全不支持时坐标鼠标点击兜底）。背景: WorkBuddy/Electron 里 TAB 可达元素
#     （任务列表条目、列表项等）不响应合成 ENTER（组件未实现键盘激活），但支持
#     AXPress 且实测与真实点击等效（20:1x 任务切换往返双验证 OK）。生产场景:
#     音量-=TAB 切焦点 → CLICK 键执行点击（建议绑定 OK 长按 / 用户自选）。
#   · 线程内执行（hs 调用 ~0.5s）不阻塞 UDP; 0.6s 防抖。
# v1.8（10-10 19:3x）: 新增「跳输入框 / 切换后焦点修复」——
#   · FOCUS_INPUT 动作（仅 DOWN）: 经 Hammerspoon 调 remotehub_focus.lua.focusInput()
#     —— 窗口聚焦修复 + 聚焦前台窗口首个可编辑元素（坐标 hit-test 为主: 缓存点 →
#     坐标网格 → 树遍历; Chromium 系（WorkBuddy/Obsidian）树遍历不可靠, 坐标探测实测
#     有效; 微信内容层无 AX, 只能窗口级修复）; 线程内执行（hs 调用 ~0.5s）不阻塞 UDP;
#     0.6s 防抖。
#   · 切换后焦点修复: APP 类动作成功后自动调度 focusWindow()（+0.45s）—— 修复
#     “切换后窗口有时无法获得键盘焦点”（macOS 14+ 对后台进程激活请求偶发静默丢弃,
#     2026-10-10 实测复现: activate 返回 true 但前台未变）。AppPicker 在其 ENTER 后
#     同款调度（见 AppPicker v1.1）。
#   · 依赖: /opt/homebrew/bin/hs + Hammerspoon 1.1.1（init.lua 已加 require("hs.ipc");
#     辅助功能授权在 Hammerspoon.app, 无需新 TCC）。脚本 ~/.hammerspoon/remotehub_focus.lua。
# v1.7（10-10 17:5x）: APP:PICK ——「应用选择器」（主页键 #102 长按生产绑定）:
#   · 触发: do_app("pick") 启动/唤起 AppPicker.app（已显示则忽略; 标志=/tmp/apppicker.sock 存在）;
#   · 路由: 选择器显示期间, LEFT/RIGHT/UP/DOWN/ENTER/ESC 的 DOWN 走 UNIX dgram 发给
#     AppPicker（不注入系统）; UP 吞掉（防裸 up 泄漏到前台应用）;
#     socket 消失（选择器已确认/取消退出）后 PICKER_GRACE(1s) 内仍吞 UP 收尾。
#   · picker 由 AppPicker.app 实现（浮动面板不抢焦点; 接收 socket 命令移动高亮/确认打开）。
# v1.6（10-10 16:4x）: APP 动作新增 CYCLE ——「全应用轮询」（主页键 #102 生产绑定）:
#   连续按沿冻结快照环状推进（z-order 快照 ≈ 最近使用序）, 手动换应用/超时 30 分钟
#   自动重建。实现=app_switch v1.1 的 cycle 子命令（NSWorkspace 激活, 非注入, 无需
#   TCC）。TOGGLE / NEXT 保留可用。
# v1.5（10-10 15:3x）: 新增「应用动作」通道 —— "KEY APP:<名称>|TOGGLE|NEXT DOWN"
#   不经过键盘注入, 调 app_switch 工具（NSWorkspace 激活应用, 无需 TCC 授权,
#   10-10 15:30 实测: activate/toggle 前台切换 + front 对账全过）。
#   语义: APP:<名称>=切换到(未运行则启动)该应用; APP:TOGGLE=最近两应用间跳
#   （≈ cmd+tab 快速点按）; APP:NEXT=按名称序循环切换。
#   APP 类动作仅 DOWN 触发（UP 忽略）+ APP_DEBOUNCE 防抖; 不进卡键守卫。
#   背景: 「组合键合成」用户态不可行（Task#30 五路线否决）, 应用切换改走
#   「直接激活」语义（≠ 合成 ⌘+Tab; 效果等价且更强）。
# v1.4（10-10 13:1x）: 注入后端升级 —— serve 常驻 socket 优先, submit 兜底。
#   根因（对照实验实证）: v1.3 的 launchctl submit 每事件起独立进程, 进程
#   「快生快灭」致合成事件偶发投递丢失（双进程 key 模式实测丢约一半:
#   key109 仅到 UP / key111 仅到 DOWN）。cgpost serve 常驻进程保持单一
#   CGEventSource 生命周期, 实测 4 组 down/up（间隔 0.05~0.4s）16/16 全
#   捕获, 监听器时间线与 serve 日志一一对应。
#   落地: /tmp/cgpost.sock 走「显式 bind 客户端」形态（macOS 上匿名/仅
#   connect 的 UNIX dgram 收不到回复——此坑已踩实, 勿再简化）。
#   serve 进程 = launchd 常驻 com.remotehub.cgpost-serve（KeepAlive 自愈）;
#   失联时本桥熔断 15s 走 submit 兜底（慢 ~100ms 但保底不丢按键）。
#   参考对照: mi-ao（Mac 开源）/ MIC-RC003-Windows 均为「常驻 App +
#   标准授权 + CGEventPost」形态 —— 本架构与其同构。
# v1.3（10-10 13:0x）: 注入二进制切换 —— 从裸二进制 cgpost 改为
#   CGPost.app/Contents/MacOS/cgpost（App Bundle 身份）。
#   根因: macOS 26/27 对「手动+添加的裸二进制」生成的 TCC 记录无法与进程
#   匹配（tccd: Failed to match existing code requirement；二进制字节未变
#   仍被拒）。换 App 形态后（Bundle ID 级记录）launchd 上下文实测
#   PostEvent/AX/Listen 三项全 1，注入可用。
#   对照参考（10-10 复核）: mi-ao（Mac 开源项目）/ MIC-RC003-Windows 同为
#   「普通 App + 标准授权 + CGEventPost」路线 —— 与本次落地形态同构。
#   备份: key_bridge.py.v12.bak-20261010-1258（指向裸 cgpost，授权不生效）。
# v1.2（10-10 12:3x）: 注入通道更换 —— 裸键从 IOHIDPostEvent 改走 CGEventPost。
#   实证（10-10 12:2x）: IOHIDPostEvent 对裸键（无 flags 的 NX_KEYDOWN/UP）
#   返回 kr=0 但事件不进系统事件流（监听器 14s 零捕获；修饰键/flags 形态才
#   有效——语音链的 ropt 注入不受影响）。cgpost(CGEventPost) 经监听器实测
#   事件完整进流（key=105 down/up, srcPid=注入进程, 属 CGEvent 正常痕迹）。
#   前置: cgpost 需 kTCCServicePostEvent 授权（系统设置>隐私与安全性>辅助功能;
#   与 Accessibility 为独立 TCC 服务, 2026-10-10 由用户手动加入列表授权）。
#   回滚: key_bridge.py.v11.bak-*（改回 iohid_post 形态；注意裸键在其上不可用）。
# v1.1（10-10 12:2x）: 排障增强 ——
#   ① 注入进程输出捕获: launchctl submit 加 -o/-e → logs/key_bridge_inject.log
#      （注: 未授权时 cgpost 会输出「警告: PostEvent 权限未授权」行, 排障信号）
#   ② 新增诊断探针协议: "RAW <nxkc> DOWN|UP" 直接注入原始 keycode（不查键表）
# 监听 UDP :8791, 收文本指令（来自 T1 voice_fwd.py, 目标=mac 时的普通键转发）:
#   "KEY <NAME> DOWN" / "KEY <NAME> UP" / "RAW <nxkc> DOWN|UP"(诊断)
# 注入形态（v1.4 双路径）:
#   主路径: UNIX dgram /tmp/cgpost.sock -- "KEY <nxkc> <0|1>" 发给常驻
#     serve 进程（CGPost.app 内二进制, launchd job com.remotehub.cgpost-serve,
#     KeepAlive 自愈）。客户端必须显式 bind 本地路径才能收到回复（macOS 坑）。
#   兜底: launchctl submit(唯一 label) -- cgpost key <nxkc> <0|1> 独立进程
#     —— 与 voice_bridge 同款「launchd 直跑」形态（TCC 已验证;
#        python→注入器 子进程链会被 TCC 静默拒绝, 勿改）。
#     submit 后 1s remove 防「幽灵重启」（v0.5 教训详见 voice_bridge 头注）。
#
# 键表（macOS NX keycode）:
#   ENTER=36  ESC=53  UP=126  DOWN=125  LEFT=123  RIGHT=124
#   SPACE=49  TAB=48  BACKSPACE=51
#
# 守卫:
#   ① 卡键自愈: 某键 DOWN 后 STUCK_TIMEOUT 秒内无该键任何活动（合法长按会持续
#      来 DOWN 连发, 由 voice_fwd 节流补发）→ 补发 UP, 防 UDP 丢包导致按键悬死
#   ② 启动清扫: 移除历史 com.remotehub.key.* job
# 诊断: "ping" → "pong"; "status" → 状态行
# 配套: 配置=keymap.json targets.mac.keys（T1 :8765 /keymap 页编辑）;
#       动作名 → keycode 的映射在本文件; 新增动作时两端同步
# 运行: launchd com.remotehub.key-bridge (RunAtLoad+KeepAlive)
#   (手动: python3 -u key_bridge.py)
# ------------------------------------------------------------------

import itertools
import os
import queue
import re
import socket
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# CGEventPost 注入器 —— 必须走 CGPost.app 内的二进制（App Bundle 身份）。
# TCC 记录按 Bundle ID 匹配（裸二进制在 macOS 26/27 上记录不匹配、实测被拒）。
# ⚠ 勿改名/移动/重编译 CGPost.app！改动前先读 cgpost.c 头注的冻结约定。
BIN = os.path.join(HERE, "CGPost.app", "Contents", "MacOS", "cgpost")
SERVE_SOCK = "/tmp/cgpost.sock"          # cgpost serve 常驻 socket（job: com.remotehub.cgpost-serve）
UDS_LOCAL = "/tmp/key_bridge_cli.sock"   # 本进程接收地址（⚠ macOS 上必须显式 bind 才能收 serve 回复）
SOCK_TIMEOUT = 0.5                       # serve 应答超时
SERVE_RETRY_WINDOW = 15.0                # serve 失联熔断窗口（期间走 submit 兜底）
PORT = 8791
VERSION = "1.15"          # 2026-10-13: TARGET:SWITCH:* 切换 HUD（v1.12: 版本号唯一来源, banner/status 共用）
UID = os.getuid()
REMOVE_DELAY = 1.0        # submit 后延迟 N 秒 remove（注入程序 <0.2s）
STUCK_TIMEOUT = 20.0      # 卡键自愈: DOWN 后无活动超时秒数
INJECT_LOG = os.path.join(HERE, "logs", "key_bridge_inject.log")  # 捕获注入进程 stdout/stderr
APP_SWITCH = os.path.join(HERE, "app_switch")   # 应用切换工具（NSWorkspace 激活, 非注入, 无需 TCC）
APP_DEBOUNCE = 0.35       # APP 类动作防抖秒数（防连发/重复包导致狂切）
CLOSE_DEBOUNCE = 2.0      # v1.12: APP:CLOSE 专用防抖 —— 关闭后前台必变, 防重复包连关第二个应用
# v1.7: 应用选择器（AppPicker.app）
PICKER = os.path.join(HERE, "AppPicker.app")
PICKER_SOCK = "/tmp/apppicker.sock"    # 选择器显示期间存在（路由标志 + 命令通道）
PICKER_KEYS = {"LEFT", "RIGHT", "UP", "DOWN", "ENTER", "ESC"}   # 选择器模式下路由的键
PICKER_GRACE = 1.0        # socket 消失后的 UP 吞收尾宽限秒数（防裸 up 泄漏）
# v1.8: 「跳输入框 / 切换后焦点修复」—— 经 Hammerspoon 的 hs CLI 调 remotehub_focus.lua
HS_BIN = "/opt/homebrew/bin/hs"
FOCUS_LUA = os.path.expanduser("~/.hammerspoon/remotehub_focus.lua")
FOCUS_DEBOUNCE = 0.6      # FOCUS_INPUT 防抖秒数
CLICK_DEBOUNCE = 0.6      # v1.9: CLICK 防抖秒数（点击焦点元素）
URL_DEBOUNCE = 0.6        # v1.11: URL 打开防抖秒数（per-url）
RUN_DEBOUNCE = 0.6        # v1.11: RUN 执行防抖秒数（per-cmd）

KEYMAP = {
    "ENTER": 36,
    "ESC": 53,
    "UP": 126,
    "DOWN": 125,
    "LEFT": 123,
    "RIGHT": 124,
    "SPACE": 49,
    "TAB": 48,
    "BACKSPACE": 51,
    "PAGEUP": 116,      # v1.10: 上一页（看长回复翻页）
    "PAGEDOWN": 121,    # v1.10: 下一页
}

_label_seq = itertools.count(1)
_pending_removals = {}    # label -> (due_ts, attempts)
_uds = None               # serve 通信用 socket 单例（显式 bind 后才能收回复）
_serve_down_until = 0.0   # 熔断截止时间戳（serve 失联期间直接走 submit）
_app_last = {}            # verb -> 上次执行时间戳（APP 类动作防抖）


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


# ---------- launchctl submit 注入（照抄 voice_bridge 已验证形态） ----------
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
    """启动清理: 移除域中全部历史 com.remotehub.key.* job（防幽灵注入）"""
    try:
        r = subprocess.run(["launchctl", "print", f"gui/{UID}"],
                           capture_output=True, text=True, timeout=15)
        labels = sorted(set(re.findall(r"com\.remotehub\.key\.\d+\.\d+", r.stdout or "")))
        if not labels:
            log("启动清理: 无历史 key job 残留")
            return
        n_ok = 0
        for lb in labels:
            try:
                rr = subprocess.run(["launchctl", "remove", lb],
                                    capture_output=True, text=True, timeout=5)
                n_ok += (rr.returncode == 0)
            except Exception:
                pass
        log(f"启动清理: 已移除 {n_ok}/{len(labels)} 个历史 key job")
    except Exception as e:
        log(f"!! 启动清理异常: {e}")


# ---------- serve 常驻通道（v1.4 主路径） ----------
def _uds_reset():
    global _uds
    if _uds is not None:
        try:
            _uds.close()
        except Exception:
            pass
        _uds = None


def _uds_request(msg: bytes, timeout=SOCK_TIMEOUT) -> bytes:
    """向 cgpost serve 发一条指令并取回复（socket 单例, 惰性建立）。
    ⚠ macOS 实测: 匿名 / 仅 connect 的 UNIX dgram 收不到回复, 必须显式 bind 路径。"""
    global _uds
    if _uds is None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            os.unlink(UDS_LOCAL)
        except OSError:
            pass
        try:
            s.bind(UDS_LOCAL)
        except Exception:
            s.close()
            raise
        _uds = s
    _uds.sendto(msg, SERVE_SOCK)
    return _uds.recv(128)


def serve_alive() -> bool:
    """PING/PONG 探测 serve 常驻进程是否在线"""
    try:
        return _uds_request(b"PING").startswith(b"PONG")
    except Exception:
        _uds_reset()
        return False


def fire_socket(nk: int, down: bool) -> bool:
    """经 serve 常驻进程注入（进程零启动开销, 事件生命周期稳定）"""
    try:
        rx = _uds_request(b"KEY %d %d" % (nk, 1 if down else 0))
        return rx.startswith(b"OK")
    except Exception:
        _uds_reset()
        return False


def fire(name, down):
    """注入一次键 down/up（name=动作名 或 原始 keycode int）; 返回是否成功。
    v1.4: 优先 serve 常驻 socket; serve 失联则熔断 SERVE_RETRY_WINDOW 秒,
    期间走 submit 独立进程兜底（-o/-e 捕获注入进程输出到 INJECT_LOG, 供排障）。"""
    global _serve_down_until
    if isinstance(name, int):
        nk, tag = name, f"raw{name}"
    else:
        nk, tag = KEYMAP[name], name
    phase = "down" if down else "up"

    if time.time() >= _serve_down_until:
        if fire_socket(nk, down):
            log(f"  -> [serve] key {tag}({nk}) {phase} OK")
            return True
        _serve_down_until = time.time() + SERVE_RETRY_WINDOW
        log(f"  !! serve 失联 → 熔断 {SERVE_RETRY_WINDOW:.0f}s 走 submit 兜底（launchd 应已自动拉起 serve）")

    seq = next(_label_seq)
    label = f"com.remotehub.key.{int(time.time())}.{seq}"
    try:
        r = subprocess.run(["launchctl", "submit", "-l", label,
                            "-o", INJECT_LOG, "-e", INJECT_LOG, "--",
                            BIN, "key", str(nk), "1" if down else "0"],
                           capture_output=True, text=True, timeout=5)
        ok = r.returncode == 0
        out0 = (r.stdout or r.stderr or "").strip().splitlines()
        out0 = out0[0] if out0 else ""
        extra = f" | {out0}" if out0 else ""
        log(f"  -> [submit兜底] key {tag}({nk}) {phase} #{seq} rc={r.returncode}{extra}")
        if ok:
            schedule_removal(label)
        return ok
    except Exception as e:
        log(f"  !! submit 调用异常: {e}")
        return False


_picker_last_seen = [0.0]   # picker socket 上次可见时刻（v1.7 宽限判定）


def _picker_route(name, phase):
    """v1.7: picker 模式路由判定（仅对 PICKER_KEYS 调用）。
    True = 已处理（DOWN 已转发给 AppPicker / UP 已吞掉, 均不再注入）;
    False = 走正常注入路径。"""
    now = time.time()
    exists = os.path.exists(PICKER_SOCK)
    if exists:
        _picker_last_seen[0] = now
    recent = (now - _picker_last_seen[0]) < PICKER_GRACE
    if phase == "DOWN":
        if not exists:
            return False        # 选择器不在 -> 正常注入
        try:
            s2 = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s2.sendto(name.encode(), PICKER_SOCK)
            s2.close()
            log(f"  -> [picker] 路由 {name} DOWN")
            return True
        except Exception as e:  # noqa: BLE001
            log(f"  !! picker 路由失败({name}): {e} -> 正常注入")
            return False
    # phase == "UP": socket 存在或刚消失（宽限内）-> 吞掉（防裸 up 泄漏到前台应用）
    if exists or recent:
        log(f"  -> [picker] 吞 {name} UP（{'显示中' if exists else '刚关闭·宽限'}）")
        return True
    return False


def do_app(verb):
    """v1.5+: 'APP:<名称>|TOGGLE|NEXT|CYCLE|CLOSE' 应用动作 —— 调 app_switch 工具（NSWorkspace
    激活/关闭, 非键盘注入, 无需 TCC）。返回是否成功; 0.35s 防抖挡连发/重复包
    （CLOSE 走 2.0s 强防抖——见 CLOSE_DEBOUNCE）。"""
    v = verb.strip()
    if not v:
        log("  !! APP 动作为空, 忽略")
        return False
    now = time.time()
    d = CLOSE_DEBOUNCE if v.lower() == "close" else APP_DEBOUNCE   # v1.12: close 走 2s 强防抖
    if now - _app_last.get(v.lower(), 0.0) < d:
        log(f"  -> [app] {v} 防抖忽略（{d:.2f}s 窗口内重复）")
        return False
    _app_last[v.lower()] = now
    if v.lower() == "pick":
        # v1.7: 应用选择器 —— 已显示则忽略; 否则启动 AppPicker（LSUIElement, 不抢焦点）
        if os.path.exists(PICKER_SOCK):
            log("  -> [app] pick 忽略（选择器已在显示中）")
            return True
        try:
            r = subprocess.run(["open", "-a", PICKER], capture_output=True, text=True, timeout=10)
            ok = r.returncode == 0
            log(f"  -> [app] pick 启动选择器 {'OK' if ok else 'FAIL'} rc={r.returncode}"
                + (f" | {(r.stderr or '').strip()[:120]}" if not ok else ""))
            return ok
        except Exception as e:
            log(f"  !! picker 启动异常: {e}")
            return False
    if v.lower() in ("toggle", "next", "cycle", "close"):
        cmd = [APP_SWITCH, v.lower()]
    else:
        cmd = [APP_SWITCH, "activate", v]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        out = out[0] if out else ""
        tag = "OK" if r.returncode == 0 else "FAIL"
        log(f"  -> [app] {v} {tag} rc={r.returncode} | {out}")
        if r.returncode == 0 and v.lower() != "close":   # v1.12: close 无切换修复需求
            do_focus_assist()   # v1.8: 切换成功后调度焦点修复（+0.45s, 异步）
        return r.returncode == 0
    except Exception as e:
        log(f"  !! app_switch 调用异常: {e}")
        return False


# ---------- v1.8: 焦点功能（经 Hammerspoon / hs CLI, AX 操作在 Hammerspoon.app 内执行） ----------
def _hs(code, timeout=8):
    """执行一段 Lua（调用方负责拼 dofile 等）。返回 (ok, 首行/末行输出或错误)。"""
    try:
        r = subprocess.run([HS_BIN, "-c", code], capture_output=True, text=True, timeout=timeout)
        lines = (r.stdout or "").strip().splitlines()
        out = lines[-1] if lines else ""
        if r.returncode != 0:
            err = ((r.stderr or "").strip().splitlines() or [""])[0]
            return False, f"rc={r.returncode} {err or out}"
        return True, out
    except Exception as e:  # noqa: BLE001
        return False, f"exc {e!r}"


_focus_last = [0.0]


def do_focus_input():
    """FOCUS_INPUT: 跳输入框（线程内执行, 不阻塞 UDP 循环）。返回 False=防抖忽略"""
    now = time.time()
    if now - _focus_last[0] < FOCUS_DEBOUNCE:
        log(f"  -> [focus] 防抖忽略（{FOCUS_DEBOUNCE:.1f}s 窗口内重复）")
        return False
    _focus_last[0] = now

    def worker():
        ok, out = _hs(f'return dofile("{FOCUS_LUA}").focusInput()')
        log(f"  -> [focus] 跳输入框 {'OK' if ok else 'FAIL'} | {out}")

    threading.Thread(target=worker, daemon=True).start()
    return True


def do_focus_assist():
    """APP 类动作成功后的切换修复（异步; hs 侧 +0.45s 自行调度; 失败仅记日志）"""
    def worker():
        ok, out = _hs(f'return dofile("{FOCUS_LUA}").assistLater()')
        log(f"  -> [focus] 切换后修复 {'已调度' if ok else '调度失败'} | {out}")

    threading.Thread(target=worker, daemon=True).start()


_click_last = [0.0]


def do_click():
    """v1.9 CLICK: 点击当前焦点元素（AXPress/坐标兜底, Hammerspoon 执行）。
    返回 False=防抖忽略"""
    now = time.time()
    if now - _click_last[0] < CLICK_DEBOUNCE:
        log(f"  -> [click] 防抖忽略（{CLICK_DEBOUNCE:.1f}s 窗口内重复）")
        return False
    _click_last[0] = now

    def worker():
        ok, out = _hs(f'return dofile("{FOCUS_LUA}").clickFocused()')
        log(f"  -> [click] 点击焦点元素 {'OK' if ok else 'FAIL'} | {out}")

    threading.Thread(target=worker, daemon=True).start()
    return True


_url_last = {}            # v1.11: url -> 上次打开时间戳（per-url 防抖）


def do_url(url):
    """v1.11 URL:<网址>: 打开网页（默认浏览器; per-url 防抖）。返回 False=防抖忽略/出错"""
    u = (url or "").strip()
    if not u:
        log("  !! URL 为空, 忽略")
        return False
    now = time.time()
    if now - _url_last.get(u, 0.0) < URL_DEBOUNCE:
        log(f"  -> [url] {u} 防抖忽略（{URL_DEBOUNCE:.1f}s 窗口内重复）")
        return False
    _url_last[u] = now
    try:
        subprocess.Popen(["open", u])
        log(f"  -> [url] 打开 {u}")
        return True
    except Exception as e:
        log(f"  !! [url] 打开异常: {e}")
        return False


_run_last = {}            # v1.11: cmd -> 上次执行时间戳（per-cmd 防抖）


def do_run(cmd):
    """v1.11 RUN:<命令>: 执行命令（/bin/sh; per-cmd 防抖; 值不含空格=协议约束,
    复杂命令请写成脚本文件后填脚本路径）。返回 False=防抖忽略/出错"""
    c = (cmd or "").strip()
    if not c:
        log("  !! RUN 为空, 忽略")
        return False
    now = time.time()
    if now - _run_last.get(c, 0.0) < RUN_DEBOUNCE:
        log(f"  -> [run] {c} 防抖忽略（{RUN_DEBOUNCE:.1f}s 窗口内重复）")
        return False
    _run_last[c] = now
    try:
        subprocess.Popen(c, shell=True, cwd=os.path.expanduser("~"))
        log(f"  -> [run] 执行 {c}")
        return True
    except Exception as e:
        log(f"  !! [run] 执行异常: {e}")
        return False


# ---------- v1.13: 鼠标模式（MOUSE:* -> Hammerspoon remotehub_focus.lua） ----------
# v1.15: TARGET:SWITCH:*（设备切换 HUD）同走本通道 —— 一次性小动作, 与鼠标动作共用串行 worker。
# 滑行/滚动为「按住」语义: DOWN 启动 / 保活 DOWN 刷新 / UP 停止。
# 执行走专用串行 worker（保序）——hs 调用 ~30-80ms, 0.4s 保活节奏余量充足;
# 队列满丢弃（保活容丢; UP 丢失由 lua 侧 1.2s 看门狗自停兜底）。
MOUSE_HS_TIMEOUT = 5      # 鼠标动作 hs 调用超时（比默认 8s 短——保活包过期无意义）
_mouse_q = queue.Queue(maxsize=64)


def _mouse_cmd(name, phase):
    """动作 -> lua 调用片段; 非法/N.A. 返回 None（phase 大小写宽容）。"""
    a = (name or "").upper()
    ph = (phase or "").upper()
    if a.startswith("MOUSE:MOVE:"):
        d = a.rsplit(":", 1)[-1].lower()
        if d not in ("up", "down", "left", "right"):
            return None
        return f'mouseStart("{d}")' if ph == "DOWN" else f'mouseStop("{d}")'
    if a.startswith("MOUSE:SCROLL:"):
        d = a.rsplit(":", 1)[-1].lower()
        if d not in ("up", "down"):
            return None
        return f'scrollStart("{d}")' if ph == "DOWN" else f'scrollStop("{d}")'
    if a == "MOUSE:LCLICK":
        return 'mouseClick("left")' if ph == "DOWN" else None
    if a == "MOUSE:RCLICK":
        return 'mouseClick("right")' if ph == "DOWN" else None
    if a in ("MOUSE:MODE:ON", "MOUSE:MODE:OFF"):      # v1.14: HUD 提示（仅 DOWN）
        if ph != "DOWN":
            return None
        return 'mouseHud("on")' if a.endswith("ON") else 'mouseHud("off")'
    if a.startswith("TARGET:SWITCH:"):                # v1.15: 设备切换 HUD（仅 DOWN）
        if ph != "DOWN":
            return None
        t = a.rsplit(":", 1)[-1].lower()
        if t not in ("atv", "mac", "win"):
            return None
        return f'switchHud("{t}")'
    return None


def _mouse_worker():
    """串行执行鼠标动作（顺序敏感: start/保活/stop 不可乱序）。"""
    while True:
        name, phase = _mouse_q.get()
        try:
            fn = _mouse_cmd(name, phase)
            if fn is None:
                log(f"  -> [mouse] {name} {phase} (无操作/忽略)")
                continue
            ok, out = _hs(f'return dofile("{FOCUS_LUA}").{fn}', timeout=MOUSE_HS_TIMEOUT)
            tag = "hud" if (name or "").upper().startswith("TARGET:SWITCH") else "mouse"
            log(f"  -> [{tag}] {name} {phase} {'OK' if ok else 'FAIL'} | {out}")
        except Exception as e:  # noqa: BLE001
            log(f"  !! [mouse] 执行异常: {e}")


def mouse_dispatch(name, phase):
    """收包线程入口: 仅入队（µs 级）。返回 False=队列满丢弃。"""
    try:
        _mouse_q.put_nowait((name, phase))
        return True
    except queue.Full:
        return False


def main():
    cleanup_stale_jobs()
    threading.Thread(target=_mouse_worker, daemon=True, name="mouse-worker").start()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", PORT))
    s.settimeout(0.5)
    log(f"key_bridge v{VERSION} 已启动: UDP :{PORT} | 注入=serve常驻({'在线' if serve_alive() else '离线(将走submit兜底)'})+submit兜底 | "
        f"键表 {len(KEYMAP)} 项 + APP动作(切换/轮询/选择器/关闭) + FOCUS_INPUT(跳输入框) + CLICK(点击焦点元素) + URL/RUN(开网页·跑命令) + MOUSE(鼠标模式:滑行/滚动/点击/模式提示) + TARGET:SWITCH(设备切换HUD) | 卡键自愈 {STUCK_TIMEOUT:.0f}s | submit-job {REMOVE_DELAY:.0f}s 即时回收")
    log(f"  接收: 'KEY <NAME> DOWN|UP' / 'KEY APP:<名称>|TOGGLE|NEXT|CYCLE|PICK|CLOSE DOWN' / 'KEY FOCUS_INPUT|CLICK DOWN' / 'KEY URL:<网址>|RUN:<命令> DOWN' / 'KEY MOUSE:MOVE:<dir>|SCROLL:<dir>|LCLICK|RCLICK|MODE:ON|OFF DOWN|UP' / 'KEY TARGET:SWITCH:<ATV|MAC|WIN> DOWN' / 'RAW <nxkc> DOWN|UP'(诊断) "
        f"| picker路由: {', '.join(sorted(PICKER_KEYS))} (socket={PICKER_SOCK}) | 注入输出→ {INJECT_LOG} | 诊断: ping / status")

    # name -> {"down": bool, "last": ts}  卡键自愈用
    keys = {}

    while True:
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            now = time.time()
            # 卡键自愈: DOWN 后长时间无活动（DOWN 连发会刷新 last）
            for name, st in keys.items():
                if st["down"] and (now - st["last"]) > STUCK_TIMEOUT:
                    log(f"!! 卡键自愈: {name} DOWN 后 {STUCK_TIMEOUT:.0f}s 无活动 → 补发 UP")
                    if fire(name, False):
                        st["down"] = False
                    st["last"] = now
            process_removals()
            continue
        except KeyboardInterrupt:
            log("收到 Ctrl-C, 退出")
            return
        text = data.decode("utf-8", "replace").strip()
        peer = f"{addr[0]}:{addr[1]}"
        now = time.time()

        parts = text.split()
        if len(parts) == 3 and parts[0] == "KEY" and parts[2] in ("DOWN", "UP"):
            name, phase = parts[1], parts[2]
            if name.startswith("APP:"):
                # v1.5: 应用动作（NSWorkspace 激活通道）—— 仅 DOWN 触发一次, UP 忽略
                if phase == "DOWN":
                    ok2 = do_app(name[4:])
                    log(f"RX {peer} -> {name} DOWN ({'已执行' if ok2 else '执行失败/忽略'})")
                else:
                    log(f"RX {peer} -> {name} UP (忽略: APP 动作仅 DOWN 触发)")
            elif name == "FOCUS_INPUT":
                # v1.8: 跳输入框 —— 仅 DOWN 触发（线程内执行, hs 调用不阻塞 UDP）
                if phase == "DOWN":
                    ok2 = do_focus_input()
                    log(f"RX {peer} -> KEY FOCUS_INPUT DOWN ({'已触发' if ok2 else '防抖忽略'})")
                else:
                    log(f"RX {peer} -> KEY FOCUS_INPUT UP (忽略)")
            elif name == "CLICK":
                # v1.9: 点击焦点元素 —— 仅 DOWN 触发（AXPress/坐标兜底, 线程内执行）
                if phase == "DOWN":
                    ok2 = do_click()
                    log(f"RX {peer} -> KEY CLICK DOWN ({'已触发' if ok2 else '防抖忽略'})")
                else:
                    log(f"RX {peer} -> KEY CLICK UP (忽略)")
            elif name.startswith("URL:"):
                # v1.11: 打开网页 —— 仅 DOWN 触发（open 拉起默认浏览器; per-url 防抖）
                if phase == "DOWN":
                    ok2 = do_url(name[4:])
                    log(f"RX {peer} -> {name} DOWN ({'已触发' if ok2 else '防抖忽略/失败'})")
                else:
                    log(f"RX {peer} -> {name} UP (忽略)")
            elif name.startswith("RUN:"):
                # v1.11: 执行命令 —— 仅 DOWN 触发（/bin/sh; per-cmd 防抖; 值不含空格）
                if phase == "DOWN":
                    ok2 = do_run(name[4:])
                    log(f"RX {peer} -> {name} DOWN ({'已触发' if ok2 else '防抖忽略/失败'})")
                else:
                    log(f"RX {peer} -> {name} UP (忽略)")
            elif name.startswith(("MOUSE:", "TARGET:SWITCH:")):
                # v1.13: 鼠标模式 —— 滑行/滚动按住语义（DOWN 启动/UP 停止）; 点击仅 DOWN
                # v1.15: TARGET:SWITCH:<ATV|MAC|WIN> 切换 HUD 复用同一串行 worker
                if not mouse_dispatch(name, phase):
                    log(f"RX {peer} -> {name} {phase} (辅助队列满, 丢弃)")
            elif name not in KEYMAP:
                log(f"RX {peer} -> {text!r} (未知动作名, 忽略)")
            else:
                down = (phase == "DOWN")
                # v1.7: 应用选择器模式 —— 方向/回车/Esc 路由给 AppPicker（不注入系统）
                if name in PICKER_KEYS and _picker_route(name, phase):
                    log(f"RX {peer} -> KEY {name} {phase} (picker 模式)")
                    continue
                st = keys.setdefault(name, {"down": False, "last": 0.0})
                ok2 = fire(name, down)
                if ok2:
                    st["down"] = down
                st["last"] = now
                log(f"RX {peer} -> KEY {name} {phase} ({'已提交' if ok2 else '提交失败'})")
        elif len(parts) == 3 and parts[0] == "RAW" and parts[2] in ("DOWN", "UP"):
            # 诊断探针: "RAW <nxkc> DOWN|UP" 直接注入原始 keycode（不查键表, 不进卡键守卫）
            try:
                nk = int(parts[1])
            except ValueError:
                nk = None
            if nk is None or not (0 <= nk <= 255):
                log(f"RX {peer} -> {text!r} (非法 keycode, 忽略)")
            else:
                ok2 = fire(nk, parts[2] == "DOWN")
                log(f"RX {peer} -> RAW {nk} {parts[2]} ({'已提交' if ok2 else '提交失败'})")
        elif text.lower() == "ping":
            s.sendto(b"pong", addr)
            log(f"RX {peer} -> ping (已回 pong)")
        elif text.lower() == "status":
            downs = [n for n, st in keys.items() if st["down"]]
            sv = "up" if serve_alive() else "down"
            msg = f"STATUS v{VERSION} port={PORT} serve={sv} picker={'on' if os.path.exists(PICKER_SOCK) else 'off'} down={','.join(downs) if downs else '-'} pending_rm={len(_pending_removals)}"
            s.sendto(msg.encode(), addr)
            log(f"RX {peer} -> status (serve={sv}, {('down=' + ','.join(downs)) if downs else 'idle'})")
        else:
            log(f"RX {peer} -> {text!r} (未知指令, 忽略)")

        process_removals()


if __name__ == "__main__":
    main()
