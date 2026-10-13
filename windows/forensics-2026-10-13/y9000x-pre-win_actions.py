#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
win_actions.py — Windows 遥控扩展动作 v1.11 (2026-10-13)
=======================================================
为 win_receiver v1.2+ 提供三类「Mac 对等」扩展动作（Mac 端参照:
key_bridge.py / app_switch.swift / hammerspoon/remotehub_focus.lua）:

  CLICK        点击「当前键盘焦点元素」—— 对齐 remotehub_focus.clickFocused()
               四段策略: ① 自身 Invoke → ② 直接子 Invoke → ③ 向上 ≤6 层 Invoke
                        → ④ 坐标兜底（元素中心鼠标点击, 尺寸门槛 w>8,h>4）
  FOCUS_INPUT  跳转到输入框 —— 对齐 remotehub_focus.focusInput()
               五阶段: ① 窗口修复（前台窗口 unmin+激活, 在 do_focus_input 内）
                      ② 缓存点（按 exe 记录窗口比例坐标）→ ③ 坐标网格（底部优先）
                      → ④ 树遍历（首个 Edit/ComboBox）→ ⑤ SetFocus + 读回验证
  APP:<x>      应用动作 —— 对齐 app_switch.swift:
               APP:CYCLE  全应用轮询（冻结快照 + 前台校验续期 30min）
               APP:TOGGLE 最近两应用回跳（{prev,cur} 状态）
               APP:NEXT   名称序循环下一个
               APP:PICK   应用选择器（图标网格 UI; ↑↓←→ 网格方向选择 / OK 打开 / 返回 取消 / 10s 自动关闭 / 长名滚动）
               APP:CLOSE  关闭当前前台应用（优雅退出——WM_CLOSE; 对齐 Mac app_switch close）
               APP:<名称> 切换（未运行则启动: App Paths → 开始菜单 lnk → PATH → cmd start）
  URL:<网址>    打开网页 —— startfile 拉起默认浏览器（仅 DOWN; 0.6s 防抖）
  RUN:<命令>    执行命令 —— cmd /c（仅 DOWN; 0.6s 防抖; 值不含空格——UDP 协议约束,
               含空格命令请写成脚本/批处理文件后填其路径）
  MOUSE:*      鼠标模式（v1.11, 由 win_receiver 专用路由直调 mouse_control —— 不走
               扩展动作 down-only 管道）:
               MOUSE:MOVE:UP|DOWN|LEFT|RIGHT  滑行移动（按住=连续滑; 补发保活刷新）
               MOUSE:SCROLL:UP|DOWN           连续滚动（按住=连续滚）
               MOUSE:LCLICK / MOUSE:RCLICK    当前位置点击（左/右; 仅 DOWN）
               引擎 = MouseGlide 滑行积分器（纯逻辑可测）: 加速 700px/s² / 上限
               1600px/s / 多方向叠加（斜向 √2 速, 对齐 Mac lua）/ 1.2s 无刷新看门狗
               自停（保活断流即刹车）/ 虚拟屏包围盒夹取。60Hz 常驻推进线程（懒启动）。
               Mac 对等 = key_bridge v1.13 + remotehub_focus.lua v1.2（参数两端一致）。

v1.11 变更（2026-10-13，鼠标模式 —— 遥控器 dpad 模拟鼠标, 用户需求）：
  · 新增 MouseGlide（策略层滑行积分器, 纯逻辑离线可测）+ mouse_control 分发入口
    （win_receiver v1.7 handle_mouse 调用; MOVE/SCROLL 双向 hold 语义）。
  · 新增 mouse_button_click（当前位置左/右键 SendInput; 不移动光标）+ _send_wheel
    （WHEEL_DELTA=120/notch, SCROLL_NPS=10 notch/s 对齐 Mac 900px/s 观感）。
  · 常量与 Mac 完全一致: MOUSE_ACCEL=700 / MOUSE_MAX=1600 / MOUSE_STALE=1.2 /
    MOUSE_TICK=1/60。展开常数不归一化（斜向 √2 速——与 lua 实装逐条对齐）。

v1.10 变更（2026-10-12，长按电源键「关闭当前应用」—— 用户需求, Mac + Windows 双端对等）：
  · 新增 APP:CLOSE（生产绑定 = keymap #116 电源键 long）—— 对齐 Mac（app_switch v1.2 close =
    NSRunningApplication.terminate 优雅退出; key_bridge v1.12 路由 + CLOSE_DEBOUNCE=2.0）。
  · 语义 = 优雅关闭: 前台顶层窗口 SendMessageTimeoutW(WM_CLOSE, SMTO_ABORTIFHUNG, 1.5s) ——
    应用走自身退出流程（未保存内容会弹保存确认, 不丢数据; 不用 TerminateProcess）。
    UWP（ApplicationFrameHost 宿主）先取真身子窗口（host_child_hwnd）再发; 桌面/任务栏等
    shell 窗口拒绝（对齐 Mac Finder 保护）。成功判定 = 窗口销毁 或 前台已切换（close_poll
    轮询 ≤2s, 纯逻辑注入可测）。多窗口应用只关前台该窗口（连续长按可依次关）——与 Mac
    整应用退出的差异为有意取舍（不误关同一应用的其余窗口）。
  · 防抖 2.0s（APP:CLOSE 专属, 对齐 Mac CLOSE_DEBOUNCE——关闭后前台必变, 防连关第二个应用）。

v1.9 变更（2026-10-12，选择器 v2.6 —— 用户实测「图标外围有一圈灰色底色, 没有融合进 UI」修复）：
  · ★ 选中格图标「透明融合」（双底色变体）：Tk PhotoImage 无 alpha 通道, 图标须预合成实底 →
    旧版仅合成「窗口灰底」一种; 选中格填充为 #6c84af 时, 图标方块的灰底 (#8a8a8a) 外露成
    「一圈灰色」。修复: 每图标生成两套合成变体（非选中=ICON_BG #8a8a8a / 选中=新增
    ICON_BG_SEL #6c84af）, _paint 选中切换时换用对应变体 → 透明区域分别贴合两种底色,
    对齐 Mac（NSImage alpha 天然透过选中 32% 蓝填充）。图标缓存键加 bg 维度; 离线可测。

v1.8 变更（2026-10-12，选择器 v2.5 —— 用户实测「颜色不太好看; 改成跟 Mac 版一样, 灰色」）：
  · ★ 配色对齐 Mac AppPicker（浅灰磨砂 HUD 风格; 色值由 Mac 实拍截图逐像素采样反推）:
    底 #151a21 → #8a8a8a（磨砂灰实色近似——HUD 属半透明材质, 取「深色背景下」的典型合成观感）;
    选中填充 #1b2c48 → #6c84af（系统蓝 32% 叠灰底之合成近似）; 选中边框 #3b82f6 → #017aff
    （macOS 系统蓝）; 文字由浅色系改近黑（#e8ecf1/#8b949e/#d7dee9 → #141414, 对齐浅色模式
    labelColor——hint/占位/名称两态同色）。ICON_BG 同步 (0x8a,0x8a,0x8a)（图标合成底色=窗口底）。

v1.7 变更（2026-10-11 深夜四期，选择器 v2.4 —— 用户实测「两行时上下键也左右移动 / 计算器图标不对」修复）：
  · ★ 网格方向导航（旧版 ↑/↓ 与 ←/→ 同为线性 ±1 —— 两行以上时 ↑↓ 不符合操作直觉）:
    新增 grid_move 纯逻辑 —— ↑/↓ = 垂直移动（相邻行同列优先; 该列缺失取最近列;
    首行 ↑ / 末行 ↓ 回绕到另一端）, ←/→ = 行内水平（行尾→下一行首, 即线性环绕）。
    单行 / 单列时 ↑↓ 自然退化为线性（与旧行为一致）。_poll 分派改走 grid_move。
  · ★ UWP / 系统自带应用真实图标（计算器实测「图标不对」——真身 exe（WindowsApps 下
    Calculator.exe）的内嵌资源 ≠ 系统显示图标; 显示图标由 shell 从应用清单资源解析）:
    新增 Shell 通路 —— 窗口 AUMID（SHGetPropertyStoreForWindow → PKEY_AppUserModel_ID;
    回退 GetApplicationUserModelId(pid)）→ shell:AppsFolder\\<AUMID> →
    IShellItemImageFactory.GetImage（ICONONLY|SCALEUP）→ HBITMAP → RGBA →
    复用既有后处理管线（裁白→补方→光学归一→合成→缩放）。UWP 条目优先 shell 通路,
    任一环节失败自动回退 exe 内嵌资源（设置齿轮等既有行为不回归）。触发条件 =
    宿主进程（ApplicationFrameHost）**或** 包应用路径（WindowsApps / 沉浸式控制面板;
    纯逻辑 is_uwp_path）——覆盖面扩至全部系统自带应用, 离线可测。
    COM 全走 ctypes 手写 vtable（不引入 comtypes 依赖; 结构与 _guid 解析离线可测）。

v1.2 变更（2026-10-11，URL: / RUN: 动作 —— 遥控一键「打开网页 / 执行命令」）：
  · 新增 URL:<网址>（startfile 默认浏览器）与 RUN:<命令>（cmd /c 执行）。
  · 仅 DOWN 触发、UP 忽略; 防抖 0.6s（与 CLICK/FOCUS_INPUT 同档）。
  · 值大小写保真（win_receiver v1.5 起 ext 动作传原始串——URL/命令不可被 upper 化）。
  · 与 Mac key_bridge v1.11 完全同构; T1 校验（t1_webui v2.10）: 前缀放行/禁空格/≤500。

v1.6 变更（2026-10-11 深夜三期，选择器 v2.3 —— 用户实测「界面颜色不好看 / 长名显示不全」修复）：
  · ★ 界面配色重做（与遥控台同色系贯通）：底 #23272e → #151a21（深炭冷调, 更沉稳）;
    选中填充 #2b4a7e → #1b2c48（哑光深蓝, 与 #3b82f6 亮蓝边框同调）; 名称双色——
    非选中 #d7dee9 / 选中 #ffffff。ICON_BG 同步 (0x15,0x1a,0x21)（图标合成底色=窗口底）。
  · ★ 长应用名滚动显示（旧版 name[:14] 硬截断、还被格边横向裁切 → 「显示不全」）:
    新增 fit_prefix（非选中: 像素预算内截断 + "…"）与 cycle_slice（选中: 跑马灯循环窗口）,
    选中项每 180ms 推进 1 字符（name + 3 空格环形）; 非选中项静态截断。纯逻辑（measure 注入）。

v1.5 变更（2026-10-11 深夜二期，选择器 v2.2 —— 用户实测「图标大小不一 / 切换时图标框在变」修复 + 补丁正式合入）：
  · ★ 图标框大小随名字变（根因）：cell 子件走 pack 布局, 但原代码调用
    cell.grid_propagate(False)（仅对 grid 管理的子件生效）→ 固定尺寸未生效,
    cell 宽被应用名文本撑开（实测 27~133px 不等）→ 选中蓝框大小变化 +
    窄格内 64px 图标被横向裁切。改为 cell.pack_propagate(False); 同步修正
    pick_layout 面板宽公式（补上每格 grid padx, 旧公式漏算 → 末列被裁 12px）,
    并在显示前按实际请求尺寸兜底校正窗口。
  · ★ 视觉尺寸归一 v2（光学）：v1.4 的 trim+square_pad 只统一了「画布」,
    圆形/长条内容与方形内容的视觉大小仍差（同径圆面积=方 78.5%）。新增
    optical_fit_rgba: 按「内容有效面积（alpha>8 像素数）√」归一到 OPTICAL_REF*px,
    直接置入 px×px 画布; 配套预乘双线性 scale_rgba（alpha 边缘不发黑）。
    参数: REF=0.84 / 放大上限 2.0 / 大边 ≤96% 画布 / 缩小下限 0.15。纯逻辑, 离线可测。
  · ★ 正式合入 Windows 真机回传补丁（20261011, 三处阻断级——不回传前图标恒退化占位）:
    ① apps_from_windows 增补 "exe_key"（原 _icon_photo_for 只读此键, 而产出是 "key"
      → 键恒空 → 全部首字母占位）;
    ② _icon_photo_for / app_display_name 键名双重兼容（exe_key → key 回退）;
    ③ PhotoImage 改 base64 解码 + latin1 传入（Tk 8.6 的 -data 不解码 base64）。

v1.4 变更（2026-10-11 深夜，选择器 v2.1 —— 用户实测三反馈修正）：
  · ★ 图标尺寸归一化：经典图标画布内留白多、现代图标满幅 → 网格里视觉大小不齐。
    新增 trim_rgba（按 alpha 求内容外接框裁空白）+ square_pad_rgba（透明补正方形,
    保比例居中）→ 每个图标内容都撑满同一方框。纯逻辑, 离线可测。
  · ★ 应用名净化：标签不再直接用窗口标题（"main.py - Visual Studio Code"），改为
    exe 版本资源 FileDescription（Code.exe→"Visual Studio Code"、WeChat.exe→"微信"）,
    失败退路 = exe 主名去 .exe。纯逻辑 choose_display_name, 离线可测。
  · ★ UWP 真实图标：设置/计算器等窗口宿主进程是 ApplicationFrameHost.exe（直接提取
    得到的是宿主壳通用图标——用户实测「设置用了别的图标」的根因）。新增 host_child_pid：
    枚举子窗口找真实应用进程（设置=SystemSettings.exe）, exe/图标/名称全部改用真身。

v1.3 变更（2026-10-11，选择器 v2 —— 崩溃根治 + 图标网格 UI + 高 DPI 适配）：
  · ★ 崩溃根治：v1.1 每次 PICK 新开线程创建/销毁一个独立 Tk 解释器 —— 解释器对象
    在「非创建线程」被 GC 回收时触发 Tcl_AsyncDelete（Tk 弹 fatal 报错窗 + 进程
    abort; 触发时机随 GC ⇒ 用户实测「试几下才炸」）。v2 改为**常驻 Tk 线程**：
    进程内只创建一次 Tk root, 每次 PICK 只开关 Toplevel; 全部 Tk 回调异常改写为
    日志（report_callback_exception）, 杜绝任何报错弹窗。
  · UI 对齐 Mac AppPicker：6 列图标网格（图标 + 名称）、←/↑ = 上一个 · →/↓ = 下一个
    （环绕移动）、初始选中第 2 项（≈上一应用）、10s 无操作自动关闭、鼠标点击/双击可用。
  · 图标提取：PrivateExtractIconsW → DIB 像素（无 alpha 用 AND 掩码兜底合成）→
    v1.4 裁空白 + 补方 → v1.5 光学归一（√面积统一视觉尺寸, 置入 px 画布）→
    纯 Python 背景合成 + 双线性缩放 → PPM → tk.PhotoImage。逐 exe 缓存（含像素
    尺寸维度）, 二次打开零成本; 任一步失败退化为首字母占位, 不影响选择器主流程。
  · ★ 高 DPI / 多屏：全部像素几何（单元格/图标/间距）按系统 DPI 缩放
    （winfo_fpixels/96, 1.0~3.0 钳制）; 图标按目标像素直接提取（100%→64px,
    150%→96px, 200%→128px）保证清晰; 显示位置 = 光标所在显示器工作区居中
    （GetMonitorInfo 规避任务栏; 失败回退主屏）。纯逻辑 pick_layout 离线可测。
  · 快捷键提示行: ↑ ↓ ← → 选择 · OK 打开 · 返回 取消 · 10s 自动关闭。

v1.1 变更（2026-10-11，APP:PICK 选择器修复 —— 用户实测「窗口难看 + 上下键无法切换」）：
  · ★ 按键直连路由（picker_route）：选择器打开期间, win_receiver 把遥控
    UP/DOWN/ENTER/ESC/BACKSPACE 直接投递进选择器（消息队列）, 不再依赖系统键盘焦点。
    根因：本进程为计划任务/后台上下文, 其 tkinter 窗口无法保证获得 Windows 前台激活,
    注入的按键会落到别的窗口 → 上下键「无反应」。路由绕过整个焦点模型, 100% 可靠。
  · 视觉重做：暗色一体化（#23272e 底 + #3b82f6 高亮, 与网页遥控台同色系）、
    无滚动条、按内容自适应高度、选中高亮手动绘制（不依赖窗口焦点态）、标题/提示行。
  · 抢前台仅「尽力而为」（focus_force + SetForegroundWindow, 不再用最小化→还原闪屏）;
    鼠标交互（点击/双击/滚轮）天然可用, 作为第二通道。

架构（两分层, 便于离线打桩测试）:
  A. 平台层  Windows only（ctypes 窗口原语 + uiautomation 晚绑定）——非 Windows 全 None
  B. 策略层  纯逻辑（依赖注入 backend / click_at）——macOS 上可用 FakeBackend 测试
     离线测试: actions_offline_test.py（Mac 可跑）
     注: picker_route 的「是否消化」判定为纯逻辑（不触 Tk）——离线可测。

依赖: pip install uiautomation（缺失时 CLICK/FOCUS_INPUT 优雅降级, APP:* 不受影响）
防抖: 由调用方（win_receiver）在收包线程执行 —— debounce_for():
      CLICK / FOCUS_INPUT = 0.6s, APP:CLOSE = 2.0s, 其余 APP:* = 0.35s（与 Mac key_bridge 对齐）
状态: state/app_switch_win.json（toggle/cycle）, state/focus_cache.json（输入框缓存）
线程: UIA 后端须在「长期存活的专用线程」首次初始化（COM apartment 一致性）;
      win_receiver 用 action-worker 线程承载全部 handle() 调用。
"""
import base64
import ctypes
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from ctypes import wintypes as wt

VERSION = "1.11"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
IS_WIN = (os.name == "nt")

# ------------------------------------------------------------------ 日志注入
_log = print


def init(log_fn):
    """由主程序注入日志函数（win_receiver 的异步 log）。"""
    global _log
    _log = log_fn


def _logv(msg):
    try:
        _log(msg)
    except Exception:
        pass


# ================================================================
# A. 平台层（Windows only；非 Windows 下全为 None）
# ================================================================
_user32 = _kernel32 = _dwmapi = _gdi32 = _shell32 = _version = None
_dpi_state = "not-set"

SHELL_CLASSES = {
    "Progman", "WorkerW",                          # 桌面
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd",     # 任务栏
    "Windows.UI.Core.CoreWindow",                  # UWP 外壳 / 搜索
    "ForegroundStaging", "MultitaskingViewFrame",  # 任务视图
    "Windows.Internal.Shell.TabProxyWindow",       # Win11 小组件桥
}

if IS_WIN:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    try:
        _dwmapi = ctypes.windll.dwmapi
    except Exception:
        _dwmapi = None
    try:
        _gdi32 = ctypes.windll.gdi32
        _shell32 = ctypes.windll.shell32
    except Exception:
        _gdi32 = _shell32 = None
    try:
        _version = ctypes.windll.version
    except Exception:
        _version = None

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                    ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                    ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                    ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND),
                    ("rcCaret", wt.RECT)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]

    # --- v1.3: 图标 / DIB / 显示器信息 ---
    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                    ("hbmMask", wt.HANDLE), ("hbmColor", wt.HANDLE)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wt.LONG), ("bmWidth", wt.LONG), ("bmHeight", wt.LONG),
                    ("bmWidthBytes", wt.LONG), ("bmPlanes", wt.WORD), ("bmBitsPixel", wt.WORD),
                    ("bmBits", ctypes.c_void_p)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                    ("dwFlags", wt.DWORD)]

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [("hIcon", wt.HANDLE), ("iIcon", ctypes.c_int), ("dwAttributes", wt.DWORD),
                    ("szDisplayName", wt.WCHAR * 260), ("szTypeName", wt.WCHAR * 80)]

    # --- 原型（64 位句柄安全） ---
    _user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    _user32.EnumWindows.restype = wt.BOOL
    _user32.IsWindowVisible.argtypes = [wt.HWND]
    _user32.IsWindowVisible.restype = wt.BOOL
    _user32.IsIconic.argtypes = [wt.HWND]
    _user32.IsIconic.restype = wt.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wt.DWORD
    _user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.SetForegroundWindow.argtypes = [wt.HWND]
    _user32.SetForegroundWindow.restype = wt.BOOL
    _user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wt.BOOL
    _user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    _user32.AttachThreadInput.restype = wt.BOOL
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursorPos.restype = wt.BOOL
    _user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    _user32.GetWindowRect.restype = wt.BOOL
    _user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    _user32.GetAncestor.restype = wt.HWND
    _user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
    _user32.GetGUIThreadInfo.restype = wt.BOOL
    _user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = wt.UINT
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _kernel32.GetCurrentThreadId.restype = wt.DWORD
    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                     ctypes.POINTER(wt.DWORD)]
    _kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.CloseHandle.restype = wt.BOOL
    if _dwmapi is not None:
        _dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    # --- v1.3: 图标提取 / DIB / 多屏定位 ---
    _user32.GetDC.argtypes = [wt.HWND]
    _user32.GetDC.restype = wt.HANDLE
    _user32.ReleaseDC.argtypes = [wt.HWND, wt.HANDLE]
    _user32.ReleaseDC.restype = ctypes.c_int
    _user32.GetIconInfo.argtypes = [wt.HANDLE, ctypes.c_void_p]
    _user32.GetIconInfo.restype = wt.BOOL
    _user32.DestroyIcon.argtypes = [wt.HANDLE]
    _user32.DestroyIcon.restype = wt.BOOL
    _user32.PrivateExtractIconsW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, ctypes.POINTER(wt.HANDLE),
                                             ctypes.POINTER(wt.UINT), wt.UINT, wt.UINT]
    _user32.PrivateExtractIconsW.restype = wt.UINT
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    _user32.GetCursorPos.restype = wt.BOOL
    _user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
    _user32.MonitorFromPoint.restype = wt.HANDLE
    _user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.c_void_p]
    _user32.GetMonitorInfoW.restype = wt.BOOL
    _gdi32.GetDIBits.argtypes = [wt.HANDLE, wt.HANDLE, wt.UINT, wt.UINT, ctypes.c_void_p,
                                 ctypes.c_void_p, wt.UINT]
    _gdi32.GetDIBits.restype = ctypes.c_int
    _gdi32.GetObjectW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p]
    _gdi32.GetObjectW.restype = ctypes.c_int
    _gdi32.DeleteObject.argtypes = [wt.HANDLE]
    _gdi32.DeleteObject.restype = wt.BOOL
    _shell32.SHGetFileInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.UINT, wt.UINT]
    _shell32.SHGetFileInfoW.restype = ctypes.c_void_p
    _user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
    _user32.EnumChildWindows.restype = wt.BOOL
    # --- v1.10: 关闭当前应用（WM_CLOSE） ---
    _user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                                            wt.UINT, wt.UINT, ctypes.POINTER(ULONG_PTR)]
    _user32.SendMessageTimeoutW.restype = ULONG_PTR
    _user32.IsWindow.argtypes = [wt.HWND]
    _user32.IsWindow.restype = wt.BOOL
    if _version is not None:
        _version.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.DWORD)]
        _version.GetFileVersionInfoSizeW.restype = wt.DWORD
        _version.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
        _version.GetFileVersionInfoW.restype = wt.BOOL
        _version.VerQueryValueW.argtypes = [ctypes.c_void_p, wt.LPCWSTR,
                                            ctypes.POINTER(ctypes.c_void_p),
                                            ctypes.POINTER(wt.UINT)]
        _version.VerQueryValueW.restype = wt.BOOL

    # --- v1.7: UWP 图标（Shell AppsFolder 通路） ---
    _shell32.SHGetPropertyStoreForWindow.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_void_p]
    _shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
    _shell32.SHCreateItemFromParsingName.argtypes = [wt.LPCWSTR, ctypes.c_void_p,
                                                     ctypes.c_void_p, ctypes.c_void_p]
    _shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    _kernel32.GetApplicationUserModelId.argtypes = [wt.HANDLE,
                                                    ctypes.POINTER(ctypes.c_uint32), wt.LPWSTR]
    _kernel32.GetApplicationUserModelId.restype = ctypes.c_long

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    DWMWA_CLOAKED = 14
    SW_RESTORE = 9
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GA_ROOT = 2
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    _NO_WINDOW = 0x08000000
    WM_CLOSE = 0x0010                 # v1.10: 关闭当前应用
    SMTO_ABORTIFHUNG = 0x0002         # v1.10: 目标无响应立即返回（不阻塞调用线程）
else:
    _NO_WINDOW = 0


def ensure_dpi_aware():
    """进程 DPI 感知（UIA 坐标与 SetCursorPos 一致性的前提；须在任何窗口创建前调用）。"""
    global _dpi_state
    if not IS_WIN:
        _dpi_state = "n/a"
        return
    try:
        _user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        _user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
        if _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            _dpi_state = "per-monitor-v2"
            return
    except Exception:
        pass
    try:
        if _user32.SetProcessDPIAware():
            _dpi_state = "system-aware"
            return
    except Exception:
        pass
    _dpi_state = "not-set(assumed)"


def prepare():
    """主程序启动时调用：平台层一次性准备。"""
    if IS_WIN:
        ensure_dpi_aware()


# ---------------------------------------------------------------- 窗口原语
def proc_exe_name(pid):
    """pid -> 'notepad.exe'（失败返回 'pid<NNN>'）。"""
    if not IS_WIN:
        return "pid%d" % pid
    try:
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return "pid%d" % pid
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(1024)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value) or ("pid%d" % pid)
            return "pid%d" % pid
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        return "pid%d" % pid


def proc_exe_path(pid):
    """v1.3: pid -> 完整 exe 路径（图标提取用; 失败 ''）。"""
    if not IS_WIN:
        return ""
    try:
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(1024)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return ""
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        return ""


HOST_PROCESS_KEY = "applicationframehost.exe"   # UWP 窗口宿主进程（设置/计算器等）


def is_host_process(exe_key):
    """v1.4 纯逻辑: 是否 UWP 窗口宿主进程（ApplicationFrameHost.exe）。
    宿主窗口背后才是真实应用进程（设置=SystemSettings.exe 等）——图标/名称需换真身。"""
    return (exe_key or "").lower() == HOST_PROCESS_KEY


def host_child_pid(hwnd):
    """v1.4 Windows: ApplicationFrameHost 窗口 → 真实应用子进程 pid（失败 0）。
    优先可见子窗口; 全不可见时取首个不同 PID 的兜底候选。"""
    if not IS_WIN or not hwnd:
        return 0
    try:
        hp = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(hp))
        found = {"pid": 0, "host": int(hp.value)}

        def _cb(ch, lparam):
            try:
                p = wt.DWORD(0)
                _user32.GetWindowThreadProcessId(ch, ctypes.byref(p))
                if p.value and p.value != found["host"]:
                    if not found["pid"]:
                        found["pid"] = int(p.value)     # 兜底候选（首个不同 PID）
                    if _user32.IsWindowVisible(ch):
                        found["pid"] = int(p.value)     # 更优候选（可见）→ 采用并停止
                        return False
            except Exception:
                pass
            return True

        _user32.EnumChildWindows(hwnd, WNDENUMPROC(_cb), 0)
        return found["pid"]
    except Exception:
        return 0


def enum_windows():
    """枚举顶层窗口（z 序, 顶→底）。
    已过滤: 不可见 / WS_EX_TOOLWINDOW / 无标题 / cloaked / shell 类。
    返回 [{"hwnd","title","pid","exe","exe_key","minimized"}]（最小化窗口保留并标记）。"""
    out = []
    if not IS_WIN:
        return out

    def _cb(hwnd, lparam):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            ex = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex & WS_EX_TOOLWINDOW:
                return True
            n = _user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            if _dwmapi is not None:
                val = wt.DWORD(0)
                try:
                    _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED,
                                                  ctypes.byref(val), ctypes.sizeof(val))
                    if val.value:
                        return True
                except Exception:
                    pass
            cbuf = ctypes.create_unicode_buffer(128)
            _user32.GetClassNameW(hwnd, cbuf, 128)
            if cbuf.value in SHELL_CLASSES:
                return True
            tbuf = ctypes.create_unicode_buffer(n + 2)
            _user32.GetWindowTextW(hwnd, tbuf, n + 2)
            pid = wt.DWORD(0)
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = proc_exe_name(pid.value)
            rpid = int(pid.value)
            uwp = False                                # v1.7: UWP 宿主来源标记（图标通路分流）
            if is_host_process(exe.lower()):           # v1.4: UWP 窗口 → 真实应用进程
                uwp = True
                cp = host_child_pid(hwnd)
                if cp:
                    rpid = cp
                    exe = proc_exe_name(cp)
            out.append({"hwnd": hwnd, "title": tbuf.value, "pid": rpid,
                        "exe": exe, "exe_key": exe.lower(), "uwp": uwp,
                        "minimized": bool(_user32.IsIconic(hwnd))})
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception as e:
        _logv("enum_windows error: %s" % e)
    return out


def exe_key_of_hwnd(hwnd):
    if not IS_WIN or not hwnd:
        return ""
    try:
        pid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return proc_exe_name(pid.value).lower()
    except Exception:
        return ""


def get_focus_hwnd():
    """前台线程的焦点 HWND（UIA GetFocusedElement 失败时的兜底路径）。"""
    if not IS_WIN:
        return None
    try:
        fg = _user32.GetForegroundWindow()
        if not fg:
            return None
        tid = _user32.GetWindowThreadProcessId(fg, None)
        if not tid:
            return None
        gti = GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(GUITHREADINFO)
        if _user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
            return gti.hwndFocus or gti.hwndActive or None
    except Exception:
        pass
    return None


def _send_alt_tap():
    """发送一次 Alt 敲击——解除 SetForegroundWindow 的前台锁定限制。"""
    if not IS_WIN:
        return
    for up in (False, True):
        inp = INPUT()
        inp.type = 1                                # INPUT_KEYBOARD
        inp.u.ki.wVk = 0x12                         # VK_MENU
        inp.u.ki.wScan = 0
        inp.u.ki.dwFlags = 0x0002 if up else 0      # KEYEVENTF_KEYUP
        inp.u.ki.time = 0
        inp.u.ki.dwExtraInfo = 0
        try:
            _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        except Exception:
            pass


def force_foreground(hwnd):
    """尽最大努力把 hwnd 带到前台。
    Windows 前台锁定: 后台进程(非前台进程自身/非前台进程派生/无近期输入)直接
    SetForegroundWindow 会被拒。实测本机: Alt 敲击无效、AttachThreadInput 返回 0(失败)，
    而「最小化→还原」可使 SetForegroundWindow 成功 —— 故作为可靠兜底。
    [Windows 本地补丁 2026-10-11: 追加兜底 3; 原始逻辑保留]"""
    if not IS_WIN or not hwnd:
        return False
    try:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        if _user32.SetForegroundWindow(hwnd):
            return True
        # 兜底 1: Alt 敲击（部分环境可解锁前台权限）
        _send_alt_tap()
        if _user32.SetForegroundWindow(hwnd):
            return True
        # 兜底 2: AttachThreadInput 到当前前台线程
        fg = _user32.GetForegroundWindow()
        if fg and fg != hwnd:
            tid_fg = _user32.GetWindowThreadProcessId(fg, None)
            tid_me = _kernel32.GetCurrentThreadId()
            if tid_fg and tid_fg != tid_me:
                _user32.AttachThreadInput(tid_me, tid_fg, True)
                try:
                    ok = bool(_user32.SetForegroundWindow(hwnd))
                finally:
                    _user32.AttachThreadInput(tid_me, tid_fg, False)
                if ok:
                    return True
        # 兜底 3: 最小化→还原（Windows 实测有效）
        _user32.ShowWindow(hwnd, 6)      # SW_MINIMIZE
        _user32.ShowWindow(hwnd, 9)      # SW_RESTORE
        return bool(_user32.SetForegroundWindow(hwnd))
    except Exception as e:
        _logv("force_foreground error: %s" % e)
        return False


def mouse_click(x, y):
    """物理鼠标左键点击（SetCursorPos + SendInput down/up）。"""
    if not IS_WIN:
        return False
    try:
        if not _user32.SetCursorPos(int(x), int(y)):
            return False
        time.sleep(0.05)
        ok = True
        for flag, pause in ((0x0002, 0.02), (0x0004, 0.0)):    # LEFTDOWN, LEFTUP
            inp = INPUT()
            inp.type = 0                                        # INPUT_MOUSE
            inp.u.mi.dx = 0
            inp.u.mi.dy = 0
            inp.u.mi.mouseData = 0
            inp.u.mi.dwFlags = flag
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0
            ok = (_user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1) and ok
            if pause:
                time.sleep(pause)
        return ok
    except Exception:
        return False


def foreground_ctx():
    """前台窗口上下文: {"hwnd","rect","exe_key"}；失败 None。"""
    if not IS_WIN:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        rc = wt.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return None
        pid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = proc_exe_name(pid.value)
        return {"hwnd": hwnd, "rect": (rc.left, rc.top, rc.right, rc.bottom),
                "exe_key": exe.lower()}
    except Exception:
        return None


# ================================================================
# v1.11: 鼠标模式（滑行引擎 —— 对齐 Mac remotehub_focus.lua v1.2 逐参数）
# ================================================================
MOUSE_ACCEL = 700.0        # 线性加速度 px/s²
MOUSE_MAX = 1600.0         # 速度上限 px/s
MOUSE_TICK = 1.0 / 60      # 推进周期
MOUSE_STALE = 1.2          # 方向无刷新超时（秒）—— 保活断流即自停
SCROLL_NPS = 10.0          # 滚动速度 notch/秒（WHEEL_DELTA=120; 对齐 Mac 900px/s 观感）
WHEEL_DELTA = 120

MOUSE_VEC = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


class MouseGlide:
    """v1.11 策略层: 滑行积分器（纯逻辑, 离线可测）。

    语义: MOVE/SCROLL 均为「按住」—— start(dir) 记录/刷新时间戳（重复 start = 保活）,
    stop(dir) 移除。多方向叠加不归一化（斜向 √2 速, 对齐 lua）; 对向相消。
    看门狗: 超过 MOUSE_STALE 无刷新的方向在 step/busy 时自动清除（up 丢包兜底刹车）。
    """

    def __init__(self):
        self.moves = {}        # D -> last refresh monotonic
        self.scrolls = {}      # D -> last refresh monotonic
        self.speed = 0.0
        self.scroll_accum = 0.0

    def start(self, kind, d, now):
        (self.moves if kind == "move" else self.scrolls)[d] = now
        return True

    def stop(self, kind, d):
        (self.moves if kind == "move" else self.scrolls).pop(d, None)
        return True

    def stop_all(self):
        self.moves.clear()
        self.scrolls.clear()
        self.speed = 0.0

    def _sweep(self, now):
        for d in [d for d, ts in self.moves.items() if now - ts > MOUSE_STALE]:
            del self.moves[d]
        for d in [d for d, ts in self.scrolls.items() if now - ts > MOUSE_STALE]:
            del self.scrolls[d]

    def busy(self, now):
        self._sweep(now)
        return bool(self.moves or self.scrolls)

    def step(self, now, cur, bounds):
        """推进一格。返回 ((nx, ny) 或 None, wheel_notches 或 None)。
        cur=(x,y) 当前光标; bounds=(minx, miny, maxx, maxy) 虚拟屏包围盒（max 排他）。"""
        self._sweep(now)
        npos = None
        if self.moves:
            self.speed = min(MOUSE_MAX, self.speed + MOUSE_ACCEL * MOUSE_TICK)
            vx = sum(MOUSE_VEC[d][0] for d in self.moves)
            vy = sum(MOUSE_VEC[d][1] for d in self.moves)
            minx, miny, maxx, maxy = bounds
            nx = max(minx + 1, min(maxx - 2, cur[0] + vx * self.speed * MOUSE_TICK))
            ny = max(miny + 1, min(maxy - 2, cur[1] + vy * self.speed * MOUSE_TICK))
            npos = (nx, ny)
        else:
            self.speed = 0.0
        wheel = None
        if self.scrolls:
            dy = 0.0
            if "UP" in self.scrolls:
                dy += 1.0
            if "DOWN" in self.scrolls:
                dy -= 1.0
            if dy:
                self.scroll_accum += dy * SCROLL_NPS * MOUSE_TICK
                n = int(self.scroll_accum)
                if n:
                    self.scroll_accum -= n
                    wheel = n
        return npos, wheel


def _get_cursor_pos():
    if not IS_WIN:
        return None
    try:
        pt = wt.POINT()
        if _user32.GetCursorPos(ctypes.byref(pt)):
            return (pt.x, pt.y)
    except Exception:
        pass
    return None


def _set_cursor_pos(x, y):
    if not IS_WIN:
        return False
    try:
        return bool(_user32.SetCursorPos(int(x), int(y)))
    except Exception:
        return False


def _screen_bounds():
    """虚拟屏包围盒 (minx, miny, maxx, maxy)（max 排他, 对齐 lua fullFrame 语义）。"""
    if not IS_WIN:
        return (0, 0, 2560, 1440)
    try:
        x = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if w > 0 and h > 0:
            return (x, y, x + w, y + h)
    except Exception:
        pass
    return (0, 0, 2560, 1440)


def _send_wheel(notches):
    """滚轮 SendInput; notches>0 = 向上滚（WHEEL_DELTA=120/notch）。"""
    if not IS_WIN:
        return False
    ok = True
    try:
        for _ in range(abs(int(notches))):
            inp = INPUT()
            inp.type = 0                                   # INPUT_MOUSE
            inp.u.mi.dx = 0
            inp.u.mi.dy = 0
            inp.u.mi.mouseData = (WHEEL_DELTA if notches > 0 else -WHEEL_DELTA) & 0xFFFFFFFF
            inp.u.mi.dwFlags = 0x0800                      # MOUSEEVENTF_WHEEL
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0
            ok = (_user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1) and ok
    except Exception:
        return False
    return ok


def mouse_button_click(button="left"):
    """v1.11: 当前位置点击（不移动光标, 对齐 Mac mouseClick）; button=left|right。"""
    if not IS_WIN:
        return False
    try:
        down, up = (0x0008, 0x0010) if button == "right" else (0x0002, 0x0004)
        ok = True
        for flag, pause in ((down, 0.02), (up, 0.0)):
            inp = INPUT()
            inp.type = 0
            inp.u.mi.dx = 0
            inp.u.mi.dy = 0
            inp.u.mi.mouseData = 0
            inp.u.mi.dwFlags = flag
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0
            ok = (_user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1) and ok
            if pause:
                time.sleep(pause)
        return ok
    except Exception:
        return False


_glide = MouseGlide()
_glide_lock = threading.Lock()
_glide_thread = None


def _ensure_glide_thread():
    """懒启动 60Hz 推进线程（常驻 daemon; 空闲 tick 仅 µs 级）。"""
    global _glide_thread
    if not IS_WIN:
        return
    t = _glide_thread
    if t is not None and t.is_alive():
        return
    _glide_thread = threading.Thread(target=_glide_worker, daemon=True, name="mouse-glide")
    _glide_thread.start()


def _glide_worker():
    while True:
        time.sleep(MOUSE_TICK)
        try:
            now = time.monotonic()
            with _glide_lock:
                if not _glide.busy(now):
                    continue
            cur = _get_cursor_pos()
            if cur is None:
                continue
            with _glide_lock:
                npos, wheel = _glide.step(now, cur, _screen_bounds())
            if npos is not None and npos != cur:
                _set_cursor_pos(npos[0], npos[1])
            if wheel:
                _send_wheel(wheel)
        except Exception as e:
            _logv("mouse glide error: %s" % e)


def mouse_control(action, phase):
    """v1.11: MOUSE:* 动作入口（win_receiver v1.7 专用路由调用; 收包线程直呼）。
    MOVE/SCROLL = 按住语义（DOWN 启动/保活刷新, UP 停止）; LCLICK/RCLICK 仅 DOWN。
    返回详情字符串（进日志）。"""
    a = (action or "").upper()
    ph = (phase or "").upper()
    now = time.monotonic()
    if a.startswith("MOUSE:MOVE:"):
        d = a.rsplit(":", 1)[-1]
        if d not in MOUSE_VEC:
            return "ERR bad-dir %s" % action
        with _glide_lock:
            if ph == "DOWN":
                _glide.start("move", d, now)
            else:
                _glide.stop("move", d)
        if ph == "DOWN":
            _ensure_glide_thread()
        return "move %s %s" % (d, "on" if ph == "DOWN" else "off")
    if a.startswith("MOUSE:SCROLL:"):
        d = a.rsplit(":", 1)[-1]
        if d not in ("UP", "DOWN"):
            return "ERR bad-scroll %s" % action
        with _glide_lock:
            if ph == "DOWN":
                _glide.start("scroll", d, now)
            else:
                _glide.stop("scroll", d)
        if ph == "DOWN":
            _ensure_glide_thread()
        return "scroll %s %s" % (d, "on" if ph == "DOWN" else "off")
    if a == "MOUSE:LCLICK":
        if ph != "DOWN":
            return "lclick ignored (up)"
        return "lclick %s" % ("ok" if mouse_button_click("left") else "FAIL")
    if a == "MOUSE:RCLICK":
        if ph != "DOWN":
            return "rclick ignored (up)"
        return "rclick %s" % ("ok" if mouse_button_click("right") else "FAIL")
    return "unknown mouse action: %s" % action


def fix_foreground_window():
    """对前台窗口做 unmin + 激活（对齐 Mac focusWindowOf: unmin/raise/main/focus）。"""
    if not IS_WIN:
        return "no-win"
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return "no-fg"
        fixed = []
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
            fixed.append("unmin")
        force_foreground(hwnd)
        fixed.append("raise")
        return "+".join(fixed)
    except Exception as e:
        return "err:%s" % e


# ================================================================
# B1. UIA 封装（uiautomation 包晚绑定；接口固定, FakeBackend 同构）
# ================================================================
CT_EDIT = 50004        # UIA_EditControlTypeId
CT_COMBOBOX = 50003    # UIA_ComboBoxControlTypeId
CT_DOCUMENT = 50030    # UIA_DocumentControlTypeId
CT_WINDOW = 50032      # UIA_WindowControlTypeId（桌面根过滤用）
CT_PANE = 50033        # UIA_PaneControlTypeId

_uia_lock = threading.Lock()
_uia_backend = None
_uia_error = ""


def uia_probe():
    """仅探测包可用性（不初始化 COM / 不创建实例；任意线程可调用）。"""
    try:
        import importlib.util
        if importlib.util.find_spec("uiautomation") is None:
            return "missing (pip install uiautomation)"
        return "ready"
    except Exception as e:
        return "error: %s" % e


class RealUia(object):
    """uiautomation 包封装。后端接口（FakeBackend 必须同构）:
    focused / from_point / from_handle / children / parent / ctrl_type / name
    / rect / invoke / set_focus / has_focus / find_type"""

    def __init__(self, auto):
        self.auto = auto

    def focused(self):
        try:
            return self.auto.GetFocusedControl()
        except Exception:
            return None

    def from_point(self, x, y):
        try:
            return self.auto.ControlFromPoint(int(x), int(y))
        except Exception:
            return None

    def from_handle(self, hwnd):
        try:
            return self.auto.ControlFromHandle(int(hwnd))
        except Exception:
            return None

    def children(self, elem):
        try:
            return list(elem.GetChildren())
        except Exception:
            return []

    def parent(self, elem):
        try:
            return elem.GetParentControl()
        except Exception:
            return None

    def ctrl_type(self, elem):
        try:
            return int(elem.ControlType)
        except Exception:
            return None

    def name(self, elem):
        try:
            return str(elem.Name or "")
        except Exception:
            return ""

    def rect(self, elem):
        try:
            r = elem.BoundingRectangle
            l, t, rr, b = int(r.left), int(r.top), int(r.right), int(r.bottom)
            if rr <= l and b <= t:
                return None
            return (l, t, rr, b)
        except Exception:
            return None

    def invoke(self, elem):
        try:
            p = elem.GetInvokePattern()
            if p is None:
                return False
            p.Invoke()
            return True
        except Exception:
            return False

    def set_focus(self, elem):
        try:
            elem.SetFocus()
            return True
        except Exception:
            return False

    def has_focus(self, elem):
        try:
            return bool(elem.HasKeyboardFocus)
        except Exception:
            return None

    def find_type(self, root, type_id):
        """深度优先找首个指定 ControlType 的子孙（原生搜索 + 全局搜索超时保护）。"""
        try:
            return root.Control(searchDepth=0xFFFFFFFF, ControlType=type_id)
        except Exception:
            return None


def get_uia():
    """获取 UIA 后端（晚绑定）。
    注意: 首次调用所在线程即 COM apartment 归属线程——须为长期存活的专用线程
    （win_receiver 的 action-worker），之后全部 UIA 调用都应来自同一线程。"""
    global _uia_backend, _uia_error
    if _uia_backend is not None:
        return _uia_backend
    if not IS_WIN:
        return None
    with _uia_lock:
        if _uia_backend is not None:
            return _uia_backend
        try:
            try:
                # 显式 MTA（UIA 客户端推荐; 免消息泵）; 已初始化时返回非零错误码可忽略
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)
            except Exception:
                pass
            import uiautomation as auto
            try:
                auto.SetGlobalSearchTimeout(3)
            except Exception:
                pass
            _uia_backend = RealUia(auto)
            _uia_error = ""
        except Exception as e:
            _uia_error = str(e)
            _uia_backend = None
        return _uia_backend


# ================================================================
# B2. 策略层（纯逻辑, Mac 可打桩测试）
# ================================================================
GRID_X = (0.5, 0.62, 0.74, 0.38, 0.86, 0.26)
GRID_Y = (0.85, 0.82, 0.88, 0.78, 0.90, 0.72, 0.62, 0.50, 0.40, 0.30, 0.20, 0.12)


def _label(uia, elem):
    try:
        return "type=%s name=%s" % (uia.ctrl_type(elem), (uia.name(elem) or "")[:36])
    except Exception:
        return "?"


def is_input_like(uia, elem, win_w, win_h):
    """网格/缓存点的可编辑判定:
    Edit/ComboBox -> 直接接受; Document -> 仅当矩形明显小于窗口（输入框特征, 页面根排除）。"""
    if elem is None:
        return False
    t = uia.ctrl_type(elem)
    if t in (CT_EDIT, CT_COMBOBOX):
        return True
    if t == CT_DOCUMENT:
        r = uia.rect(elem)
        if not r:
            return False
        ew, eh = r[2] - r[0], r[3] - r[1]
        if ew <= 0 or eh <= 0:
            return False
        return (eh < win_h * 0.55) or (ew < win_w * 0.60)
    return False


def click_strategy(uia, elem, click_at):
    """四段点击（对齐 Mac remotehub_focus.clickFocused）。
    click_at(x, y) -> bool 为坐标兜底注入函数（测试可注入记录器）。
    返回 (ok, detail)。"""
    if elem is None:
        return (False, "NOFOCUS")
    if uia.invoke(elem):                                   # ① 自身
        return (True, "press self %s" % _label(uia, elem))
    for ch in uia.children(elem):                          # ② 直接子（壳容器场景）
        if uia.invoke(ch):
            return (True, "press child %s" % _label(uia, ch))
    cur, depth = uia.parent(elem), 1                       # ③ 向上 ≤6 层
    while cur is not None and depth <= 6:
        if uia.invoke(cur):
            return (True, "press up%d %s" % (depth, _label(uia, cur)))
        cur, depth = uia.parent(cur), depth + 1
    r = uia.rect(elem)                                     # ④ 坐标兜底（尺寸门槛）
    if r:
        w, h = r[2] - r[0], r[3] - r[1]
        if w > 8 and h > 4:
            x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            if click_at(x, y):
                return (True, "click@%d,%d" % (x, y))
    return (False, "no-invoke-no-coord %s" % _label(uia, elem))


def focus_input_strategy(uia, ctx, cache):
    """五阶段跳输入框（②③④⑤；① 窗口修复在 do_focus_input 内先行）。
    ctx:   {"hwnd","rect","exe_key"}
    cache: {exe_key: {"fx","fy"}}（命中不修改；由调用方在成功后持久化）
    返回 (ok, detail, rect_frac)；rect_frac = (fx, fy) 或 None。"""
    l, t, r, b = ctx["rect"]
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return (False, "bad-window-rect", None)
    elem, fx, fy, src = None, None, None, None

    # ② 缓存点
    c = cache.get(ctx["exe_key"])
    if isinstance(c, dict) and c.get("fx") is not None and c.get("fy") is not None:
        try:
            cfx, cfy = float(c["fx"]), float(c["fy"])
        except Exception:
            cfx = cfy = -1.0
        if 0.0 <= cfx <= 1.0 and 0.0 <= cfy <= 1.0:
            ex, ey = l + int(w * cfx), t + int(h * cfy)
            e2 = uia.from_point(ex, ey)
            if is_input_like(uia, e2, w, h):
                elem, fx, fy, src = e2, cfx, cfy, "cache"

    # ③ 坐标网格（底部输入区优先）
    if elem is None:
        for gy in GRID_Y:
            for gx in GRID_X:
                x = l + int(w * gx)
                y = t + int(h * gy)
                ymax = b - 10
                if y > ymax:
                    y = ymax
                e2 = uia.from_point(x, y)
                if is_input_like(uia, e2, w, h):
                    elem, fx, fy, src = e2, gx, gy, "grid"
                    break
            if elem is not None:
                break

    # ④ 树遍历（首个 Edit → ComboBox）
    if elem is None and ctx.get("hwnd"):
        root = uia.from_handle(ctx["hwnd"])
        if root is not None:
            e2 = uia.find_type(root, CT_EDIT)
            if e2 is None or uia.ctrl_type(e2) not in (CT_EDIT, CT_COMBOBOX):
                e2 = uia.find_type(root, CT_COMBOBOX)
            if e2 is not None and uia.ctrl_type(e2) in (CT_EDIT, CT_COMBOBOX):
                elem, src = e2, "tree"
                rr = uia.rect(e2)
                if rr and rr[2] > rr[0] and rr[3] > rr[1]:
                    cx = (rr[0] + rr[2]) / 2.0
                    cy = (rr[1] + rr[3]) / 2.0
                    fx = max(0.05, min(0.95, (cx - l) / w))
                    fy = max(0.05, min(0.95, (cy - t) / h))

    if elem is None:
        return (False, "NOEDIT (窗口已修复, 未找到输入框)", None)

    # ⑤ SetFocus + 读回
    before = uia.has_focus(elem)
    if before is not True:
        if not uia.set_focus(elem):
            return (False, "FAIL-set %s" % _label(uia, elem), None)
    after = uia.has_focus(elem)
    if after is True or before is True:
        frac = (fx, fy) if (fx is not None and fy is not None) else None
        return (True, "OK src=%s %s fx=%s fy=%s" % (
            src, _label(uia, elem),
            ("%.2f" % fx) if fx is not None else "-",
            ("%.2f" % fy) if fy is not None else "-"), frac)
    return (False, "FAIL-readback %s" % _label(uia, elem), None)


# ---------------------------------------------------------------- 应用轮询/切换
def apps_from_windows(windows, include_minimized=False):
    """z 序窗口列表 -> 应用条目（每 exe 取 z 最高窗口为代表, 保序去重）。"""
    out, seen = [], set()
    for w in windows:
        if not include_minimized and w.get("minimized"):
            continue
        k = w.get("exe_key") or ("pid%d" % w.get("pid", 0))
        if k in seen:
            continue
        seen.add(k)
        # v1.5: "key" 之外同步补写 "exe_key"（原 _icon_photo_for 只读 exe_key）
        out.append({"key": k, "exe_key": k, "exe": w.get("exe", ""),
                    "title": w.get("title", ""),
                    "hwnd": w.get("hwnd"), "pid": w.get("pid", 0),
                    "uwp": bool(w.get("uwp")),      # v1.7: UWP 标记透传（图标通路分流）
                    "minimized": bool(w.get("minimized"))})
    return out


def cycle_step(state, front_key, ordered_keys, alive_keys, now_ts, renew_window=1800.0):
    """全应用轮询环推进（对齐 app_switch doCycle 语义）。
    state:        dict（cycle_list/cycle_idx/cycle_expect/cycle_ts, 缺失容忍）
    front_key:    当前前台应用 key
    ordered_keys: 需要重建快照时的有序候选（z 序或名称序）
    alive_keys:   仍存活可切的 key 集合（含最小化——激活路径会 restore）
    返回 (target_key | None, new_state, detail)。"""
    st = dict(state or {})
    names = [n for n in (st.get("cycle_list") or []) if n]
    expect = st.get("cycle_expect") or ""
    try:
        last_idx = int(st.get("cycle_idx", -1) or -1)
    except Exception:
        last_idx = -1
    try:
        ts = float(st.get("cycle_ts", 0) or 0)
    except Exception:
        ts = 0.0
    continued = bool(names) and front_key == expect and (now_ts - ts) < renew_window
    tag = "续"
    if not continued:
        seen = set()
        names = [n for n in ordered_keys if n and not (n in seen or seen.add(n))]
        tag = "重建"
    if front_key and front_key not in names:
        names.insert(0, front_key)                         # 前台不在快照 -> 补首位, 保环闭合
    if len(names) < 2:
        return (None, st, "%s 不足2个" % tag)
    if continued and 0 <= last_idx < len(names):
        base = last_idx
    else:
        base = names.index(front_key) if front_key in names else -1
    n = len(names)
    target, target_idx = None, -1
    for step in range(1, n + 1):
        cand = ((base + step) % n + n) % n
        cid = names[cand]
        if cid == front_key:
            continue                                       # 跳过自己
        if cid in alive_keys:
            target, target_idx = cid, cand
            break
    if target is None:
        return (None, st, "%s 环中无可切目标" % tag)
    st["cycle_list"] = names
    st["cycle_idx"] = target_idx
    st["cycle_expect"] = target
    st["cycle_ts"] = now_ts
    return (target, st, "%s idx=%d/%d" % (tag, target_idx, n - 1))


def toggle_target(state, front_key):
    """最近两应用回跳目标（对齐 app_switch doToggle）。返回 (target|None, reason)。"""
    st = state or {}
    prev = st.get("prev") or ""
    cur = st.get("cur") or ""
    if not cur:
        return (None, "无切换记录")
    target = prev if front_key == cur else cur
    if not target or target == front_key:
        return (None, "目标与当前相同")
    return (target, "toggle")


def next_target(ordered_keys, front_key):
    """名称序循环下一个（对齐 doNext；front 不在列表则取第 0 个）。"""
    if not ordered_keys or len(ordered_keys) < 2:
        return None
    try:
        i = ordered_keys.index(front_key)
    except ValueError:
        i = -1
    return ordered_keys[(i + 1) % len(ordered_keys)]


def match_query(query, entries):
    """应用查询匹配（对齐 app_switch findApp 链）:
    exe 精确（含去/带 .exe）-> 标题精确 -> exe 包含 -> 标题包含。"""
    q = (query or "").strip().lower()
    if not q:
        return None
    qn = q[:-4] if q.endswith(".exe") else q

    def _has(e, k):
        return k in e.get("key", "") or k in (e.get("exe") or "").lower()

    for e in entries:                                      # ① exe 精确
        ek = e.get("key", "")
        if ek == q or ek == qn or ek == qn + ".exe":
            return e
    for e in entries:                                      # ② 标题精确
        if (e.get("title") or "").strip().lower() == q:
            return e
    for e in entries:                                      # ③ exe 包含
        if qn and _has(e, qn):
            return e
    for e in entries:                                      # ④ 标题包含
        if q in (e.get("title") or "").lower():
            return e
    return None


# ---------------------------------------------------------------- 启动未运行应用
_LNK_CACHE = {"ts": 0.0, "list": []}


def find_start_menu_lnk(query, max_age=300.0):
    """在开始菜单（用户+全局）中找名称包含 query 的快捷方式（浅层优先）。"""
    if not IS_WIN:
        return None
    now = time.time()
    if now - _LNK_CACHE["ts"] > max_age or not _LNK_CACHE["list"]:
        lst = []
        for root in (os.path.join(os.environ.get("APPDATA", ""),
                                  r"Microsoft\Windows\Start Menu\Programs"),
                     os.path.join(os.environ.get("ProgramData", ""),
                                  r"Microsoft\Windows\Start Menu\Programs")):
            if not root or not os.path.isdir(root):
                continue
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if fn.lower().endswith(".lnk"):
                        lst.append(os.path.join(dirpath, fn))
        lst.sort(key=lambda p: p.count(os.sep))
        _LNK_CACHE["list"] = lst
        _LNK_CACHE["ts"] = now
    q = (query or "").strip().lower()
    if not q:
        return None
    for p in _LNK_CACHE["list"]:
        stem = os.path.splitext(os.path.basename(p))[0].lower()
        if q in stem:
            return p
    return None


def launch_app(query):
    """未运行应用的启动尝试: App Paths 注册表 → 开始菜单 lnk → PATH → cmd start。
    返回 (ok, detail)。"""
    if not IS_WIN:
        return (False, "not-windows")
    q = (query or "").strip()
    if not q:
        return (False, "empty-query")
    # ① App Paths 注册表
    try:
        import winreg
        for hive, sub in (
                (winreg.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths")):
            for name in (q, q + ".exe"):
                try:
                    with winreg.OpenKey(hive, sub + "\\" + name) as k:
                        exe, _ = winreg.QueryValueEx(k, "")
                        if exe and os.path.exists(exe):
                            subprocess.Popen([exe], creationflags=_NO_WINDOW)
                            return (True, "launch app-paths %s" % exe)
                except OSError:
                    continue
    except Exception:
        pass
    # ② 开始菜单快捷方式
    lnk = find_start_menu_lnk(q)
    if lnk:
        try:
            os.startfile(lnk)
            return (True, "launch lnk %s" % os.path.basename(lnk))
        except Exception:
            pass
    # ③ PATH 中的可执行
    try:
        r = subprocess.run(["where", q], capture_output=True, text=True, timeout=5,
                           creationflags=_NO_WINDOW)
        lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
        if r.returncode == 0 and lines:
            subprocess.Popen([lines[0]], creationflags=_NO_WINDOW)
            return (True, "launch where %s" % lines[0])
    except Exception:
        pass
    # ④ cmd start（壳关联: 协议 URI / 商店应用别名）
    try:
        subprocess.Popen(["cmd", "/c", "start", "", q], creationflags=_NO_WINDOW)
        return (True, "launch cmd-start %s" % q)
    except Exception as e:
        return (False, "launch failed: %s" % e)


# ---------------------------------------------------------------- 状态文件
def _state_path():
    return os.path.join(STATE_DIR, "app_switch_win.json")


def _load_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _state_path())
    except Exception as e:
        _logv("state save error: %s" % e)


def _load_focus_cache():
    try:
        with open(os.path.join(STATE_DIR, "focus_cache.json"), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_focus_cache(c):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = os.path.join(STATE_DIR, "focus_cache.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(STATE_DIR, "focus_cache.json"))
    except Exception:
        pass


# ================================================================
# C. 动作执行层（连接平台层与策略层；在调用方 worker 线程内执行）
# ================================================================
def _sane_focus(uia, elem):
    """焦点元素合理化: 拒绝「覆盖整个虚拟屏的 Window/Pane」（= 焦点丢失时的桌面壳层）。"""
    if elem is None:
        return None
    t = uia.ctrl_type(elem)
    if t not in (CT_WINDOW, CT_PANE):
        return elem
    r = uia.rect(elem)
    if not r:
        return elem
    if not IS_WIN:
        return elem
    try:
        vw = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if vw > 0 and vh > 0 and (r[2] - r[0]) >= vw and (r[3] - r[1]) >= vh:
            return None
    except Exception:
        pass
    return elem


def do_click():
    uia = get_uia()
    if uia is None:
        return "CLICK unavailable: uia=%s %s" % (uia_probe(), _uia_error)
    elem = _sane_focus(uia, uia.focused())
    if elem is None:
        hwnd = get_focus_hwnd()
        if hwnd:
            elem = _sane_focus(uia, uia.from_handle(hwnd))
    ok, detail = click_strategy(uia, elem, mouse_click)
    return ("CLICK " if ok else "CLICK FAIL ") + detail


def do_focus_input():
    uia = get_uia()
    if uia is None:
        return "FOCUS_INPUT unavailable: uia=%s %s" % (uia_probe(), _uia_error)
    fix = fix_foreground_window()
    ctx = foreground_ctx()
    if ctx is None:
        return "FOCUS_INPUT FAIL no-foreground (winfix=%s)" % fix
    cache = _load_focus_cache()
    ok, detail, frac = focus_input_strategy(uia, ctx, cache)
    if ok and frac and frac[0] is not None and frac[1] is not None:
        cache[ctx["exe_key"]] = {"fx": round(float(frac[0]), 3),
                                 "fy": round(float(frac[1]), 3)}
        _save_focus_cache(cache)
    return "FOCUS_INPUT %s [winfix=%s]" % (detail, fix)


def _activate_key(key, apps):
    """激活指定 key 应用的代表窗口（优先非最小化; 全最小化则 restore 之）。"""
    cands = [a for a in apps if a["key"] == key and a.get("hwnd")]
    if not cands:
        return False
    target = next((a for a in cands if not a["minimized"]), cands[0])
    return force_foreground(target["hwnd"])


def _apps_now():
    wins = enum_windows()
    return wins, apps_from_windows(wins, include_minimized=True)


def do_app_cycle():
    if not IS_WIN:
        return "not-windows"
    wins = enum_windows()
    all_apps = apps_from_windows(wins, include_minimized=True)
    alive = {a["key"] for a in all_apps}
    front_key = exe_key_of_hwnd(_user32.GetForegroundWindow())
    z_apps = apps_from_windows(wins, include_minimized=False)
    ordered = [a["key"] for a in z_apps]
    src = "z序"
    if len(ordered) < 2:
        ordered = sorted(alive)
        src = "名称序"
    st = _load_state()
    target, st2, detail = cycle_step(st, front_key, ordered, alive, time.time())
    if target is None:
        return "cycle: %s" % detail
    ok = _activate_key(target, all_apps)
    if ok:
        _save_state(st2)
        return "cycle[%s] -> %s ok (%s)" % (src, target, detail)
    return "cycle FAIL activate %s (%s)" % (target, detail)


def do_app_toggle():
    if not IS_WIN:
        return "not-windows"
    _wins, all_apps = _apps_now()
    front_key = exe_key_of_hwnd(_user32.GetForegroundWindow())
    st = _load_state()
    target, why = toggle_target(st, front_key)
    if target is None:
        return "toggle: %s" % why
    if target not in {a["key"] for a in all_apps}:
        return "toggle: target not running (%s)" % target
    ok = _activate_key(target, all_apps)
    if ok:
        _save_state(dict(st, prev=front_key, cur=target))
    return "toggle %s -> %s ok=%s" % (front_key, target, ok)


def do_app_next():
    if not IS_WIN:
        return "not-windows"
    _wins, all_apps = _apps_now()
    front_key = exe_key_of_hwnd(_user32.GetForegroundWindow())
    ordered = sorted({a["key"] for a in all_apps})
    t = next_target(ordered, front_key)
    if not t:
        return "next: 不足2个应用"
    ok = _activate_key(t, all_apps)
    return "next -> %s ok=%s" % (t, ok)


def do_app_activate(query):
    if not IS_WIN:
        return "not-windows"
    _wins, all_apps = _apps_now()
    front_key = exe_key_of_hwnd(_user32.GetForegroundWindow())
    m = match_query(query, all_apps)
    if m:
        ok = _activate_key(m["key"], all_apps)
        if ok and front_key != m["key"]:
            _save_state(dict(_load_state(), prev=front_key, cur=m["key"]))
        return "activate %s '%s' ok=%s" % (m["exe"], (m["title"] or "")[:30], ok)
    ok, detail = launch_app(query)
    return "not-running -> %s" % detail


def host_child_hwnd(hwnd):
    '''v1.10 Windows: ApplicationFrameHost 窗口 → 真实应用子窗口（失败 0）。
    与 host_child_pid 同构（可见子窗口优先, 兜底首个不同 PID 候选）——
    UWP 关闭须对真身子窗口发 WM_CLOSE（宿主外壳窗口不发）。'''
    if not IS_WIN or not hwnd:
        return 0
    try:
        hp = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(hp))
        found = {"hwnd": 0, "host": int(hp.value)}

        def _cb(ch, lparam):
            try:
                p = wt.DWORD(0)
                _user32.GetWindowThreadProcessId(ch, ctypes.byref(p))
                if p.value and p.value != found["host"]:
                    if not found["hwnd"]:
                        found["hwnd"] = ch          # 兜底候选（首个不同 PID）
                    if _user32.IsWindowVisible(ch):
                        found["hwnd"] = ch          # 更优候选（可见）→ 采用
                        return False
            except Exception:
                pass
            return True

        _user32.EnumChildWindows(hwnd, WNDENUMPROC(_cb), 0)
        return found["hwnd"]
    except Exception:
        return 0


def close_poll(is_alive, is_front, timeout=2.0, interval=0.1,
               _sleep=time.sleep, _clock=time.time):
    '''v1.10 纯逻辑（注入可测）: 轮询等待关闭生效。
    ok = 窗口已销毁（not is_alive）或前台已切换（not is_front）——
    任一成立即成功; 超时返回 (False, waited)（应用可能弹出保存确认）。'''
    t0 = _clock()
    while True:
        if not is_alive() or not is_front():
            return True, _clock() - t0
        if _clock() - t0 >= timeout:
            return False, _clock() - t0
        _sleep(interval)


def do_app_close():
    '''v1.10: 关闭当前前台应用 —— 优雅退出（WM_CLOSE, 非 TerminateProcess）,
    对齐 Mac app_switch v1.2 close / key_bridge v1.12（生产绑定 = #116 长按）。
    语义: 只关前台窗口（多窗口应用连续长按可依次关闭）; UWP 找真身子窗口;
    系统 shell 窗口（桌面/任务栏）拒绝; 未保存内容由应用自身弹保存确认。'''
    if not IS_WIN:
        return "not-windows"
    fg = _user32.GetForegroundWindow()
    if not fg:
        return "close: 无前台窗口"
    cbuf = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(fg, cbuf, 64)
    if cbuf.value in SHELL_CLASSES:
        return "close: 拒绝关闭系统窗口（%s）" % cbuf.value
    front_key = exe_key_of_hwnd(fg)
    n = _user32.GetWindowTextLengthW(fg)
    tbuf = ctypes.create_unicode_buffer(n + 2)
    if n:
        _user32.GetWindowTextW(fg, tbuf, n + 2)
    title = tbuf.value or front_key
    target = fg
    if is_host_process(front_key):                # UWP → 真身子窗口
        ch = host_child_hwnd(fg)
        if ch:
            target = ch
    dw = ULONG_PTR(0)
    try:
        _user32.SendMessageTimeoutW(target, WM_CLOSE, 0, 0,
                                    SMTO_ABORTIFHUNG, 1500, ctypes.byref(dw))
    except Exception as e:
        return "close FAIL send: %r" % e
    ok, waited = close_poll(is_alive=lambda: bool(_user32.IsWindow(target)),
                            is_front=lambda: _user32.GetForegroundWindow() == fg)
    if ok:
        return "close[%s] -> %s ok (%.1fs)" % (front_key, title[:30], waited)
    return "close[%s] pending: 窗口仍在（可能弹保存确认/应用无响应）" % front_key


# ================================================================
# PICK 应用选择器 v2（v1.3: 常驻 Tk 线程 + 图标网格 + 高 DPI; v1.4: 尺寸归一 + 纯应用名 + UWP 真身）
# ----------------------------------------------------------------
# 崩溃史（v1.1 → v1.3 根治）：旧实现每次 PICK 新开线程创建/销毁独立 Tk 解释器，
# 解释器对象在非创建线程被 GC 回收时触发 Tcl_AsyncDelete（Tk fatal 弹窗 + abort，
# 触发时机随 GC 不定 ⇒「试几下才炸」）。v2 = 进程内唯一常驻 Tk 线程：只创建一次
# root，每次 PICK 只开关 Toplevel；所有回调异常改写为日志。
# ================================================================
_pick_state = {"open": False}
_pick_ctl = {"q": None,          # 按键投递队列（选择器就绪期间非 None; picker_route 判定）
             "cmd_q": None,      # 控制队列（do_app_pick -> Tk 线程: "open"）
             "thread": None, "root": None, "win": None, "failed": False}
PICKER_KEYS = {"UP", "DOWN", "LEFT", "RIGHT", "ENTER", "ESC", "BACKSPACE", "KP_ENTER"}
PICK_AUTO_CANCEL = 10.0          # 秒（对齐 Mac AppPicker）
PICK_COLS_MAX = 6                # 网格最大列数（对齐 Mac AppPicker）
PICK_MARQUEE_MS = 180            # v1.6: 长名滚动步进间隔（ms/字符）


def picker_route(action, phase):
    """v1.1: 选择器打开时把遥控按键**直接路由**给选择器（不依赖系统键盘焦点——
    本进程为计划任务/后台上下文, 其窗口无法保证获 Windows 前台激活, 注入按键
    会落到别的窗口 → 上下键「无反应」的根因）。
    返回 True = 已消化（调用方不再注入 SendInput）; False = 未消化（照常注入）。
    纯逻辑判定（不触 Tk）, 离线可测。"""
    if not _pick_state["open"]:
        return False
    a = (action or "").upper()
    if a not in PICKER_KEYS:
        return False
    q = _pick_ctl.get("q")
    if q is None:
        return False                 # 竞态窗口（选择器线程尚未就绪）→ 回退注入
    if phase == "down":
        try:
            q.put_nowait(a)
        except Exception:
            return False
    return True                      # up 也吞掉（down 已消化, 防孤立注入）


def pick_move(sel, d, n):
    """v1.3 纯逻辑: 环绕移动（Mac 对齐: ←/↑=-1, →/↓=+1; wrap）。离线可测。
    （v1.7 起选择器导航改走 grid_move; 本函数保留供线性语义/历史兼容。）"""
    if n <= 0:
        return 0
    return (sel + d) % n


def grid_move(sel, action, cols, n):
    """v1.7 纯逻辑: 网格方向导航（电视遥控直觉——两行以上时 ↑/↓ 垂直移动）。
    ←/→: 行内水平（行尾 → 下一行首; 行首 → 上一行尾, 即线性环绕）。
    ↑/↓: 垂直——相邻行同列优先; 该列缺失时取最近列（平手靠左）;
         首行 ↑ / 末行 ↓ 回绕到另一端。
    单行 / 单列时 ↑↓ 退化为线性（与旧行为一致）。离线可测。"""
    if n <= 0:
        return 0
    a = (action or "").upper()
    try:
        c = int(cols)
    except (TypeError, ValueError):
        c = 1
    if c <= 1 or n <= c:                       # 单列 / 单行 → 线性环绕
        if a in ("UP", "LEFT"):
            return (sel - 1) % n
        if a in ("DOWN", "RIGHT"):
            return (sel + 1) % n
        return sel % n
    if a == "LEFT":
        return (sel - 1) % n
    if a == "RIGHT":
        return (sel + 1) % n
    if a not in ("UP", "DOWN"):
        return sel % n
    rows = (n + c - 1) // c
    row, col = divmod(sel % n, c)
    if a == "UP":
        tr = row - 1 if row > 0 else rows - 1
    else:
        tr = row + 1 if row < rows - 1 else 0
    base = tr * c
    cnt = min(c, n - base)                     # 目标行实际格数（末行可能不满）
    if col < cnt:
        return base + col                      # 同列存在
    return base + (cnt - 1)                    # 该列缺失 → 最近列（靠左）


def fit_prefix(name, budget, measure):
    """v1.6 纯逻辑: 静态截断——name 在像素预算内取最长前缀; 溢出时末尾加 "…"。
    measure(s) = 字符串像素宽（注入 tkfont.Font.measure; 离线测试打桩）。"""
    if not name or measure(name) <= budget:
        return name
    ew = measure("…")
    out, w = [], 0
    for ch in name:
        cw = measure(ch)
        if w + cw + ew > budget:
            break
        out.append(ch)
        w += cw
    return ("".join(out) or name[:1]) + "…"


def cycle_slice(name, offset, budget, measure):
    """v1.6 纯逻辑: 跑马灯窗口——(name + 3 空格) 环形序列自 offset 起取满预算像素。
    选中项长名滚动用; 预算内放得下的短名原样返回。离线可测。"""
    if not name or measure(name) <= budget:
        return name
    seq = name + "   "
    n = len(seq)
    out, w, i = [], 0, offset % n
    while len(out) < n:
        ch = seq[i % n]
        cw = measure(ch)
        if w + cw > budget:
            break
        out.append(ch)
        w += cw
        i += 1
    return "".join(out)


def pick_layout(scale, n, cols_max=PICK_COLS_MAX):
    """v1.3 纯逻辑: 依据 DPI 缩放计算网格布局（不同 DPI 观感一致; 离线可测）。
    scale = 系统 DPI/96（1.0~3.0 钳制）。返回 w/h/cell/icon/pad 等像素值。"""
    try:
        s = max(1.0, min(3.0, float(scale or 1.0)))
    except (TypeError, ValueError):
        s = 1.0

    def px(v):
        return int(round(v * s))

    cols = max(1, min(cols_max, int(n)))
    rows = (int(n) + cols - 1) // cols if n > 0 else 1
    cell = (px(96), px(100))
    return {"scale": s, "cols": cols, "rows": rows, "cell": cell,
            "icon": max(16, px(64)), "pad": px(14), "head_h": px(40),
            # v1.5: 每格含 grid padx（2*px(2)）— 旧公式漏算, 末列会被裁 12px
            "w": cols * (cell[0] + 2 * px(2)) + px(14) * 2,
            "h": px(40) + rows * cell[1] + px(14) + px(10)}


# ---------------------------------------------------------------- v1.3: 图标管线
# ---- v1.7: GUID / Shell 图标结构 + COM helpers（模块级——离线可测） ----
# 注意: 全部用固定宽度类型（c_uint32/c_uint16/c_int32）——wt.DWORD 在非 Windows
# 上是 c_ulong（8 字节）会破坏离线测试的结构布局; 固定宽度在 Windows/mac 行为一致。
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]


class PROPVARIANT(ctypes.Structure):
    # x64: vt+pad(8) + union(16, 以两指针模拟——VT_LPWSTR 读 val 即可)
    _fields_ = [("vt", ctypes.c_uint16), ("r1", ctypes.c_uint16),
                ("r2", ctypes.c_uint16), ("r3", ctypes.c_uint16),
                ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_int32), ("cy", ctypes.c_int32)]


def _guid(hexs):
    """v1.7 纯逻辑: GUID 串（可带花括号/大小写）→ GUID 结构（Windows 内存布局）。
    离线可测。"""
    s = (hexs or "").replace("-", "").replace("{", "").replace("}", "")
    if len(s) != 32:
        raise ValueError("bad guid: %r" % (hexs,))
    b = bytes.fromhex(s)
    g = GUID()
    # 各段按打印序（大端）解读为字段值; ctypes 结构自动以小端落内存 —— 与
    # CLSIDFromString/COM GUID 的内存布局一致（前 3 字段小端, Data4 原样）。
    g.Data1 = int.from_bytes(b[0:4], "big")
    g.Data2 = int.from_bytes(b[4:6], "big")
    g.Data3 = int.from_bytes(b[6:8], "big")
    for i in range(8):
        g.Data4[i] = b[8 + i]
    return g


def _vtbl_of(p):
    """v1.7: COM 接口指针 → vtable 函数地址序列（ctypes 手写调用用）。"""
    return ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents


_com_done = [False]


def _com_ensure():
    """v1.7: 本线程 COM 初始化（幂等; 已初始化/异模式均视为可用, 同 get_uia 容忍口径）。"""
    if _com_done[0]:
        return
    _com_done[0] = True
    if not IS_WIN:
        return
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass


def _com_release(p):
    """v1.7: IUnknown::Release（vtable[2]）——静默失败。"""
    try:
        if p is not None and p.value:
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(_vtbl_of(p)[2])(p)
    except Exception:
        pass


ICON_PX = 64                      # 100% DPI 基准图标像素
ICON_BG = (0x8a, 0x8a, 0x8a)      # 合成底色（v1.8: 与选择器窗口 BG #8a8a8a 同值——改色须同步）
ICON_BG_SEL = (0x6c, 0x84, 0xaf)  # v1.9: 选中格合成底色（= SEL #6c84af, 双变体切换——改色须同步）
_ppm_cache = {}                   # (exe_key, px, "bg"|"sel") -> base64 PPM str | None（失败也缓存）
_icon_photos = {}                 # (exe_key, px, "bg"|"sel") -> tk.PhotoImage | False（Tk 线程内建, 永持）


def trim_rgba(rgba, w, h, alpha_thr=8, min_keep=8, margin_frac=0.04):
    """v1.4 纯逻辑: 按 alpha 求内容外接框 → 裁掉空白边缘（图标视觉尺寸归一化的关键）。
    保守策略: 全透明 / 内容过小（<min_keep）/ 无明显留白 → 原样返回。
    margin_frac = 相对内容边长补的透气边距。"""
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        base = y * w * 4 + 3
        for x in range(w):
            if rgba[base + x * 4] > alpha_thr:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    if x1 < 0 or y1 < 0:
        return rgba, w, h
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if bw < min_keep or bh < min_keep:
        return rgba, w, h
    if bw >= w and bh >= h:
        return rgba, w, h
    m = int(round(max(bw, bh) * margin_frac))
    x0 = max(0, x0 - m)
    y0 = max(0, y0 - m)
    x1 = min(w - 1, x1 + m)
    y1 = min(h - 1, y1 + m)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    out = bytearray(bw * bh * 4)
    for y in range(bh):
        s = ((y0 + y) * w + x0) * 4
        d = y * bw * 4
        out[d:d + bw * 4] = rgba[s:s + bw * 4]
    return bytes(out), bw, bh


def square_pad_rgba(rgba, w, h):
    """v1.4 纯逻辑: 非正方形 → 透明补成正方形（居中, 保比例）。
    已是正方形 / 非法尺寸原样返回。（缩放前补齐, 避免拉伸变形）"""
    if w == h or w <= 0 or h <= 0:
        return rgba, w, h
    side = max(w, h)
    out = bytearray(side * side * 4)              # 全透明填充
    ox, oy = (side - w) // 2, (side - h) // 2
    for y in range(h):
        s = y * w * 4
        d = ((oy + y) * side + ox) * 4
        out[d:d + w * 4] = rgba[s:s + w * 4]
    return bytes(out), side, side


def composite_rgba_on_bg(rgba, w, h, bg=ICON_BG):
    """v1.3 纯逻辑: RGBA 按 alpha 合成到 bg 底 → RGB bytes（先合成后缩放, 防黑边）。"""
    out = bytearray(w * h * 3)
    for i in range(w * h):
        s = i * 4
        o = i * 3
        a = rgba[s + 3]
        out[o] = (rgba[s] * a + bg[0] * (255 - a) + 127) // 255
        out[o + 1] = (rgba[s + 1] * a + bg[1] * (255 - a) + 127) // 255
        out[o + 2] = (rgba[s + 2] * a + bg[2] * (255 - a) + 127) // 255
    return bytes(out)


def scale_rgb(src, sw, sh, dw, dh):
    """v1.3 纯逻辑: RGB 双线性缩放（图标 32→64 / 32→96 等; 离线可测）。
    恒等尺寸直接返回。"""
    if (sw, sh) == (dw, dh):
        return bytes(src)
    out = bytearray(dw * dh * 3)
    for y in range(dh):
        fy = (y + 0.5) * sh / dh - 0.5
        fy = 0.0 if fy < 0 else (sh - 1.0 if fy > sh - 1 else fy)
        y0 = int(fy)
        y1 = y0 + 1 if y0 + 1 < sh else y0
        wy = fy - y0
        r0 = y0 * sw * 3
        r1 = y1 * sw * 3
        for x in range(dw):
            fx = (x + 0.5) * sw / dw - 0.5
            fx = 0.0 if fx < 0 else (sw - 1.0 if fx > sw - 1 else fx)
            x0 = int(fx)
            x1 = x0 + 1 if x0 + 1 < sw else x0
            wx = fx - x0
            i00 = r0 + x0 * 3
            i10 = r0 + x1 * 3
            i01 = r1 + x0 * 3
            i11 = r1 + x1 * 3
            o = (y * dw + x) * 3
            out[o] = int(src[i00] * (1 - wx) * (1 - wy) + src[i10] * wx * (1 - wy)
                         + src[i01] * (1 - wx) * wy + src[i11] * wx * wy + 0.5)
            out[o + 1] = int(src[i00 + 1] * (1 - wx) * (1 - wy) + src[i10 + 1] * wx * (1 - wy)
                             + src[i01 + 1] * (1 - wx) * wy + src[i11 + 1] * wx * wy + 0.5)
            out[o + 2] = int(src[i00 + 2] * (1 - wx) * (1 - wy) + src[i10 + 2] * wx * (1 - wy)
                             + src[i01 + 2] * (1 - wx) * wy + src[i11 + 2] * wx * wy + 0.5)
    return bytes(out)


# ---------------------------------------------------------------- v1.5: 视觉归一（光学）
OPTICAL_REF = 0.84        # 内容 √面积 / 画布 px（方形内容边长 ≈ 84% 画布; 圆/长条按面积补偿）
OPTICAL_F_MAX = 2.0       # 放大上限（防小内容放大过糊）
OPTICAL_F_MIN = 0.15      # 缩小下限（极端场景保护）
OPTICAL_MAX_FILL = 0.96   # 内容最大边 ≤ 96% 画布（硬上限, 防溢出）


def scale_rgba(src, sw, sh, dw, dh):
    """v1.5 纯逻辑: RGBA 预乘双线性缩放（alpha 边缘不混入脏色; 恒等直拷）。"""
    if (sw, sh) == (dw, dh):
        return bytes(src)
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        fy = (y + 0.5) * sh / dh - 0.5
        fy = 0.0 if fy < 0 else (sh - 1.0 if fy > sh - 1 else fy)
        y0 = int(fy)
        y1 = y0 + 1 if y0 + 1 < sh else y0
        wy = fy - y0
        r0 = y0 * sw * 4
        r1 = y1 * sw * 4
        for x in range(dw):
            fx = (x + 0.5) * sw / dw - 0.5
            fx = 0.0 if fx < 0 else (sw - 1.0 if fx > sw - 1 else fx)
            x0 = int(fx)
            x1 = x0 + 1 if x0 + 1 < sw else x0
            wx = fx - x0
            i00 = r0 + x0 * 4
            i10 = r0 + x1 * 4
            i01 = r1 + x0 * 4
            i11 = r1 + x1 * 4
            w00 = (1 - wx) * (1 - wy)
            w10 = wx * (1 - wy)
            w01 = (1 - wx) * wy
            w11 = wx * wy
            a00 = src[i00 + 3]
            a10 = src[i10 + 3]
            a01 = src[i01 + 3]
            a11 = src[i11 + 3]
            asum = (a00 * w00 + a10 * w10 + a01 * w01 + a11 * w11) / 255.0
            o = (y * dw + x) * 4
            if asum <= 0.002:
                continue                      # 全透明 → 输出保持 0,0,0,0
            out[o] = int((src[i00] * a00 * w00 + src[i10] * a10 * w10 +
                          src[i01] * a01 * w01 + src[i11] * a11 * w11) / (255.0 * asum) + 0.5)
            out[o + 1] = int((src[i00 + 1] * a00 * w00 + src[i10 + 1] * a10 * w10 +
                              src[i01 + 1] * a01 * w01 + src[i11 + 1] * a11 * w11) / (255.0 * asum) + 0.5)
            out[o + 2] = int((src[i00 + 2] * a00 * w00 + src[i10 + 2] * a10 * w10 +
                              src[i01 + 2] * a01 * w01 + src[i11 + 2] * a11 * w11) / (255.0 * asum) + 0.5)
            out[o + 3] = int(asum * 255.0 + 0.5)
    return bytes(out)


def optical_fit_rgba(rgba, w, h, px=ICON_PX, alpha_thr=8):
    """v1.5 纯逻辑: 视觉尺寸归一（光学）—— 内容有效面积 √ 统一到 OPTICAL_REF*px,
    直接居中置入 px×px 透明画布（输出即最终 PhotoImage 尺寸）。
    输入一般来自 trim→square_pad（内容贴紧）; 任意 w×h 兼容; 全透明按几何尺寸。"""
    if w <= 0 or h <= 0 or px <= 0:
        return rgba, w, h
    side = max(w, h)
    filled = 0
    for o in range(3, w * h * 4, 4):
        if rgba[o] > alpha_thr:
            filled += 1
    s = math.sqrt(filled) if filled > 0 else float(side)
    f = (OPTICAL_REF * px) / s if s > 0 else 1.0
    if f > OPTICAL_F_MAX:
        f = OPTICAL_F_MAX
    if f < OPTICAL_F_MIN:
        f = OPTICAL_F_MIN
    lim = (OPTICAL_MAX_FILL * px) / float(side)
    if f > lim:
        f = lim
    w2 = max(1, min(px, int(round(w * f))))
    h2 = max(1, min(px, int(round(h * f))))
    scaled = scale_rgba(rgba, w, h, w2, h2)
    out = bytearray(px * px * 4)
    ox = (px - w2) // 2
    oy = (px - h2) // 2
    row = w2 * 4
    for y in range(h2):
        s0 = y * row
        d0 = ((oy + y) * px + ox) * 4
        out[d0:d0 + row] = scaled[s0:s0 + row]
    return bytes(out), px, px


def ppm_encode(rgb, w, h):
    """v1.3 纯逻辑: RGB bytes → PPM(P6) bytes（Tk PhotoImage 直接可读）。"""
    return b"P6\n%d %d\n255\n" % (w, h) + rgb


# ---------------------------------------------------------------- v1.4: 应用名 / UWP
_name_cache = {}                  # exe_key -> 显示名（会话内缓存）


def choose_display_name(desc, exe):
    """v1.4 纯逻辑: 选择器显示名 —— FileDescription 优先, 退路 exe 主名（去 .exe）。"""
    d = (desc or "").strip()
    if d:
        return d
    e = (exe or "").strip()
    if e.lower().endswith(".exe"):
        e = e[:-4]
    return e or "?"


def _file_description(path):
    """v1.4 Windows: exe → 版本资源 FileDescription（中文块优先; 失败 ''）。"""
    if not IS_WIN or not path or _version is None:
        return ""
    try:
        handle = wt.DWORD(0)
        size = _version.GetFileVersionInfoSizeW(str(path), ctypes.byref(handle))
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        pb = ctypes.cast(buf, ctypes.c_void_p)
        if not _version.GetFileVersionInfoW(str(path), 0, size, pb):
            return ""
        ptr = ctypes.c_void_p()
        ln = wt.UINT(0)
        if not _version.VerQueryValueW(pb, "\\VarFileInfo\\Translation",
                                       ctypes.byref(ptr), ctypes.byref(ln)):
            return ""
        pairs = []
        n = int(ln.value) // 4
        arr = ctypes.cast(ptr, ctypes.POINTER(wt.WORD))
        for i in range(min(n, 8)):
            pairs.append("%04x%04x" % (arr[i * 2], arr[i * 2 + 1]))
        pairs.sort(key=lambda t: 0 if t.startswith("0804") else 1)   # 中文块优先
        for tag in pairs:
            sub = "\\StringFileInfo\\%s\\FileDescription" % tag
            p2 = ctypes.c_void_p()
            l2 = wt.UINT(0)
            if _version.VerQueryValueW(pb, sub, ctypes.byref(p2), ctypes.byref(l2)) and p2.value:
                s = ctypes.wstring_at(p2.value).strip()
                if s:
                    return s
        return ""
    except Exception:
        return ""


def app_display_name(app):
    """v1.4: 应用条目 → 显示名（FileDescription 优先; 按 exe_key 缓存）。"""
    key = (app.get("exe_key") or app.get("key") or "")   # v1.5: 兼容产出键 "key"
    if key and key in _name_cache:
        return _name_cache[key]
    desc = _file_description((app.get("path") or "").strip())
    name = choose_display_name(desc, app.get("exe") or "")
    if key:
        _name_cache[key] = name
    return name


# ---- v1.7: UWP 真实图标（Shell AppsFolder 通路; 计算器等系统应用「图标不对」修复） ----
UWP_REQ_PX = 256                  # Shell 图标请求边长（后处理管线归一到目标 px）
SIIGBF_ICONONLY = 0x4             # GetImage: 只要图标（不要缩略图）
SIIGBF_SCALEUP = 0x100            # GetImage: 允许放大到请求尺寸


def is_uwp_path(path):
    """v1.7 纯逻辑: exe 完整路径判定 = 包应用（UWP/MSIX）。
    WindowsApps 下（多数 UWP/Store 应用真身）或沉浸式控制面板（设置）。
    用作 Shell 图标通路触发条件的**第二判据**——个别不走 ApplicationFrameHost
    托管的包应用窗口也能拿到系统显示图标（失败仍回退 exe 内嵌）。离线可测。"""
    p = (path or "").lower()
    if not p:
        return False
    return ("\\windowsapps\\" in p or "/windowsapps/" in p
            or "\\immersivecontrolpanel\\" in p or "/immersivecontrolpanel/" in p)


def uwp_aumid_for(hwnd, pid=0):
    """v1.7 Windows: 窗口/进程的 AppUserModelID（UWP 图标解析入口）。
    ① SHGetPropertyStoreForWindow(hwnd) → PKEY_AppUserModel_ID（窗口属性; 最直接）;
    ② 回退 GetApplicationUserModelId(pid)（内核按进程查询）。非 UWP / 失败 → ""。"""
    if not IS_WIN:
        return ""
    _com_ensure()
    a = _aumid_from_window(hwnd)
    if a:
        return a
    return _aumid_from_pid(pid)


def _aumid_from_window(hwnd):
    if not hwnd:
        return ""
    pps = ctypes.c_void_p()
    try:
        iid = _guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")   # IID_IPropertyStore
        hr = _shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(pps))
        if hr != 0 or not pps.value:
            return ""
        # IPropertyStore::GetValue = vtable[5]
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                ctypes.POINTER(PROPERTYKEY),
                                ctypes.POINTER(PROPVARIANT))(_vtbl_of(pps)[5])
        pkey = PROPERTYKEY()
        pkey.fmtid = _guid("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3")   # PKEY_AppUserModel_ID
        pkey.pid = 5
        pv = PROPVARIANT()
        if fn(pps, ctypes.byref(pkey), ctypes.byref(pv)) != 0:
            return ""
        if pv.vt == 31 and pv.val:                      # VT_LPWSTR
            return ctypes.wstring_at(pv.val) or ""
        return ""
    except Exception as e:
        _logv("aumid window fail: %s" % e)
        return ""
    finally:
        _com_release(pps)


def _aumid_from_pid(pid):
    if not pid:
        return ""
    h = None
    try:
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return ""
        ln = ctypes.c_uint32(0)
        r = _kernel32.GetApplicationUserModelId(h, ctypes.byref(ln), None)
        if r == 122 and ln.value:                       # ERROR_INSUFFICIENT_BUFFER
            buf = ctypes.create_unicode_buffer(int(ln.value))
            r = _kernel32.GetApplicationUserModelId(h, ctypes.byref(ln), buf)
            if r == 0:
                return buf.value or ""
        return ""
    except Exception as e:
        _logv("aumid pid fail: %s" % e)
        return ""
    finally:
        if h:
            try:
                _kernel32.CloseHandle(h)
            except Exception:
                pass


def _hbitmap_to_rgba(hbmp):
    """v1.7 Windows: HBITMAP(32bpp BGRA) → (RGBA, w, h)——Shell 图标位图。
    alpha 通道恒 0（资源无 alpha）时按不透明处理。失败 (None, 0, 0)。"""
    if not IS_WIN or not hbmp:
        return None, 0, 0
    try:
        bm = BITMAP()
        if not _gdi32.GetObjectW(hbmp, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
            return None, 0, 0
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if h < 0:
            h = -h
        if not (0 < w <= 1024 and 0 < h <= 1024):
            return None, 0, 0
        hdc = _user32.GetDC(0)
        if not hdc:
            return None, 0, 0
        try:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h        # top-down DIB
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            col = ctypes.create_string_buffer(w * h * 4)
            if not _gdi32.GetDIBits(hdc, hbmp, 0, h, col, ctypes.byref(bmi), 0):
                return None, 0, 0
        finally:
            try:
                _user32.ReleaseDC(0, hdc)
            except Exception:
                pass
        raw = col.raw
        opaque = not any(raw[3::4])
        out = bytearray(w * h * 4)
        for o in range(0, w * h * 4, 4):    # BGRA -> RGBA（非预乘）
            out[o] = raw[o + 2]
            out[o + 1] = raw[o + 1]
            out[o + 2] = raw[o]
            out[o + 3] = 255 if opaque else raw[o + 3]
        return bytes(out), w, h
    except Exception as e:
        _logv("hbitmap rgba fail: %s" % e)
        return None, 0, 0


def _shell_icon_rgba(aumid, req=UWP_REQ_PX):
    """v1.7 Windows: shell:AppsFolder\\<AUMID> → IShellItemImageFactory.GetImage →
    图标 RGBA。失败 (None, 0, 0)（调用方回退 exe 内嵌资源通路）。"""
    if not IS_WIN or not aumid:
        return None, 0, 0
    _com_ensure()
    p = ctypes.c_void_p()
    hb = ctypes.c_void_p()
    try:
        # [patch 20261012-username] IID_IShellItemImageFactory 原写成 bcc38b79-…
        # （正确为 bcc18b79-…, '3'↔'1' 一个字符之差）→ SHCreateItemFromParsingName
        # 恒返回 E_NOINTERFACE(0x80004002) → UWP 图标通路 100% 失败静默回退 exe 内嵌
        # → 计算器/设置等系统应用「图标不对」的修复根本没生效。已按官方 IID 更正。
        iid = _guid("bcc18b79-ba16-442f-80c4-8a59c30c463b")   # IID_IShellItemImageFactory
        hr = _shell32.SHCreateItemFromParsingName(
            "shell:AppsFolder\\" + str(aumid), None, ctypes.byref(iid), ctypes.byref(p))
        if hr != 0 or not p.value:
            _logv("shell item hr=0x%08x aumid=%s" % (hr & 0xFFFFFFFF, aumid))
            return None, 0, 0
        # IShellItemImageFactory::GetImage = vtable[3]
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, SIZE, ctypes.c_uint,
                                ctypes.POINTER(ctypes.c_void_p))(_vtbl_of(p)[3])
        sz = SIZE(int(req), int(req))
        hr = fn(p, sz, SIIGBF_ICONONLY | SIIGBF_SCALEUP, ctypes.byref(hb))
        if hr != 0 or not hb.value:
            _logv("shell getimage hr=0x%08x aumid=%s" % (hr & 0xFFFFFFFF, aumid))
            return None, 0, 0
        return _hbitmap_to_rgba(hb)
    except Exception as e:
        _logv("shell icon fail: %s" % e)
        return None, 0, 0
    finally:
        try:
            if hb.value:
                _gdi32.DeleteObject(hb)
        except Exception:
            pass
        _com_release(p)


def _extract_icon_hicon(path, size):
    """Windows: 从文件提取 size×size 图标 HICON（私有 API 优先, SHGetFileInfo 兜底）。
    失败 None。返回的 HICON 需调用方 DestroyIcon。"""
    try:
        h = ctypes.c_void_p()
        n = _user32.PrivateExtractIconsW(str(path), 0, size, size, ctypes.byref(h), None, 1, 0)
        if n and h.value:
            return h.value
    except Exception:
        pass
    try:
        sfi = SHFILEINFOW()
        _shell32.SHGetFileInfoW(str(path), 0, ctypes.byref(sfi), ctypes.sizeof(sfi), 0x100)
        if sfi.hIcon:
            return sfi.hIcon
    except Exception:
        pass
    return None


def _hicon_to_rgba(hicon):
    """Windows: HICON → (RGBA bytes, w, h)。优先颜色位图 32bpp（含 alpha）;
    无 alpha（老式）时用 AND 掩码合成透明度。失败 (None, 0, 0)。"""
    ii = ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(ii)):
        return None, 0, 0
    hc, hm = ii.hbmColor, ii.hbmMask
    hdc = _user32.GetDC(0)
    try:
        bm = BITMAP()
        src_bm = hc or hm
        if not src_bm or not _gdi32.GetObjectW(src_bm, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
            return None, 0, 0
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if hc is None and h == 2 * w:      # 老式单色图标: 掩码 2h 高（上 AND 下 XOR）
            h = w
        if not (0 < w <= 512 and 0 < h <= 512):
            return None, 0, 0
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h        # top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0    # BI_RGB
        col = ctypes.create_string_buffer(w * h * 4)
        if hc:
            if not _gdi32.GetDIBits(hdc, hc, 0, h, col, ctypes.byref(bmi), 0):
                return None, 0, 0
        raw = col.raw
        if hc and any(raw[3::4]):          # 颜色位图带 alpha
            out = bytearray(w * h * 4)
            for o in range(0, w * h * 4, 4):   # BGRA -> RGBA
                out[o] = raw[o + 2]
                out[o + 1] = raw[o + 1]
                out[o + 2] = raw[o]
                out[o + 3] = raw[o + 3]
            return bytes(out), w, h
        if not hm:
            return None, 0, 0
        msk = ctypes.create_string_buffer(w * h * 4)
        if not _gdi32.GetDIBits(hdc, hm, 0, h, msk, ctypes.byref(bmi), 0):
            return None, 0, 0
        m = msk.raw
        out = bytearray(w * h * 4)
        for o in range(0, w * h * 4, 4):
            out[o] = raw[o + 2]
            out[o + 1] = raw[o + 1]
            out[o + 2] = raw[o]
            out[o + 3] = 255 - m[o]        # AND 掩码: 白(0xFF)=透明
        return bytes(out), w, h
    finally:
        try:
            _user32.ReleaseDC(0, hdc)
        except Exception:
            pass
        for hbm in (hc, hm):
            if hbm:
                try:
                    _gdi32.DeleteObject(hbm)
                except Exception:
                    pass


def _finish_icon_ppm(rgba, w, h, px, bg=ICON_BG):
    """v1.7 抽公用（exe 内嵌 / Shell 两通路共用）: 图标 RGBA → 统一后处理
    （裁白 → 补方 → 光学归一 → 合成 → 缩放 → PPM base64）。
    v1.9: bg 参数化 —— 非选中=ICON_BG（窗口灰底）/ 选中=ICON_BG_SEL（SEL 蓝底）。"""
    rgba, w, h = trim_rgba(rgba, w, h)          # v1.4: 裁空白（视觉尺寸归一化）
    rgba, w, h = square_pad_rgba(rgba, w, h)    # v1.4: 透明补正方形（保比例居中）
    rgba, w, h = optical_fit_rgba(rgba, w, h, int(px))  # v1.5: 光学归一（√面积 → px 画布）
    rgb = composite_rgba_on_bg(rgba, w, h, bg)
    rgb = scale_rgb(rgb, w, h, int(px), int(px))
    return base64.b64encode(ppm_encode(rgb, int(px), int(px))).decode("ascii")


def _uwp_icon_ppm(app, px, bg=ICON_BG):
    """v1.7: UWP（系统自带）应用图标 —— Shell AppsFolder 通路。
    真身 exe（WindowsApps 下）的内嵌资源 ≠ 系统显示图标（显示图标由 shell 从
    清单资源解析; 计算器「图标不对」根因）→ 经 AUMID 走 shell:AppsFolder,
    失败返回 None（调用方回退 exe 内嵌资源）。"""
    aumid = uwp_aumid_for(app.get("hwnd"), app.get("pid") or 0)
    if not aumid:
        return None
    rgba, w, h = _shell_icon_rgba(aumid)
    if not rgba:
        return None
    return _finish_icon_ppm(rgba, w, h, px, bg)


def _make_ppm_b64(app, px=ICON_PX, bg=ICON_BG):
    """Windows: app → 合成好的 PPM base64（供 Tk PhotoImage; px=目标像素, 按 DPI）。
    任一环节失败返回 None（调用方退化为占位显示）。"""
    if not IS_WIN:
        return None
    path = (app.get("path") or "").strip()
    if not path:
        return None
    if app.get("uwp") or is_uwp_path(path):   # v1.7: UWP/包应用优先 shell 显示图标（失败回退 exe 内嵌）
        try:
            b64 = _uwp_icon_ppm(app, int(px), bg)
            if b64:
                return b64
        except Exception as e:
            _logv("uwp icon fail %s: %s" % (path, e))
    hicon = _extract_icon_hicon(path, int(px))
    if not hicon:
        return None
    try:
        rgba, w, h = _hicon_to_rgba(hicon)
    except Exception as e:
        _logv("icon dib fail %s: %s" % (path, e))
        return None
    finally:
        try:
            _user32.DestroyIcon(hicon)
        except Exception:
            pass
    if not rgba:
        return None
    try:
        return _finish_icon_ppm(rgba, w, h, int(px), bg)
    except Exception as e:
        _logv("icon encode fail %s: %s" % (path, e))
        return None


def _icon_photo_for(app, tk_mod, px=ICON_PX, sel=False):
    """Tk 线程内调用: (exe_key, px, bg) → PhotoImage | None（负结果同样缓存）。
    v1.9: sel=True 取「选中格」变体（合成底 ICON_BG_SEL; 否则 ICON_BG）。
    PhotoImage 永久持有（防跨线程 GC + 复开复用）。"""
    k = (app.get("exe_key") or app.get("key") or "", int(px), "sel" if sel else "bg")   # v1.5: 键名双重兼容
    if not k[0]:
        return None
    v = _icon_photos.get(k)
    if v is not None:
        return v if v is not False else None
    b64 = _ppm_cache.get(k)
    if b64 is None:
        try:
            b64 = _make_ppm_b64(app, int(px), ICON_BG_SEL if sel else ICON_BG)
        except Exception as e:
            _logv("icon ppm fail %s: %s" % (k[0], e))
            b64 = None
        _ppm_cache[k] = b64
    ph = False
    if b64:
        try:
            # v1.5: Tk 8.6 的 -data 不解码 base64（TclError: couldn't recognize
            # image data）→ 先解码为 PPM 原始字节, 以 latin1 逐字节映射为 str
            # 传入（Tk 依 P6 magic 识别; Windows 真机验证）。
            ph = tk_mod.PhotoImage(data=base64.b64decode(b64).decode("latin1"),
                                   format="PPM")
        except Exception as e:
            _logv("icon photo fail %s: %s" % (k[0], e))
    _icon_photos[k] = ph
    return ph if ph is not False else None


def _picker_screen_rect():
    """Windows: 光标所在显示器的工作区 (x, y, w, h)（物理像素; 多屏 + 任务栏规避）。
    失败 None（调用方回退 Tk 主屏值）。"""
    if not IS_WIN:
        return None
    try:
        pt = wt.POINT()
        if not _user32.GetCursorPos(ctypes.byref(pt)):
            return None
        hmon = _user32.MonitorFromPoint(pt, 2)          # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return int(r.left), int(r.top), int(r.right - r.left), int(r.bottom - r.top)
    except Exception:
        return None


# ---------------------------------------------------------------- 选择器线程
def _pick_ensure_thread():
    """常驻 Tk 线程（单例; v1.3 崩溃根治的关键）。返回 True = 线程可用。"""
    if not IS_WIN:
        return False
    t = _pick_ctl.get("thread")
    if t is not None:
        if t.is_alive():
            return True
        _pick_ctl["failed"] = True      # 线程曾崩 —— 不再重建（保进程安全）
        return False
    if _pick_ctl.get("failed"):
        return False
    try:
        _pick_ctl["cmd_q"] = queue.Queue()
        t = threading.Thread(target=_pick_thread_main, daemon=True, name="app-picker-tk")
        _pick_ctl["thread"] = t
        t.start()
        return True
    except Exception as e:
        _logv("picker thread spawn failed: %s" % e)
        _pick_ctl["failed"] = True
        return False


def _pick_reset_state():
    """只清状态（不触 Tk; 可在任意线程调用）。"""
    _pick_ctl["win"] = None
    _pick_ctl["q"] = None
    _pick_state["open"] = False


def _pick_cb_error(exc, val, tb):
    """Tk 回调异常兜底: 只记日志（绝不弹窗——防「报错弹窗」重现）。"""
    try:
        import traceback
        lines = traceback.format_exception(exc, val, tb)
        _logv("picker tk callback error: %s" % lines[-1].strip())
    except Exception:
        pass


def _pick_thread_main():
    """常驻选择器线程: 创建一次 Tk root 并永久 mainloop; 每次 PICK 只开关 Toplevel。"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.report_callback_exception = _pick_cb_error
        _pick_ctl["root"] = root
        _logv("picker tk thread ready (Tk v%s)" % tk.TkVersion)
    except Exception as e:
        _logv("picker tk init failed: %s" % e)
        _pick_ctl["failed"] = True
        _pick_reset_state()
        return

    def pump():
        try:
            while True:
                cmd = _pick_ctl["cmd_q"].get_nowait()
                if cmd == "open":
                    _pick_open()
        except queue.Empty:
            pass
        except Exception as e:
            _logv("picker pump error: %s" % e)
        try:
            root.after(100, pump)
        except Exception:
            pass

    root.after(50, pump)
    try:
        root.mainloop()
    except Exception as e:
        _logv("picker mainloop exited: %s" % e)


def do_app_pick():
    if not IS_WIN:
        return "not-windows"
    if _pick_state["open"]:
        t = _pick_ctl.get("thread")
        if t is not None and t.is_alive():
            return "picker already open (忽略)"
        _logv("picker stale open state -> reset")
        _pick_reset_state()
    if not _pick_ensure_thread():
        return "picker unavailable (Tk 线程故障, 详见日志)"
    _pick_state["open"] = True
    try:
        _pick_ctl["cmd_q"].put_nowait("open")
    except Exception as e:
        _pick_reset_state()
        return "picker open failed: %s" % e
    return "picker opened (↑↓←→ 选择 / OK 打开 / 返回 取消)"


def _pick_open():
    """（Tk 线程内）构建并显示选择器 Toplevel; 全程异常自兜底。"""
    import tkinter as tk
    import tkinter.font as tkfont
    root = _pick_ctl.get("root")
    win = None
    try:
        if root is None:
            raise RuntimeError("tk root missing")
        apps = apps_from_windows(enum_windows(), include_minimized=False)
        if not apps:
            raise RuntimeError("no visible app windows")
        for a in apps:                          # 图标提取需要完整 exe 路径
            a["path"] = proc_exe_path(a.get("pid"))
        # —— v1.3: DPI 缩放布局（100%→96px 单元/64px 图标; 150%→144/96; 200%→192/128）
        try:
            dpi_scale = float(root.winfo_fpixels("1i")) / 96.0
        except Exception:
            dpi_scale = 1.0
        lay = pick_layout(dpi_scale, len(apps))
        # v1.8: 配色对齐 Mac AppPicker（浅灰磨砂底 + 系统蓝选中 + 近黑文字; ICON_BG 须与 BG 同值）
        BG, FG, DIM, ACC, SEL = "#8a8a8a", "#141414", "#141414", "#017aff", "#6c84af"
        NMFG, SFG = "#141414", "#141414"   # 名称文字: 非选中 / 选中（对齐 Mac 浅色 labelColor, 两态一致）
        FNAME = "Microsoft YaHei UI"
        f10 = tkfont.Font(family=FNAME, size=9)
        f12 = tkfont.Font(family=FNAME, size=10)
        s = lay["scale"]
        cw, ch = lay["cell"]
        pad = lay["pad"]
        name_budget = cw - int(round(10 * s))    # v1.6: 名称可用像素宽（两侧留白防贴边）
        # —— 多屏定位: 光标所在显示器工作区居中（失败回退 Tk 主屏）
        scr = _picker_screen_rect()
        if scr:
            sx, sy, swp, shp = scr
            gx = sx + max(0, (swp - lay["w"]) // 2)
            gy = sy + max(0, (shp - lay["h"]) // 2)
        else:
            swp, shp = root.winfo_screenwidth(), root.winfo_screenheight()
            gx = (swp - lay["w"]) // 2
            gy = (shp - lay["h"]) // 2
        win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.geometry("%dx%d+%d+%d" % (lay["w"], lay["h"], gx, gy))
        _pick_ctl["win"] = win
        tk.Label(win, text="↑ ↓ ← → 选择    ·    OK 打开    ·    返回 取消    ·    10s 自动关闭",
                 bg=BG, fg=DIM, font=f10, anchor="center").pack(fill="x", pady=(pad, 0))
        gridf = tk.Frame(win, bg=BG)
        gridf.pack(padx=pad, pady=int(round(6 * s)))
        cells = []
        icon_target = lay["icon"]
        iconwrap_h = ch - int(round(34 * s))
        for i, a in enumerate(apps):
            r, c = divmod(i, lay["cols"])
            cell = tk.Frame(gridf, bg=BG, width=cw, height=ch,
                            highlightthickness=2, highlightbackground=BG)
            cell.grid(row=r, column=c, padx=int(round(2 * s)), pady=int(round(2 * s)))
            cell.pack_propagate(False)   # v1.5: 子件走 pack; grid_propagate 对其无效（旧致 cell 宽随名字变）
            iconwrap = tk.Frame(cell, bg=BG, height=iconwrap_h)
            iconwrap.pack(fill="x", pady=(int(round(8 * s)), 0))
            iconwrap.pack_propagate(False)
            name = app_display_name(a)               # v1.4: 纯应用名（FileDescription）
            ph_img = _icon_photo_for(a, tk, icon_target)
            # v1.9: 选中格变体（SEL 蓝底合成）——透明区域在两种底色下分别贴合
            ph_sel = _icon_photo_for(a, tk, icon_target, sel=True) if ph_img is not None else None
            if ph_img is not None:
                ilb = tk.Label(iconwrap, image=ph_img, bg=BG)
            else:
                ilb = tk.Label(iconwrap, text=(name or "?")[:1].upper(),
                               fg=DIM, bg=BG, font=(FNAME, int(round(20 * s)), "bold"))
            ilb.pack()
            scroll = bool(name) and f12.measure(name) > name_budget   # v1.6: 超宽名 → 选中时滚动
            fit_text = name if not scroll else fit_prefix(name, name_budget, f12.measure)
            nlb = tk.Label(cell, text=fit_text, bg=BG, fg=NMFG, font=f12)
            nlb.pack(side="bottom", pady=(0, int(round(6 * s))))
            cells.append({"f": cell, "ws": [iconwrap, ilb, nlb], "nlb": nlb, "name": name,
                          "off": 0, "scroll": scroll, "fit": fit_text,
                          "ilb": ilb, "ph": ph_img, "phs": (ph_sel or ph_img)})   # v1.9: 双变体
        result = {"hwnd": None, "done": False}
        cur = {"i": 1 if len(apps) > 1 else 0}     # 初始=第 2 项（≈上一应用, 对齐 Mac）
        last = {"t": time.time()}

        def _paint():
            for i, cc in enumerate(cells):
                on = (i == cur["i"])
                bgc = SEL if on else BG
                cc["f"].configure(bg=bgc, highlightbackground=(ACC if on else BG))
                for wdg in cc["ws"]:
                    wdg.configure(bg=bgc)
                if cc["ph"] is not None:            # v1.9: 图标换底变体（透明融合）
                    cc["ilb"].configure(image=(cc["phs"] if on else cc["ph"]))
                cc["nlb"].configure(fg=(SFG if on else NMFG))
                if cc["scroll"]:                     # v1.6: 选中从头发车; 非选中静态截断
                    if on:
                        cc["off"] = 0
                        cc["nlb"].configure(text=cycle_slice(cc["name"], 0, name_budget, f12.measure))
                    else:
                        cc["nlb"].configure(text=cc["fit"])

        def _move(a):
            i = grid_move(cur["i"], a, lay["cols"], len(apps))   # v1.7: 网格方向导航
            if i != cur["i"]:
                cur["i"] = i
                _paint()

        def _close():
            result["done"] = True
            try:
                win.destroy()
            except Exception:
                pass
            _pick_reset_state()
            if result["hwnd"]:
                try:
                    force_foreground(result["hwnd"])
                except Exception as e:
                    _logv("picker foreground fail: %s" % e)

        def choose(_evt=None):
            result["hwnd"] = apps[cur["i"]].get("hwnd")
            _close()

        def cancel(_evt=None):
            _close()

        q = queue.Queue()
        _pick_ctl["q"] = q

        def _poll():
            try:
                while True:
                    a = q.get_nowait()
                    last["t"] = time.time()
                    if a in ("UP", "DOWN", "LEFT", "RIGHT"):
                        _move(a)
                    elif a in ("ENTER", "KP_ENTER"):
                        choose()
                        return
                    elif a in ("ESC", "BACKSPACE"):
                        cancel()
                        return
            except queue.Empty:
                pass
            except Exception as e:
                _logv("picker poll error: %s" % e)
            if not result["done"]:
                win.after(80, _poll)

        def _tick():
            if result["done"]:
                return
            if time.time() - last["t"] > PICK_AUTO_CANCEL:
                _logv("picker auto-cancel (%ds 无操作)" % int(PICK_AUTO_CANCEL))
                cancel()
                return
            win.after(500, _tick)

        def _marquee():
            """v1.6: 选中项长名滚动（每 PICK_MARQUEE_MS 步进 1 字符; 非超宽项不动）。"""
            if result["done"]:
                return
            try:
                cc = cells[cur["i"]]
                if cc["scroll"]:
                    cc["off"] = (cc["off"] + 1) % (len(cc["name"]) + 3)
                    cc["nlb"].configure(text=cycle_slice(cc["name"], cc["off"], name_budget, f12.measure))
            except Exception as e:
                _logv("picker marquee error: %s" % e)
            win.after(PICK_MARQUEE_MS, _marquee)

        def _make_click(i):
            def _click(_evt=None):
                cur["i"] = i
                last["t"] = time.time()
                _paint()
            return _click

        def _bind_tree(wdg, i):
            wdg.bind("<Button-1>", _make_click(i))
            wdg.bind("<Double-Button-1>", choose)
            for ch2 in wdg.winfo_children():
                _bind_tree(ch2, i)

        for i, cc in enumerate(cells):
            _bind_tree(cc["f"], i)
        win.bind("<Return>", choose)
        win.bind("<KP_Enter>", choose)
        win.bind("<Escape>", cancel)
        win.bind("<BackSpace>", cancel)

        def _grab():
            """尽力抢前台（失败无碍: 按键走路由; 鼠标点击天然可用; 不闪屏）。"""
            try:
                win.focus_force()
            except Exception:
                pass
            try:
                top = _user32.GetAncestor(win.winfo_id(), GA_ROOT)
                _user32.SetForegroundWindow(top)
                _user32.BringWindowToTop(top)
            except Exception:
                pass

        _paint()
        try:  # v1.5: 按实际请求尺寸兜底校正窗口（防字体/DPI 差异下网格被裁）
            win.update_idletasks()
            win.geometry("%dx%d+%d+%d" % (
                max(lay["w"], gridf.winfo_reqwidth() + 2 * pad),
                max(lay["h"], win.winfo_reqheight()), gx, gy))
        except Exception:
            pass
        win.deiconify()
        win.lift()
        win.after(60, _grab)
        win.after(80, _poll)
        win.after(500, _tick)
        win.after(PICK_MARQUEE_MS, _marquee)
        _logv("picker open: %d apps, sel=%d, dpi=%.0f%% (%dx%d)" % (
            len(apps), cur["i"], lay["scale"] * 100, lay["w"], lay["h"]))
    except Exception as e:
        _logv("picker open failed: %s" % e)
        try:
            if win is not None:
                win.destroy()
        except Exception:
            pass
        _pick_reset_state()


# ---------------------------------------------------------------- v1.2: URL / RUN
# 平台原语（测试可打桩）:
_startfile = getattr(os, "startfile", None)   # Windows: 默认浏览器打开; 非 Windows=None
_run_spawn = subprocess.Popen                 # RUN 命令启动器（测试可打桩）


def do_url(url):
    """v1.2 URL:<网址>: 打开网页（默认浏览器; per-url 0.6s 防抖由调用方收包线程执行）。
    与 Mac key_bridge.do_url 同构。"""
    u = (url or "").strip()
    if not u:
        return "URL no-arg"
    if _startfile is None:
        return "URL unavailable (no startfile)"
    try:
        _startfile(u)
    except Exception as e:
        return "URL FAIL %s: %r" % (e, u)
    return "URL -> " + u


def do_run(cmd):
    """v1.2 RUN:<命令>: 执行命令（cmd /c; 值不含空格=UDP 协议约束, 复杂命令请用
    脚本文件后填其路径）。与 Mac key_bridge.do_run 同构。"""
    c = (cmd or "").strip()
    if not c:
        return "RUN no-arg"
    try:
        _run_spawn(c, shell=True, cwd=os.path.expanduser("~"))
    except Exception as e:
        return "RUN FAIL %s: %r" % (e, c)
    return "RUN -> " + c


# ================================================================
# D. 分发接口（win_receiver 用）
# ================================================================
def is_ext_action(action):
    a = (action or "").upper()
    return a in ("CLICK", "FOCUS_INPUT") or a.startswith(("APP:", "URL:", "RUN:"))


def debounce_for(action):
    """防抖窗口（秒）——对齐 Mac key_bridge: CLICK/FOCUS/URL/RUN=0.6, APP:CLOSE=2.0, 其余 APP=0.35。"""
    a = (action or "").upper()
    if a in ("CLICK", "FOCUS_INPUT") or a.startswith(("URL:", "RUN:")):
        return 0.6
    if a == "APP:CLOSE":      # v1.10: 关闭后前台必变——强防抖防连关第二个应用（对齐 Mac CLOSE_DEBOUNCE=2.0）
        return 2.0
    return 0.35


def handle(action):
    """执行扩展动作（仅 DOWN 已由调用方过滤; 返回详情字符串进日志）。"""
    a = (action or "").upper()
    if a == "CLICK":
        return do_click()
    if a == "FOCUS_INPUT":
        return do_focus_input()
    if a.startswith("APP:"):
        verb = action[4:].strip()
        vl = verb.lower()
        if vl == "cycle":
            return do_app_cycle()
        if vl == "toggle":
            return do_app_toggle()
        if vl == "next":
            return do_app_next()
        if vl == "pick":
            return do_app_pick()
        if vl == "close":
            return do_app_close()
        return do_app_activate(verb)
    if a.startswith("URL:"):
        return do_url(action[4:].strip())
    if a.startswith("RUN:"):
        return do_run(action[4:].strip())
    return "unknown ext action: %s" % action


# ---------------------------------------------------------------- 自检
def selftest():
    lines = ["win_actions v%s selftest" % VERSION,
             "platform: %s | dpi: %s | uia: %s" % (sys.platform, _dpi_state, uia_probe())]
    wins = enum_windows()
    apps = apps_from_windows(wins, include_minimized=True)
    lines.append("top-level windows (filtered): %d | apps: %d" % (len(wins), len(apps)))
    for a in apps[:12]:
        lines.append("  %-18s | %s" % (a["exe"][:18], (a["title"] or "")[:44]))
    try:
        import tkinter as _tk
        lines.append("tkinter: v%s ok (APP:PICK 图标网格可用)" % _tk.TkVersion)
    except Exception as e:
        lines.append("tkinter: FAILED (%s) -> APP:PICK 不可用" % e)
    if IS_WIN:
        lines.append("uwp icon path: shell:AppsFolder via IShellItemImageFactory %s"
                     % ("ready" if _shell32 is not None else "N/A"))
    if IS_WIN and uia_probe() == "ready":
        try:
            uia = get_uia()
            if uia is None:
                lines.append("uia init: FAILED (%s)" % _uia_error)
            else:
                f = _sane_focus(uia, uia.focused())
                if f is None:
                    lines.append("focused element: (none / filtered)")
                else:
                    lines.append("focused element: %s rect=%s" % (_label(uia, f), uia.rect(f)))
        except Exception as e:
            lines.append("uia probe error: %s" % e)
    return "\n".join(lines)
