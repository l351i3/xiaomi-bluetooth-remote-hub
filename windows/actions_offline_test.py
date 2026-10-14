#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""actions_offline_test.py — win_actions.py 离线逻辑测试（macOS/Linux 可跑, 无需 Windows）

打桩法：FakeUia + FakeElem 模拟 UIA 后端（win_actions 的 B 层策略纯逻辑），
不触达任何平台 API。Windows 上同样可跑（本文件不依赖平台）。
覆盖:
  1) 防抖表 / 扩展动作识别（对齐 Mac key_bridge 参数）
  2) click_strategy 四段策略（自身→直接子→向上≤6→坐标兜底+尺寸门槛）
  3) focus_input_strategy 五阶段（缓存→网格底部优先→树反算→SetFocus 读回 / Document 尺寸启发 / y 钳制）
  4) cycle_step 环推进（首按/续按/超时重建/补首位/跳死/不足2个）
  5) toggle_target / next_target
  6) match_query 匹配链（.exe 变体 / 大小写 / 标题）
  7) apps_from_windows 过滤去重（最小化 / 每 exe 首窗 / z 序保持）
  8) is_input_like Document 尺寸启发式
  9) picker_route 按键直连路由（v1.1：关闭不拦 / 未就绪回退 / 拦截投递 / up 相位吞掉 / 非 picker 键放行）
 10) URL / RUN（v1.2：startfile / Popen 打桩、空值拒绝、非 Windows 降级、异常捕获、handle 分派大小写保真）
 11) v1.3 纯逻辑：pick_move 环绕 / pick_layout DPI 缩放与钳制 / composite_rgba_on_bg
     合成数学 / scale_rgb 双线性缩放 / ppm_encode 头格式
 12) v1.4 纯逻辑：is_host_process UWP 宿主识别 / choose_display_name 名称净化 /
     trim_rgba 内容外接框裁剪 / square_pad_rgba 保比例补方
13) v1.5 纯逻辑：scale_rgba 预乘双线性 / optical_fit_rgba 光学归一（√面积）/
     源码约定静态守护（cell.pack_propagate / 键名兼容 / PhotoImage latin1 / 光学管线）
14) v1.6 纯逻辑：fit_prefix 静态截断 / cycle_slice 跑马灯窗口 /
     源码约定静态守护（无旧硬截断 / 名称文字近黑 / 灰底与 ICON_BG 同值 / marquee 接入）
15) v1.7 纯逻辑：grid_move 网格方向导航（↑↓=垂直/回绕/末行不满取最近列；←→=线性环绕；
     单行/单列退化；越界/非法输入安全）/ GUID 结构解析（Shell AppsFolder 通路 + 内存布局）/
     is_uwp_path 包应用路径判定 / 非 Win 安全返回 / 源码约定静态守护（uwp·路径分流 /
     网格导航接入 / 接口常量在场）
16) v1.9 双底色变体：composite_rgba_on_bg SEL 底合成数学 / _finish_icon_ppm bg 变体
     端到端（角部=底 / 中心=内容 / P6 头）/ 源码约定静态守护（常量·缓存键·换底接入）
17) v1.10 关闭当前应用（APP:CLOSE）：close_poll 轮询注入打桩（立即关/前台切换/延迟关/
     持续存活超时）/ debounce_for=2.0 / is_ext_action 放行 / handle 分派（非 Win 安全降级）/
     源码约定静态守护（WM_CLOSE 通路·优雅退出·UWP 真身·shell 拒绝）
18) v1.11 鼠标模式（MouseGlide 滑行引擎）：加速离散积分/速度上限/停止即停/1.2s 看门狗/
    对向相消/斜向不归一化/边界夹取/滚动速率与方向/保活刷新/stop_all +
    mouse_control 分派矩阵 + 源码约定静态守护（常量·类·入口·WHEEL·线程懒启动）
19) v1.12 实测反馈修复轮：速度事件驱动清零（stop/看门狗扫除即归零 —— 治「越按越快」,
    离散按压流对照）/ MODE 提示分派（非 Win 优雅降级）/ REPORT 取证报告落盘
    （重定向 STATE_DIR 零副作用）/ _mouse_stat 计数与 click ok-fail 分类 +
    源码约定静态守护（impl 改名·HUD 接入 pump·探针零位移）
20) v1.13 ★ 跨模块 SendInput 类型冲突修复（元凶级）：类统一运行时断言
    （win_receiver.INPUT is win_actions.INPUT）/ 兜底分支等价性（sys.modules 哨兵）/
    源码形态守护（通用层定义·复用分支·异常落盘·input_class_module 指纹）
21) v1.14 电源键连击切换设备（HUD）：TARGET:SWITCH 分派矩阵（仅 DOWN / 非法目标 /
    大小写宽容 / 非 Win no-tk 降级）/ 取证计数 / win_actions + win_receiver 源码
    约定守护（SWITCH_NAMES·_hud_open_text 抽取·pump swhud 接入·双前缀路由·版本标识）
22) v1.15 FOCUS_INPUT 兜底点击：全 miss + click_at -> NOEDIT+CLICK@底部中央(0.5,0.92) /
    点击失败如实降级 / 矮窗 y 钳制 / 既有 NOEDIT 断言向后兼容（默认不兜底）
23) v1.16 do_app_activate 观察日志：changelog / app-activate 前缀 / front= 记录
    源码约定静态守护（另：20d/21d 版本标识断言同步 win_receiver v1.11）
用法：python3 actions_offline_test.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "win_actions.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(HERE, "win_actions.py"), "__name__": "win_actions_test"}
exec(compile(src, "win_actions.py", "exec"), ns)

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, "| got =", repr(got), "| want =", repr(want))


# ---------------------------------------------------------------- 打桩
class FakeElem:
    """模拟 UIA 控件元素。t=ControlType; ch=children; parent 由构造时回填。"""

    def __init__(self, t, name="", rect=None, children=(), invoke_ok=False,
                 focus_ok=True, focus_result=None):
        self.t = t
        self.name = name
        self.rect = rect
        self.ch = list(children)
        for c in self.ch:
            c.parent = self
        self.parent = None
        self.invoke_ok = invoke_ok
        self.focus_ok = focus_ok
        # focus_result=False -> SetFocus 调用成功但读回仍 False（模拟设置未生效）
        self.focus_result = focus_result
        self.has_focus = False


class FakeUia:
    def __init__(self):
        self.focused_el = None
        self.point_map = {}
        self.handle_map = {}
        self.invoked = []
        self.point_queries = []
        self.focus_calls = []

    def focused(self):
        return self.focused_el

    def from_point(self, x, y):
        self.point_queries.append((x, y))
        return self.point_map.get((x, y))

    def from_handle(self, hwnd):
        return self.handle_map.get(hwnd)

    def children(self, e):
        return list(e.ch)

    def parent(self, e):
        return e.parent

    def ctrl_type(self, e):
        return e.t

    def name(self, e):
        return e.name

    def rect(self, e):
        return e.rect

    def invoke(self, e):
        self.invoked.append(e)
        return bool(e.invoke_ok)

    def set_focus(self, e):
        self.focus_calls.append(e)
        if not e.focus_ok:
            return False
        if e.focus_result is False:
            return True
        e.has_focus = True
        return True

    def has_focus(self, e):
        return e.has_focus

    def find_type(self, root, t):
        stack, n = [root], 0
        while stack and n < 500:
            c = stack.pop()
            n += 1
            if c.t == t:
                return c
            stack.extend(reversed(c.ch))
        return None


CT_E, CT_C, CT_D, CT_BTN, CT_WIN = 50004, 50003, 50030, 50000, 50032

# ---- 1) 防抖表 / 扩展动作识别 ----
print("== 1) 防抖表 / 扩展动作识别 ==")
check("debounce CLICK = 0.6", ns["debounce_for"]("CLICK"), 0.6)
check("debounce FOCUS_INPUT = 0.6", ns["debounce_for"]("FOCUS_INPUT"), 0.6)
check("debounce APP:CYCLE = 0.35", ns["debounce_for"]("APP:CYCLE"), 0.35)
check("debounce APP:WorkBuddy = 0.35", ns["debounce_for"]("APP:WorkBuddy"), 0.35)
check("debounce URL:https://x = 0.6", ns["debounce_for"]("URL:https://x"), 0.6)
check("debounce RUN:foo.exe = 0.6", ns["debounce_for"]("RUN:foo.exe"), 0.6)
check("is_ext CLICK", ns["is_ext_action"]("CLICK"), True)
check("is_ext APP:PICK", ns["is_ext_action"]("APP:PICK"), True)
check("is_ext URL:https://x", ns["is_ext_action"]("URL:https://x"), True)
check("is_ext RUN:foo", ns["is_ext_action"]("RUN:foo"), True)
check("is_ext ENTER = False", ns["is_ext_action"]("ENTER"), False)

# ---- 2) click_strategy 四段 ----
print("== 2) click_strategy 四段 ==")
click_strategy = ns["click_strategy"]
clicks = []


def fake_click(x, y):
    clicks.append((x, y))
    return True


# ① 自身
e1 = FakeElem(CT_BTN, rect=(10, 10, 60, 40), invoke_ok=True)
u = FakeUia()
ok, det = click_strategy(u, e1, fake_click)
check("① 自身 Invoke", (ok, det.startswith("press self")), (True, True))
check("① 仅调用自身", u.invoked, [e1])

# ② 直接子
child = FakeElem(CT_BTN, invoke_ok=True)
e2 = FakeElem(CT_WIN, children=[child], invoke_ok=False, rect=(0, 0, 5, 5))
u = FakeUia()
ok, det = click_strategy(u, e2, fake_click)
check("② 直接子 Invoke", (ok, det.startswith("press child")), (True, True))

# ③ 向上 3 层
up3 = FakeElem(CT_BTN, invoke_ok=True)
up2 = FakeElem(CT_WIN)
up2.parent = up3
up1 = FakeElem(CT_WIN)
up1.parent = up2
e3 = FakeElem(CT_WIN, invoke_ok=False, rect=(100, 100, 200, 200))
e3.parent = up1
u = FakeUia()
ok, det = click_strategy(u, e3, fake_click)
check("③ 向上 3 层 Invoke", (ok, det.startswith("press up3")), (True, True))

# ④ 坐标兜底（中心 + 尺寸门槛）
e4 = FakeElem(CT_WIN, rect=(100, 100, 200, 140))     # 100x40
u = FakeUia()
ok, det = click_strategy(u, e4, fake_click)
check("④ 坐标兜底成功", (ok, det.startswith("click@")), (True, True))
check("④ 坐标=元素中心", clicks[-1], (150, 120))
e5 = FakeElem(CT_WIN, rect=(0, 0, 8, 4))             # 8x4 不满足 w>8,h>4
u = FakeUia()
ok, det = click_strategy(u, e5, fake_click)
check("④ 尺寸门槛 8x4 拒绝(坐标)", ok, False)
e6 = FakeElem(CT_WIN, rect=(0, 0, 9, 5))             # 9x5 刚好通过
u = FakeUia()
ok, det = click_strategy(u, e6, fake_click)
check("④ 尺寸门槛 9x5 通过", (ok, det.startswith("click@")), (True, True))

# 无焦点元素
u = FakeUia()
check("无焦点元素 NOFOCUS", click_strategy(u, None, fake_click), (False, "NOFOCUS"))

# 向上仅查 ≤6 层（第 7 层即便支持也不该被调用 -> 坐标兜底接管）
up7 = FakeElem(CT_BTN, invoke_ok=True)
chain = [up7]
for _ in range(6):                                   # up6..up1（up1 = chain[-1]）
    nxt = FakeElem(CT_WIN)
    nxt.parent = chain[-1]
    chain.append(nxt)
elem7 = FakeElem(CT_WIN, rect=(0, 0, 100, 50), invoke_ok=False)
elem7.parent = chain[-1]
u = FakeUia()
ok, det = click_strategy(u, elem7, fake_click)
check("向上第 7 层不检查（≤6）", up7 in u.invoked, False)
check("向上超限 -> 坐标兜底", (ok, det.split()[0]), (True, "click@50,25"))

# ---- 3) focus_input_strategy 五阶段 ----
print("== 3) focus_input_strategy 五阶段 ==")
fis = ns["focus_input_strategy"]
win_ctx = {"hwnd": 777, "rect": (0, 0, 1000, 800), "exe_key": "app.exe"}

# A 缓存命中
u = FakeUia()
ed = FakeElem(CT_E)
u.point_map[(500, 680)] = ed
ok, det, frac = fis(u, win_ctx, {"app.exe": {"fx": 0.5, "fy": 0.85}})
check("缓存命中", (ok, "src=cache" in det), (True, True))
check("缓存 frac 原样返回", frac, (0.5, 0.85))

# B 网格底部优先
u = FakeUia()
ed = FakeElem(CT_E)
u.point_map[(500, 680)] = ed
ok, det, frac = fis(u, win_ctx, {})
check("网格命中", (ok, "src=grid" in det), (True, True))
check("网格首试点=底部中央 (500,680)", u.point_queries[0], (500, 680))

# C 整窗 Document 拒绝 -> 网格继续
u = FakeUia()
doc_big = FakeElem(CT_D, rect=(0, 0, 1000, 800))
u.point_map[(500, 680)] = doc_big
ed2 = FakeElem(CT_E)
u.point_map[(620, 680)] = ed2
ok, det, frac = fis(u, win_ctx, {})
check("整窗 Document 拒绝后网格继续", (ok, "src=grid" in det), (True, True))
check("第二次试点=(620,680)", u.point_queries[1], (620, 680))

# D 小 Document 接受（输入框特征）
u = FakeUia()
doc_small = FakeElem(CT_D, rect=(100, 600, 900, 700))    # 高 100 < 800*0.55
u.point_map[(500, 680)] = doc_small
ok, det, frac = fis(u, win_ctx, {})
check("小 Document 接受", (ok, "src=grid" in det), (True, True))

# E 网格全 miss -> 树遍历（Edit + frac 反算）
u = FakeUia()
root = FakeElem(CT_WIN)
ed_tree = FakeElem(CT_E, rect=(400, 600, 600, 640))
root.ch = [ed_tree]
ed_tree.parent = root
u.handle_map[777] = root
ok, det, frac = fis(u, win_ctx, {})
check("树命中 Edit", (ok, "src=tree" in det), (True, True))
check("树 frac 反算", (round(frac[0], 3), round(frac[1], 3)), (0.5, 0.775))

# F 全 miss -> NOEDIT
u = FakeUia()
root2 = FakeElem(CT_WIN)
u.handle_map[777] = root2
ok, det, frac = fis(u, win_ctx, {})
check("全 miss -> NOEDIT", (ok, det.startswith("NOEDIT"), frac), (False, True, None))

# F2 v1.15 全 miss + click_at -> 兜底点击（底部中央 (500,736)）
u = FakeUia()
root3 = FakeElem(CT_WIN)
u.handle_map[777] = root3
clicked = []

def _fc(x, y):
    clicked.append((x, y))
    return True

ok, det, frac = fis(u, win_ctx, {}, click_at=_fc)
check("全 miss 兜底点击", (ok, det.startswith("NOEDIT+CLICK"), frac), (False, True, None))
check("兜底点击坐标=底部中央 (500,736)", clicked, [(500, 736)])

# F3 兜底点击失败 -> 普通 NOEDIT（如实返回, 不谎报）
u = FakeUia()
root4 = FakeElem(CT_WIN)
u.handle_map[777] = root4
ok, det, frac = fis(u, win_ctx, {}, click_at=lambda x, y: False)
check("兜底点击失败 -> 普通 NOEDIT", (ok, det.startswith("NOEDIT "), frac), (False, True, None))

# F4 矮窗兜底 y 钳制：int(30*0.92)=27 > 30-4=26 -> 钳至 26
u = FakeUia()
root5 = FakeElem(CT_WIN)
u.handle_map[778] = root5
clicked2 = []
ok, det, frac = fis(u, {"hwnd": 778, "rect": (0, 0, 1000, 30), "exe_key": "c.exe"}, {},
                    click_at=lambda x, y: (clicked2.append((x, y)), True)[1])
check("矮窗兜底 y 钳制 (500,26)", clicked2, [(500, 26)])

# G SetFocus 失败
u = FakeUia()
u.point_map[(500, 680)] = FakeElem(CT_E, focus_ok=False)
ok, det, frac = fis(u, win_ctx, {})
check("SetFocus 失败 -> FAIL-set", (ok, det.startswith("FAIL-set")), (False, True))

# H 读回失败（调用成功焦点未生效）
u = FakeUia()
u.point_map[(500, 680)] = FakeElem(CT_E, focus_result=False)
ok, det, frac = fis(u, win_ctx, {})
check("读回失败 -> FAIL-readback", (ok, det.startswith("FAIL-readback")), (False, True))

# I y 钳制（矮窗口）: 0.85*60=51 -> 钳至 60-10=50
u = FakeUia()
ctx_small = {"hwnd": 778, "rect": (0, 0, 1000, 60), "exe_key": "b.exe"}
u.point_map[(500, 50)] = FakeElem(CT_E)
ok, det, frac = fis(u, ctx_small, {})
check("y 钳制命中 (500,50)", (ok, (500, 50) in u.point_queries), (True, True))
check("y 钳制未查询 51", (500, 51) in u.point_queries, False)

# J 非法缓存（越界）忽略 -> 网格
u = FakeUia()
u.point_map[(500, 680)] = FakeElem(CT_E)
ok, det, frac = fis(u, win_ctx, {"app.exe": {"fx": 5.0, "fy": -1}})
check("非法缓存忽略走网格", (ok, "src=grid" in det), (True, True))

# ---- 4) cycle_step ----
print("== 4) cycle_step 环推进 ==")
cs = ns["cycle_step"]
ordered = ["code.exe", "chrome.exe", "wechat.exe"]
alive = set(ordered)
t1, st2, det1 = cs({}, "code.exe", ordered, alive, 1000.0)
check("首按 -> chrome", t1, "chrome.exe")
check("首按 idx=1", st2["cycle_idx"], 1)
check("首按 expect=chrome", st2["cycle_expect"], "chrome.exe")
t2, st3, det2 = cs(st2, "chrome.exe", ordered, alive, 1010.0)
check("续按 -> wechat", t2, "wechat.exe")
check("续按 idx=2", st3["cycle_idx"], 2)
t3, st4, det3 = cs(st3, "wechat.exe", ["chrome.exe", "wechat.exe", "code.exe"],
                   alive, 9999.0)
check("超时重建（新序列）-> code", t3, "code.exe")
check("超时重建标记", "重建" in det3, True)
t4, st5, det4 = cs({}, "z.exe", ["a.exe", "b.exe"],
                   {"z.exe", "a.exe", "b.exe"}, 2000.0)
check("front 不在列表 -> 补首位后推进", t4, "a.exe")
t5, st6, det5 = cs({}, "a.exe", ["a.exe", "b.exe", "c.exe"],
                   {"a.exe", "c.exe"}, 3000.0)
check("跳死条目 -> c", t5, "c.exe")
t6, st7, det6 = cs({}, "a.exe", ["a.exe", "b.exe"], {"a.exe"}, 4000.0)
check("环中全死 -> None", t6, None)
t7, st8, det7 = cs({}, "a.exe", ["a.exe"], {"a.exe"}, 5000.0)
check("不足 2 个 -> None", t7, None)

# ---- 5) toggle / next ----
print("== 5) toggle / next ==")
tt = ns["toggle_target"]
check("无记录", tt({}, "a.exe"), (None, "无切换记录"))
check("front==cur -> prev", tt({"prev": "a.exe", "cur": "b.exe"}, "b.exe"),
      ("a.exe", "toggle"))
check("front!=cur -> cur", tt({"prev": "a.exe", "cur": "b.exe"}, "c.exe"),
      ("b.exe", "toggle"))
check("prev 空 -> 无操作", tt({"prev": "", "cur": "b.exe"}, "b.exe"),
      (None, "目标与当前相同"))
nt = ns["next_target"]
check("NEXT 环", nt(["a", "b", "c"], "a"), "b")
check("NEXT 环尾回环", nt(["a", "b", "c"], "c"), "a")
check("NEXT front 不在 -> 首个", nt(["a", "b", "c"], "z"), "a")
check("NEXT 单个 -> None", nt(["a"], "a"), None)

# ---- 6) match_query ----
print("== 6) match_query 匹配链 ==")
mq = ns["match_query"]
entries = [
    {"key": "code.exe", "exe": "Code.exe", "title": "main.py - Visual Studio Code"},
    {"key": "wechat.exe", "exe": "WeChat.exe", "title": "微信"},
    {"key": "chrome.exe", "exe": "chrome.exe", "title": "Google Chrome"},
]
check("exe 去扩展名精确", mq("code", entries)["key"], "code.exe")
check("exe 带扩展名精确", mq("Code.exe", entries)["key"], "code.exe")
check("标题精确（中文）", mq("微信", entries)["key"], "wechat.exe")
check("exe 包含", mq("wechat", entries)["key"], "wechat.exe")
check("标题包含", mq("studio", entries)["key"], "code.exe")
check("大小写不敏感", mq("WECHAT", entries)["key"], "wechat.exe")
check("无命中 None", mq("notepad", entries), None)
check("空查询 None", mq("   ", entries), None)

# ---- 7) apps_from_windows ----
print("== 7) apps_from_windows ==")
afw = ns["apps_from_windows"]
wins = [
    {"hwnd": 1, "title": "A1", "exe": "A.exe", "exe_key": "a.exe", "pid": 1, "minimized": False},
    {"hwnd": 2, "title": "A2", "exe": "A.exe", "exe_key": "a.exe", "pid": 1, "minimized": False},
    {"hwnd": 3, "title": "B", "exe": "B.exe", "exe_key": "b.exe", "pid": 2, "minimized": True},
    {"hwnd": 4, "title": "C", "exe": "C.exe", "exe_key": "c.exe", "pid": 3, "minimized": False},
]
a1 = afw(wins)
check("排除最小化 + 每 exe 去重", [a["key"] for a in a1], ["a.exe", "c.exe"])
check("代表窗口 = z 最高", a1[0]["hwnd"], 1)
a2 = afw(wins, include_minimized=True)
check("含最小化（保 z 序）", [a["key"] for a in a2], ["a.exe", "b.exe", "c.exe"])
check("minimized 标记保留", a2[1]["minimized"], True)

# ---- 8) is_input_like ----
print("== 8) is_input_like Document 尺寸启发式 ==")
iil = ns["is_input_like"]
u = FakeUia()
check("Edit 任意大小接受", iil(u, FakeElem(CT_E, rect=(0, 0, 1000, 800)), 1000, 800), True)
check("ComboBox 接受", iil(u, FakeElem(CT_C), 1000, 800), True)
check("整窗 Document 拒绝", iil(u, FakeElem(CT_D, rect=(0, 0, 1000, 800)), 1000, 800), False)
check("矮 Document 接受", iil(u, FakeElem(CT_D, rect=(0, 600, 1000, 700)), 1000, 800), True)
check("窄 Document 接受", iil(u, FakeElem(CT_D, rect=(0, 0, 300, 800)), 1000, 800), True)
check("其他类型拒绝", iil(u, FakeElem(CT_BTN, rect=(0, 0, 100, 50)), 1000, 800), False)
check("None 拒绝", iil(u, None, 1000, 800), False)

# ---- 9) picker_route（v1.1 按键直连路由）----
print("== 9) picker_route 按键直连路由 ==")
import queue as _q
pr = ns["picker_route"]
pst = ns["_pick_state"]
pctl = ns["_pick_ctl"]

pst["open"] = False
pctl["q"] = None
check("关闭时 UP 不拦截", pr("UP", "down"), False)
check("关闭时 ENTER 不拦截", pr("ENTER", "down"), False)
check("关闭时 CLICK 不拦截", pr("CLICK", "down"), False)

pst["open"] = True
pctl["q"] = None
check("已打开但队列未就绪 → 回退注入", pr("UP", "down"), False)

qq = _q.Queue()
pctl["q"] = qq
check("UP down 拦截", pr("UP", "down"), True)
check("UP 已投递", qq.get_nowait(), "UP")
check("小写动作名同样拦截", pr("up", "down"), True)
check("投递值已标准化大写", qq.get_nowait(), "UP")
check("DOWN 拦截", pr("DOWN", "down"), True)
check("DOWN 已投递", qq.get_nowait(), "DOWN")
check("ENTER 拦截", pr("ENTER", "down"), True)
check("ENTER 已投递", qq.get_nowait(), "ENTER")
check("UP 的 up 相位吞掉", pr("UP", "up"), True)
check("up 相位不产生投递", qq.empty(), True)
check("非 picker 键不拦截（SPACE）", pr("SPACE", "down"), False)
check("扩展动作不拦截（CLICK）", pr("CLICK", "down"), False)
check("非 picker 键不投递", qq.empty(), True)

pst["open"] = False
pctl["q"] = None

# ---- 10) URL / RUN（v1.2 扩展动作）----
print("== 10) URL / RUN ==")
opened = []
ns["_startfile"] = lambda u: opened.append(u)
check("do_url 正常返回", ns["do_url"]("https://www.baidu.com"), "URL -> https://www.baidu.com")
check("do_url 调 startfile 原值", opened, ["https://www.baidu.com"])
check("do_url 空值拒绝", ns["do_url"](""), "URL no-arg")

ns["_startfile"] = None
check("do_url 非 Windows 降级", ns["do_url"]("https://x"), "URL unavailable (no startfile)")


def _boom_startfile(u):
    raise RuntimeError("boom")


ns["_startfile"] = _boom_startfile
check("do_url 异常捕获", ns["do_url"]("https://x").startswith("URL FAIL"), True)

spawned = []
ns["_run_spawn"] = lambda c, shell=False, cwd=None: spawned.append((c, shell, cwd))
check("do_run 正常返回", ns["do_run"]("calc.exe"), "RUN -> calc.exe")
check("do_run shell=True", spawned[-1][1], True)
check("do_run cwd=home", spawned[-1][2], os.path.expanduser("~"))
check("do_run 空值拒绝", ns["do_run"]("   "), "RUN no-arg")


def _boom_spawn(c, shell=False, cwd=None):
    raise RuntimeError("x")


ns["_run_spawn"] = _boom_spawn
check("do_run 异常捕获", ns["do_run"]("x").startswith("RUN FAIL"), True)

# handle() 分派 + 大小写保真（URL/RUN 值原样透传, 仅前缀参与判定）
ns["do_url"] = lambda u: "URL -> " + u
ns["do_run"] = lambda c: "RUN -> " + c
check("handle URL: 分派+大小写保真", ns["handle"]("URL:https://Example.COM/Path?q=Aa"),
      "URL -> https://Example.COM/Path?q=Aa")
check("handle RUN: 分派+大小写保真", ns["handle"]("RUN:C:\\Tools\\MyScript.CMD"),
      "RUN -> C:\\Tools\\MyScript.CMD")
check("handle 未知动作", ns["handle"]("FOO:bar").startswith("unknown"), True)

# ---- 11) v1.3 纯逻辑: 选择器网格 / DPI / 图标管线 ----
print("== 11) v1.3 pick_move / pick_layout / 图标管线 ==")
pm = ns["pick_move"]

# 环绕移动（Mac 对齐: ←/↑=-1, →/↓=+1; wrap）
check("move 首项 +1", pm(0, 1, 5), 1)
check("move 尾项 +1 环绕", pm(4, 1, 5), 0)
check("move 首项 -1 环绕", pm(0, -1, 5), 4)
check("move 中间 -1", pm(3, -1, 5), 2)
check("move d=0 原地", pm(2, 0, 5), 2)
check("move n=1 恒 0", pm(0, -1, 1), 0)
check("move n=0 安全", pm(3, 1, 0), 0)
check("move n 负数安全", pm(3, 1, -2), 0)

pl = ns["pick_layout"]

# 100% DPI, 7 项（Mac 6 列基准）
L1 = pl(1.0, 7)
check("100% 列数", L1["cols"], 6)
check("100% 行数", L1["rows"], 2)
check("100% 单元格", L1["cell"], (96, 100))
check("100% 图标 64", L1["icon"], 64)
check("100% 宽", L1["w"], 628)
check("100% 高", L1["h"], 264)

# 150% DPI（笔记本常见缩放）
L2 = pl(1.5, 7)
check("150% scale 记录", L2["scale"], 1.5)
check("150% 单元格", L2["cell"], (144, 150))
check("150% 图标 96", L2["icon"], 96)
check("150% pad", L2["pad"], 21)
check("150% 头高", L2["head_h"], 60)
check("150% 宽", L2["w"], 942)
check("150% 高", L2["h"], 396)

# 200% DPI, 13 项（3 行）
L3 = pl(2.0, 13)
check("200% 列/行数", (L3["cols"], L3["rows"]), (6, 3))
check("200% 图标 128", L3["icon"], 128)
check("200% 宽", L3["w"], 1256)
check("200% 高", L3["h"], 728)

# 钳制: <1.0 → 1.0; >3.0 → 3.0; 非法 → 1.0
check("钳制 0.5→1.0", pl(0.5, 3)["scale"], 1.0)
check("钳制 0.5 图标", pl(0.5, 3)["icon"], 64)
check("钳制 4.0→3.0", pl(4.0, 3)["scale"], 3.0)
check("钳制 4.0 图标", pl(4.0, 2)["icon"], 192)
check("钳制 4.0 宽", pl(4.0, 2)["w"], 684)
check("None→1.0", pl(None, 3)["scale"], 1.0)
check("非法值→1.0", pl("abc", 3)["scale"], 1.0)

# 边界项数: 1 项 / 0 项
L4 = pl(1.0, 1)
check("单项 1×1 网格", (L4["cols"], L4["rows"]), (1, 1))
check("单项宽 128", L4["w"], 128)
check("单项高 164", L4["h"], 164)
L5 = pl(1.0, 0)
check("0 项安全不回环", (L5["cols"], L5["rows"]), (1, 1))
check("300% 图标 192", pl(3.0, 5)["icon"], 192)

# 合成: alpha=255 全不透明 / 0 全透明 / 128 半透明（先合成后缩放的前提）
comp = ns["composite_rgba_on_bg"]
check("合成 全不透明红", comp(bytes([255, 0, 0, 255]), 1, 1), bytes([255, 0, 0]))
check("合成 全透明=底色", comp(bytes([0, 0, 0, 0]), 1, 1), bytes([0x8a, 0x8a, 0x8a]))
check("合成 半透明白", comp(bytes([255, 255, 255, 128]), 1, 1), bytes([197, 197, 197]))
check("合成 两像素各自处理", comp(bytes([0, 0, 0, 0, 0, 0, 255, 255]), 2, 1),
      bytes([0x8a, 0x8a, 0x8a, 0, 0, 255]))
check("合成 自定义底", comp(bytes([255, 255, 255, 128]), 1, 1, bg=(0, 0, 0)), bytes([128, 128, 128]))
check("合成 输出长度", len(comp(bytes([1, 2, 3, 4]) * 4, 2, 2)), 12)

# scale_rgb: 恒等 / 放大 / 缩小
sr = ns["scale_rgb"]
s1 = bytes([255, 128, 0])
check("缩放 恒等原样", sr(s1, 1, 1, 1, 1), s1)
check("缩放 1→2 全同色", sr(s1, 1, 1, 2, 2), s1 * 4)
check("缩放 输出长度", len(sr(bytes(12), 2, 2, 3, 1)), 9)
mix = bytes([0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255])
check("缩放 2×2→1×1 均值", sr(mix, 2, 2, 1, 1), bytes([191, 191, 191]))
same = bytes(range(12))
check("缩放 恒等不改内容", sr(same, 2, 2, 2, 2), same)
row2 = bytes([0, 0, 0, 255, 255, 255, 0, 0, 0, 255, 255, 255])
check("缩放 2×2→1×2 横向均值", sr(row2, 2, 2, 1, 2), bytes([128] * 6))

# ppm_encode: P6 头 + 原始 RGB
pe = ns["ppm_encode"]
check("ppm 头格式", pe(b"\x00\x01\x02", 1, 1), b"P6\n1 1\n255\n\x00\x01\x02")
check("ppm 尺寸字段", pe(b"", 0, 0), b"P6\n0 0\n255\n")
check("ppm 大图头", pe(bytes(300), 10, 10).startswith(b"P6\n10 10\n255\n"), True)

# ---- 12) v1.4 纯逻辑: 图标尺寸归一 / 应用名净化 / UWP 宿主识别 ----
print("== 12) v1.4 trim_rgba / square_pad_rgba / 名称与 UWP ==")
ihp = ns["is_host_process"]
check("宿主进程识别（设置/计算器等）", ihp("applicationframehost.exe"), True)
check("宿主识别大小写不敏感", ihp("ApplicationFrameHost.EXE"), True)
check("真实应用进程非宿主", ihp("systemsettings.exe"), False)
check("空值非宿主", ihp(""), False)

cdn = ns["choose_display_name"]
check("优先 FileDescription", cdn("Visual Studio Code", "Code.exe"), "Visual Studio Code")
check("FileDescription 去空白", cdn("  微信  ", "WeChat.exe"), "微信")
check("退路 exe 主名", cdn("", "Code.exe"), "Code")
check("退路 exe 主名大小写", cdn("", "wechat.EXE"), "wechat")
check("全空回 '?'", cdn("", ""), "?")

adn = ns["app_display_name"]
app_a = {"exe_key": "code.exe", "exe": "Code.exe", "path": ""}
check("app_display_name 退路（mac 无版本资源）", adn(app_a), "Code")
check("app_display_name 缓存一致", adn(app_a), "Code")

tr = ns["trim_rgba"]


def _mk(w, h, x0, y0, x1, y1, a=255):
    """构造 w×h RGBA: 矩形 [x0..x1]×[y0..y1] 不透明, 其余全透明。"""
    b = bytearray(w * h * 4)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            o = (y * w + x) * 4
            b[o] = 200
            b[o + 1] = 100
            b[o + 2] = 50
            b[o + 3] = a
    return bytes(b)


# 16×16 画布 / 内容 8×8 @(4,4): m=round(8*0.04)=0 → 裁到 8×8
t1b = _mk(16, 16, 4, 4, 11, 11)
r1, tw1, th1 = tr(t1b, 16, 16)
check("trim 裁空白后尺寸", (tw1, th1), (8, 8))
check("trim 首像素=内容色", r1[:4], bytes([200, 100, 50, 255]))
check("trim 输出字节数", len(r1), 8 * 8 * 4)

# 满幅内容: 原样
full = _mk(16, 16, 0, 0, 15, 15)
r2, tw2, th2 = tr(full, 16, 16)
check("trim 满幅不动", (tw2, th2), (16, 16))
check("trim 满幅内容不变", r2, full)

# 全透明: 原样
empt = bytes(16 * 16 * 4)
r3, tw3, th3 = tr(empt, 16, 16)
check("trim 全透明原样", (tw3, th3), (16, 16))

# 过小内容（<min_keep=8）: 保护原样
tiny = _mk(16, 16, 7, 7, 9, 9)
r4, tw4, th4 = tr(tiny, 16, 16)
check("trim 过小内容保护", (tw4, th4), (16, 16))

# alpha 全部低于阈值: 视为空
low = _mk(16, 16, 4, 4, 11, 11, a=5)
r5, tw5, th5 = tr(low, 16, 16)
check("trim 低 alpha 视为空", (tw5, th5), (16, 16))

# 32 画布 / 内容 20 → margin=round(20*0.04)=1 → 22×22; 边距区透明、内容不透明
t6 = _mk(32, 32, 6, 6, 25, 25)
r6, tw6, th6 = tr(t6, 32, 32)
check("trim 加边距 20→22", (tw6, th6), (22, 22))
check("trim 边距区透明", r6[3], 0)
check("trim 内容区不透明", r6[(1 * 22 + 1) * 4 + 3], 255)

sp = ns["square_pad_rgba"]
b2 = bytes([1, 2, 3, 255, 4, 5, 6, 255])
p1, pw1, ph1 = sp(b2, 2, 1)
check("pad 2×1→2×2 尺寸", (pw1, ph1), (2, 2))
check("pad 2×1 顶行=内容", p1[:8], b2)
check("pad 2×1 底行=透明", p1[8:], bytes(8))
p2, pw2, ph2 = sp(b2, 1, 2)
check("pad 1×2 左列=内容", p2[:4], b2[:4])
check("pad 1×2 右列=透明", p2[4:8], bytes(4))
check("pad 1×2 第二行左列", p2[8:12], b2[4:8])
sq = bytes(range(16))
p3, pw3, ph3 = sp(sq, 2, 2)
check("pad 正方形原样", (p3, pw3, ph3), (sq, 2, 2))

# ---- 13) v1.5 纯逻辑: 预乘缩放 / 光学归一 / 源码约定 ----
print("== 13) v1.5 scale_rgba / optical_fit_rgba / 约定 ==")
srgba = ns["scale_rgba"]
ofit = ns["optical_fit_rgba"]

quad = bytes([10, 20, 30, 255] * 4)
check("rgba 恒等原样", srgba(quad, 2, 2, 2, 2), quad)
red = bytes([255, 0, 0, 255])
check("rgba 1→2 全同色", srgba(red, 1, 1, 2, 2), red * 4)

# 半红半透 2×2 → 1×1: 预乘 — 颜色不被透明像素 RGB 污染（仍纯红）, alpha 取均值
px2 = bytes([255, 0, 0, 255,  0, 0, 0, 0,
             255, 0, 0, 255,  0, 0, 0, 0])
r1p = srgba(px2, 2, 2, 1, 1)
check("rgba 预乘色不混脏（纯红）", r1p[:3], bytes([255, 0, 0]))
check("rgba 预乘 alpha 均值", r1p[3], 128)
check("rgba 全透明 → 全透明", srgba(bytes(16), 2, 2, 1, 1), bytes(4))
check("rgba 输出长度", len(srgba(bytes(64), 4, 4, 2, 3)), 24)

# 光学归一: 32×32 全幅方（filled=1024, s=32）→ f=0.84*64/32=1.68 → 内容 54×54
sq32 = bytes([200, 100, 50, 255]) * 1024
o1, w1, h1 = ofit(sq32, 32, 32, 64)
check("光学 输出画布=px", (w1, h1), (64, 64))
check("光学 角部透明", o1[3], 0)
check("光学 中心不透明", o1[(32 * 64 + 32) * 4 + 3], 255)
cnt = sum(1 for x in range(64) if o1[(32 * 64 + x) * 4 + 3] > 8)
check("光学 方内容宽 54（REF=0.84）", cnt, 54)

# 圆形补偿: 64 画布内切圆（d=64, filled≈3217）→ f≈0.948 → 直径≈61（>方 54）
b = bytearray(64 * 64 * 4)
for yy in range(64):
    for xx in range(64):
        if (xx - 31.5) ** 2 + (yy - 31.5) ** 2 <= 1024.0:
            oo = (yy * 64 + xx) * 4
            b[oo] = 255
            b[oo + 3] = 255
o2, _, _ = ofit(bytes(b), 64, 64, 64)
cnt2 = sum(1 for x in range(64) if o2[(32 * 64 + x) * 4 + 3] > 8)
check("光学 圆>方（视觉面积补偿生效）", cnt2 > 54, True)
check("光学 圆直径 ≈61", 59 <= cnt2 <= 63, True)

# 长条大边钳制: 128×32 → 理论 f=0.84 但 lim=0.96*64/128=0.48 → 内容 61×15
strip = bytes([1, 2, 3, 255]) * (128 * 32)
o3, _, _ = ofit(strip, 128, 32, 64)
cnt3 = sum(1 for x in range(64) if o3[(32 * 64 + x) * 4 + 3] > 8)
check("光学 长条 ≤96%（横条 61）", 60 <= cnt3 <= 62, True)

# 放大上限 F_MAX=2.0: 8×8（s=8）理论 f=6.72 → 截 2.0 → 16×16（防糊）
tiny = bytes([9, 9, 9, 255]) * 64
o4, _, _ = ofit(tiny, 8, 8, 64)
cnt4 = sum(1 for x in range(64) if o4[(32 * 64 + x) * 4 + 3] > 8)
check("光学 放大上限 2.0（16px）", cnt4, 16)

# 全透明: 输出仍为 px 画布且全零
o5, w5, h5 = ofit(bytes(16 * 16 * 4), 16, 16, 64)
check("光学 全透明画布仍 px", (w5, h5), (64, 64))
check("光学 全透明全零", any(o5), False)

# 源码约定（静态守护——防关键修复被无意回改）
_srcv = open(os.path.join(HERE, "win_actions.py"), encoding="utf-8").read()
check("约定 cell.pack_propagate 在代码位", "\n            cell.pack_propagate(False)" in _srcv, True)
check("约定 无旧 grid_propagate 代码行", "\n            cell.grid_propagate" not in _srcv, True)
check("约定 键名双重兼容", 'app.get("exe_key") or app.get("key")' in _srcv, True)
check("约定 PhotoImage latin1 解码", 'decode("latin1")' in _srcv, True)
check("约定 光学归一接入管线", "optical_fit_rgba(rgba, w, h, int(px))" in _srcv, True)

# ---- 14) v1.6 纯逻辑: 长名截断/跑马灯 / 配色与滚动约定 ----
print("== 14) v1.6 fit_prefix / cycle_slice / 约定 ==")
fp = ns["fit_prefix"]
cs = ns["cycle_slice"]

def M10(_s):   # 每字符 10px 打桩（含省略号）
    return 10 * len(_s)

check("截断 短名原样", fp("Calc", 50, M10), "Calc")
check("截断 长名加省略号", fp("ABCDEFGH", 50, M10), "ABCD…")
check("截断 省略号占宽（55px 仍 4 字）", fp("ABCDEFGH", 55, M10), "ABCD…")
check("截断 极窄保底 1 字", fp("ABCDEFGH", 19, M10), "A…")
check("截断 空名安全", fp("", 50, M10), "")
check("截断 恰好等于预算不截", fp("ABCDE", 50, M10), "ABCDE")

check("滚动 短名原样", cs("Calc", 3, 50, M10), "Calc")
check("滚动 起点窗口", cs("ABCDEFGHIJKLM", 0, 50, M10), "ABCDE")
check("滚动 推进 2 步", cs("ABCDEFGHIJKLM", 2, 50, M10), "CDEFG")
check("滚动 尾段跨界（含分隔空格）", cs("ABCDEFGHIJKLM", 11, 50, M10), "LM   ")
check("滚动 环绕回起点", cs("ABCDEFGHIJKLM", 16, 50, M10), "ABCDE")
check("滚动 环绕越界取模", cs("ABCDEFGHIJKLM", 18, 50, M10), "CDEFG")
check("滚动 空名安全", cs("", 0, 50, M10), "")

# 配色 / 滚动接入约定（静态守护——v1.6）
check("约定 无旧硬截断 name[:14]", "text=name[:14]" not in _srcv, True)
check("约定 截断/滚动函数在代码位", ("def fit_prefix(" in _srcv and "def cycle_slice(" in _srcv), True)
check("约定 名称文字近黑（Mac 浅色对齐）", 'NMFG, SFG = "#141414", "#141414"' in _srcv, True)
check("约定 灰底 #8a8a8a 与 ICON_BG 同值", ('BG, FG, DIM, ACC, SEL = "#8a8a8a"' in _srcv and "(0x8a, 0x8a, 0x8a)" in _srcv), True)
check("约定 marquee 启动调度", "win.after(PICK_MARQUEE_MS, _marquee)" in _srcv, True)

# ---- 15) v1.7 纯逻辑: 网格方向导航 / GUID 结构 / Shell 通路约定 ----
print("== 15) v1.7 grid_move / GUID / 约定 ==")
gm = ns["grid_move"]

# 两行 5 项（3 列）: r0=0,1,2 / r1=3,4
check("网格 两行 ↓ 同列", gm(0, "DOWN", 3, 5), 3)
check("网格 两行 ↓ 同列（第二列）", gm(1, "DOWN", 3, 5), 4)
check("网格 两行 ↓ 末行该列空缺 → 最近列", gm(2, "DOWN", 3, 5), 4)
check("网格 两行 ↑ 同列", gm(4, "UP", 3, 5), 1)
check("网格 两行 ↑ 同列（第三列）", gm(3, "UP", 3, 5), 0)
check("网格 首行 ↑ 回绕末行同列", gm(0, "UP", 3, 5), 3)
check("网格 首行 ↑ 回绕末行（第二列）", gm(1, "UP", 3, 5), 4)
check("网格 末行 ↓ 回绕首行同列", gm(3, "DOWN", 3, 5), 0)
check("网格 末行 ↓ 回绕首行（第二列）", gm(4, "DOWN", 3, 5), 1)
check("网格 ← 行尾跨到上一行尾", gm(3, "LEFT", 3, 5), 2)
check("网格 ← 首项回绕", gm(0, "LEFT", 3, 5), 4)
check("网格 → 行尾跨到下一行首", gm(2, "RIGHT", 3, 5), 3)
check("网格 → 末项回绕", gm(4, "RIGHT", 3, 5), 0)

# 7 项 6 列: r0=0..5 / r1=6
check("网格 7/6 ↓ 到末行唯一格", gm(1, "DOWN", 6, 7), 6)
check("网格 7/6 首格 ↓ 末行同列", gm(0, "DOWN", 6, 7), 6)
check("网格 7/6 ↑ 回绕首行同列", gm(6, "UP", 6, 7), 0)
check("网格 7/6 末行再 ↓ 回绕", gm(6, "DOWN", 6, 7), 0)
check("网格 7/6 → 行尾跨行", gm(5, "RIGHT", 6, 7), 6)
check("网格 7/6 ← 行首跨行", gm(6, "LEFT", 6, 7), 5)

# 9 项 6 列（末行 3 格）: r1=6,7,8
check("网格 9/6 ↓ 最近列（3→8）", gm(3, "DOWN", 6, 9), 8)
check("网格 9/6 ↑ 同列（8→2）", gm(8, "UP", 6, 9), 2)
check("网格 9/6 ↓ 同列（1→7）", gm(1, "DOWN", 6, 9), 7)
check("网格 9/6 ↓ 回移（7→1）", gm(7, "DOWN", 6, 9), 1)
check("网格 9/6 首行 ↑ 回绕末行同列（2→8）", gm(2, "UP", 6, 9), 8)

# 单行 / 单列 / 边界: 退化线性 + 安全
check("网格 单行 ↓ 线性 +1", gm(0, "DOWN", 5, 5), 1)
check("网格 单行 ↑ 线性 -1（回绕）", gm(0, "UP", 5, 5), 4)
check("网格 单列 ↓ 线性 +1", gm(1, "DOWN", 1, 3), 2)
check("网格 单列 ↑ 线性 -1（回绕）", gm(0, "UP", 1, 3), 2)
check("网格 n=0 安全", gm(3, "DOWN", 3, 0), 0)
check("网格 n=1 恒 0", gm(0, "UP", 3, 1), 0)
check("网格 非法 action 原地", gm(2, "FOO", 3, 5), 2)
check("网格 cols 非法按单列", gm(1, "DOWN", None, 3), 2)
check("网格 sel 越界取模安全", gm(7, "DOWN", 3, 5), 4)

# GUID 结构解析（Shell AppsFolder 通路; 内存布局 = COM 标准: 前 3 段小端, Data4 原样）
gd = ns["_guid"]
g1 = gd("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
check("guid Data1（打印序解读）", g1.Data1, 0xBCC18B79)
check("guid Data2", g1.Data2, 0xBA16)
check("guid Data3", g1.Data3, 0x442F)
check("guid Data4 前四字节", list(g1.Data4[:4]), [0x80, 0xC4, 0x8A, 0x59])
check("guid Data4 后四字节", list(g1.Data4[4:]), [0xC3, 0x0C, 0x46, 0x3B])
check("guid 内存布局（Windows/COM 标准）", bytes(g1).hex(), "798bc1bc16ba2f4480c48a59c30c463b")
check("guid 大小写不敏感", gd("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3").Data1, 0x9F4C2855)

# 包应用路径判定（Shell 图标通路触发条件第二判据）
iup = ns["is_uwp_path"]
check("包应用路径 WindowsApps", iup(r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11_x64__8wekyb3d8bbwe\Calculator.exe"), True)
check("包应用路径 沉浸式控制面板（设置）", iup(r"C:\Windows\ImmersiveControlPanel\SystemSettings.exe"), True)
check("普通桌面应用路径不命中", iup(r"C:\Program Files\Google\Chrome\Application\chrome.exe"), False)
check("空路径安全", iup(None), False)
check("大小写不敏感", iup(r"c:\program files\windowsapps\x\app.exe"), True)

# 非 Win 安全返回（离线环境不打桩平台调用）
check("非Win aumid 安全空", ns["uwp_aumid_for"](None, 0), "")
check("非Win shell 图标安全", ns["_shell_icon_rgba"]("x!App"), (None, 0, 0))
check("非Win hbitmap 安全", ns["_hbitmap_to_rgba"](None), (None, 0, 0))

# 网格导航 / UWP 通路接入约定（静态守护——v1.7）
check("约定 grid_move 在代码位", "def grid_move(" in _srcv, True)
check("约定 _poll 走网格导航", '_move(a)' in _srcv, True)
check("约定 网格导航带 cols/项数", 'grid_move(cur["i"], a, lay["cols"], len(apps))' in _srcv, True)
check("约定 IPropertyStore IID", "886d8eeb-8cf2-4446-8d02-cdba1dbdcf99" in _srcv, True)
check("约定 PKEY_AppUserModel_ID", "9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3" in _srcv, True)
check("约定 IShellItemImageFactory IID", "bcc18b79-ba16-442f-80c4-8a59c30c463b" in _srcv, True)
check("约定 AppsFolder 前缀", "shell:AppsFolder" in _srcv, True)
check("约定 GetImage flags", "SIIGBF_ICONONLY | SIIGBF_SCALEUP" in _srcv, True)
check("约定 AUMID 进程回退", "GetApplicationUserModelId" in _srcv, True)
check("约定 uwp/包应用分流（_make_ppm_b64）", 'if app.get("uwp") or is_uwp_path(path):' in _srcv, True)
check("约定 包应用路径判定在代码位", "def is_uwp_path(" in _srcv, True)
check("约定 enum 产出 uwp 标记", '"uwp": uwp,' in _srcv, True)
check("约定 apps 透传 uwp", '"uwp": bool(w.get("uwp"))' in _srcv, True)
check("约定 后处理抽取 _finish_icon_ppm", "def _finish_icon_ppm(" in _srcv, True)
check("约定 v1.7 changelog", "v1.7 变更" in _srcv, True)
# 配色对齐 Mac 接入约定（静态守护——v1.8）
check("约定 v1.8 changelog", "v1.8 变更" in _srcv, True)
check("约定 选中边框系统蓝 #017aff", '"#017aff"' in _srcv, True)
check("约定 选中填充蓝灰 #6c84af", '"#6c84af"' in _srcv, True)

# ---- 16) v1.9 双底色变体: 选中格图标透明融合 ----
print("")
print("== 16) v1.9 双底色变体 / _finish_icon_ppm bg 参数化 ==")

# composite_rgba_on_bg 指定 SEL 底（选中格合成色 #6c84af）
check("合成SEL 全透明=蓝底", comp(bytes([0, 0, 0, 0]), 1, 1, bg=(0x6c, 0x84, 0xaf)),
      bytes([0x6c, 0x84, 0xaf]))
check("合成SEL 半透明白", comp(bytes([255, 255, 255, 128]), 1, 1, bg=(0x6c, 0x84, 0xaf)),
      bytes([182, 194, 215]))

# _finish_icon_ppm 端到端: 6×6（1px 透明边 + 4×4 红心）→ 16px 画布
import base64 as _b64
_fppm = ns["_finish_icon_ppm"]
_src6 = bytearray(6 * 6 * 4)
for _y in range(1, 5):
    for _x in range(1, 5):
        _o = (_y * 6 + _x) * 4
        _src6[_o] = 255
        _src6[_o + 3] = 255
_raw_g = _b64.b64decode(_fppm(bytes(_src6), 6, 6, 16, bg=(0x8a, 0x8a, 0x8a)))
_raw_s = _b64.b64decode(_fppm(bytes(_src6), 6, 6, 16, bg=ns["ICON_BG_SEL"]))
check("图标PPM P6 头 + 尺寸", _raw_s.startswith(b"P6\n16 16\n255\n"), True)
check("图标PPM 负载长度 16×16×3", len(_raw_s) - 13, 16 * 16 * 3)
_g_rgb = _raw_g[13:]
_s_rgb = _raw_s[13:]
check("图标PPM 灰底变体 角部=底色", tuple(_g_rgb[0:3]), (0x8a, 0x8a, 0x8a))
check("图标PPM 蓝底变体 角部=SEL", tuple(_s_rgb[0:3]), (0x6c, 0x84, 0xaf))
check("图标PPM 蓝底变体 中心=图标内容", tuple(_s_rgb[(8 * 16 + 8) * 3:(8 * 16 + 8) * 3 + 3]), (255, 0, 0))
check("图标PPM 蓝底变体 透明区(2,2)=底", tuple(_s_rgb[(2 * 16 + 2) * 3:(2 * 16 + 2) * 3 + 3]), (0x6c, 0x84, 0xaf))

# 接入约定（静态守护——v1.9）
check("约定 v1.9 changelog", "v1.9 变更" in _srcv, True)
check("约定 ICON_BG_SEL 常量", "ICON_BG_SEL = (0x6c, 0x84, 0xaf)" in _srcv, True)
check("约定 _finish_icon_ppm 底参数化", "def _finish_icon_ppm(rgba, w, h, px, bg=ICON_BG):" in _srcv, True)
check("约定 合成管线透传 bg", "composite_rgba_on_bg(rgba, w, h, bg)" in _srcv, True)
check("约定 图标缓存键带 bg 维度", '"sel" if sel else "bg"' in _srcv, True)
check("约定 选中变体随格构建", "_icon_photo_for(a, tk, icon_target, sel=True)" in _srcv, True)
check("约定 _paint 换底变体接入", 'cc["ilb"].configure(image=' in _srcv, True)

# ---- 17) v1.10 关闭当前应用（APP:CLOSE）----
print("")
print("== 17) v1.10 关闭当前应用 / close_poll 轮询 ==")

_poll = ns["close_poll"]

class _Clock:
    def __init__(self):
        self.t = 0.0
    def now(self):
        return self.t
    def sleep(self, s):
        self.t += s

# ① 窗口瞬间已销毁 → 立即成功
ck = _Clock()
_r = _poll(lambda: False, lambda: True, timeout=2.0, _sleep=ck.sleep, _clock=ck.now)
check("close_poll 窗口已销毁→成功", (_r[0], _r[1] < 0.5), (True, True))

# ② 存活但前台已切换 → 成功
ck = _Clock()
_r = _poll(lambda: True, lambda: False, timeout=2.0, _sleep=ck.sleep, _clock=ck.now)
check("close_poll 前台已切换→成功", (_r[0], _r[1] < 0.5), (True, True))

# ③ 延迟关闭（前 3 次存活, 第 4 次销毁）→ 成功且 waited ≈ 0.3s
_st = {"n": 0}
def _alive_n():
    _st["n"] += 1
    return _st["n"] <= 3
ck = _Clock()
_r = _poll(_alive_n, lambda: True, timeout=2.0, interval=0.1, _sleep=ck.sleep, _clock=ck.now)
check("close_poll 延迟关闭→成功", (_r[0], round(_r[1], 2)), (True, 0.3))

# ④ 持续存活 → 超时失败（waited ≥ timeout）
ck = _Clock()
_r = _poll(lambda: True, lambda: True, timeout=2.0, interval=0.1, _sleep=ck.sleep, _clock=ck.now)
check("close_poll 持续存活→超时失败", (_r[0], _r[1] >= 2.0), (False, True))

# ⑤ 分派与防抖（真实调用）
check("debounce APP:CLOSE=2.0", ns["debounce_for"]("APP:CLOSE"), 2.0)
check("debounce app:Close 大小写不敏感", ns["debounce_for"]("app:Close"), 2.0)
check("debounce 其余 APP 仍 0.35", ns["debounce_for"]("APP:PICK"), 0.35)
check("is_ext_action 放行 APP:CLOSE", ns["is_ext_action"]("APP:CLOSE"), True)
check("handle APP:CLOSE 非 Win 安全", ns["handle"]("APP:CLOSE"), "not-windows")

# ⑥ 源码约定静态守护（v1.10）
check("约定 v1.10 changelog", "v1.10 变更" in _srcv, True)
check("约定 VERSION 常量在场", 'VERSION = "1.' in _srcv, True)   # 具体版本由最新组断言
check("约定 do_app_close 在场", "def do_app_close():" in _srcv, True)
check("约定 host_child_hwnd 在场", "def host_child_hwnd(hwnd):" in _srcv, True)
check("约定 close_poll 在场", "def close_poll(" in _srcv, True)
check("约定 WM_CLOSE 常量", "WM_CLOSE = 0x0010" in _srcv, True)
check("约定 SMTO_ABORTIFHUNG 常量", "SMTO_ABORTIFHUNG = 0x0002" in _srcv, True)
check("约定 SendMessageTimeoutW 绑定", "_user32.SendMessageTimeoutW.argtypes" in _srcv, True)
check("约定 handle close 分派", 'if vl == "close":' in _srcv, True)
check("约定 shell 窗口拒绝保护", "拒绝关闭系统窗口" in _srcv, True)
check("约定 UWP 真身分流", "host_child_hwnd(fg)" in _srcv, True)
check("约定 优雅退出注释", "不用 TerminateProcess" in _srcv, True)
check("约定 无 TerminateProcess 调用", "TerminateProcess(" not in _srcv, True)
check("约定 CLOSE 强防抖注释", "强防抖防连关第二个应用" in _srcv, True)

# ---- 18) v1.11 鼠标模式（MouseGlide 滑行引擎 + mouse_control 分派）----
print("== 18) v1.11 鼠标模式 / 滑行引擎 ==")
MG = ns["MouseGlide"]

# 加速: 速度按 tick 离散积分（700px/s² @60Hz —— 与 lua doEvery 同构）
g = MG()
g.start("move", "RIGHT", 0.0)
npos, wheel = g.step(0.0, (100.0, 100.0), (0, 0, 1920, 1080))
check("单 tick 速度 = ACCEL/60", round(g.speed, 4), round(700 / 60, 4))
check("单 tick 位移 = v*dt", round(npos[0] - 100.0, 4), round((700 / 60) * (1 / 60), 4))
check("无滚动返回 None", wheel, None)

# 60 tick -> 速度 700
for i in range(1, 60):
    npos, _ = g.step(i / 60.0, npos, (0, 0, 999999, 1080))
check("60 tick 速度 = 700", round(g.speed, 1), 700.0)

# 速度上限（保活 0.5s 节奏, 对齐真实 T1 0.4s 包）
for i in range(300):
    t = 1.0 + i / 60.0
    if i % 30 == 0:
        g.start("move", "RIGHT", t)
    npos, _ = g.step(t, npos, (0, 0, 999999, 1080))
check("速度上限 1600", g.speed, 1600.0)

# 停止即停
g.stop("move", "RIGHT")
check("停止即停(无位移)", g.step(10.0, npos, (0, 0, 1920, 1080)), (None, None))
check("停止后速度归零", g.speed, 0.0)

# 看门狗 1.2s 无刷新自清（up 丢包兜底刹车）
g = MG()
g.start("move", "UP", 0.0)
check("看门狗窗口内活跃", g.busy(1.0), True)
check("看门狗超时自清", g.busy(1.3), False)

# 对向相消（零净位移）
g = MG()
g.start("move", "UP", 0.0)
g.start("move", "DOWN", 0.0)
npos, _ = g.step(0.0, (300.5, 300.5), (0, 0, 1920, 1080))
check("对向相消(零位移)", npos, (300.5, 300.5))

# 斜向不归一化（各轴分量=单轴值 -> 合成 √2 速, 对齐 lua）
g = MG()
g.start("move", "RIGHT", 0.0)
g.start("move", "DOWN", 0.0)
npos, _ = g.step(0.0, (100.0, 100.0), (0, 0, 5000, 5000))
check("斜向各轴=单轴速", round(npos[0] - 100.0, 4), round(700 / 60 / 60, 4))

# 边界夹取（max 排他 -2）
g = MG()
g.start("move", "RIGHT", 0.0)
npos = (1900.0, 500.0)
lk = 0.0
for i in range(400):
    t = i / 60.0
    if t - lk >= 0.5:
        g.start("move", "RIGHT", t)
        lk = t
    npos, _ = g.step(t, npos, (0, 0, 1920, 1080))
check("边界夹取 maxx-2", npos[0], 1918.0)

# 滚动速率（≈10 notch/s）与方向（下负上正）
g = MG()
g.start("scroll", "UP", 0.0)
tot = 0
for i in range(61):
    _, w = g.step(i / 60.0, (0, 0), (0, 0, 100, 100))
    tot += (w or 0)
check("1s 向上滚 8~11 notch", 8 <= tot <= 11, True)
g = MG()
g.start("scroll", "DOWN", 0.0)
tot = 0
for i in range(61):
    _, w = g.step(i / 60.0, (0, 0), (0, 0, 100, 100))
    tot += (w or 0)
check("1s 向下滚 = 负 notch", -11 <= tot <= -8, True)

# 保活刷新（重复 start 更新时间戳 -> 看门狗不误刹）
g = MG()
g.start("move", "LEFT", 0.0)
g.start("move", "LEFT", 1.0)
check("保活刷新不误触看门狗", g.busy(1.5), True)
check("保活过后仍过期(2.3)", g.busy(2.3), False)

# stop_all
g = MG()
g.start("move", "LEFT", 0.0)
g.start("scroll", "UP", 0.0)
g.stop_all()
check("stop_all 清空", (g.moves, g.scrolls, g.speed), ({}, {}, 0.0))

# mouse_control 分派矩阵（非 Win: 状态机运行, 平台执行受保护）
mc = ns["mouse_control"]
check("mc move down/up", (mc("MOUSE:MOVE:UP", "down"), mc("MOUSE:MOVE:UP", "up")),
      ("move UP on", "move UP off"))
check("mc scroll down/up", (mc("MOUSE:SCROLL:DOWN", "down"), mc("MOUSE:SCROLL:DOWN", "up")),
      ("scroll DOWN on", "scroll DOWN off"))
check("mc 非法方向", mc("MOUSE:MOVE:X", "down"), "ERR bad-dir MOUSE:MOVE:X")
check("mc 非法滚动", mc("MOUSE:SCROLL:X", "down"), "ERR bad-scroll MOUSE:SCROLL:X")
check("mc 未知动作", mc("MOUSE:FOO", "down"), "unknown mouse action: MOUSE:FOO")
check("mc lclick up 忽略", mc("MOUSE:LCLICK", "up"), "lclick ignored (up)")
check("mc rclick up 忽略", mc("MOUSE:RCLICK", "up"), "rclick ignored (up)")
check("mc 大小写宽容", mc("mouse:move:left", "down"), "move LEFT on")
ns["_glide"].stop_all()

# 源码约定静态守护（v1.11）
check("约定 v1.11 changelog", "v1.11 变更" in _srcv, True)
check("约定 VERSION 1.16", 'VERSION = "1.16"' in _srcv, True)
check("约定 MOUSE_ACCEL=700", "MOUSE_ACCEL = 700.0" in _srcv, True)
check("约定 MOUSE_MAX=1600", "MOUSE_MAX = 1600.0" in _srcv, True)
check("约定 MOUSE_STALE=1.2", "MOUSE_STALE = 1.2" in _srcv, True)
check("约定 MouseGlide 在场", "class MouseGlide:" in _srcv, True)
check("约定 mouse_control 在场", "def mouse_control(action, phase):" in _srcv, True)
check("约定 mouse_button_click 在场", "def mouse_button_click(button=" in _srcv, True)
check("约定 WHEEL 标志位", "0x0800" in _srcv, True)
check("约定 _send_wheel 在场", "def _send_wheel(notches):" in _srcv, True)
check("约定 glide 线程懒启动", "def _ensure_glide_thread():" in _srcv, True)
check("约定 看门狗注释", "保活断流即自停" in _srcv, True)
check("约定 键盘 INPUT 复用", "_user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))" in _srcv, True)

# ---- 19) v1.12 实测反馈修复轮（速度清零 / MODE / REPORT / 取证统计）----
import json as _json
import shutil as _shutil
import tempfile as _tempfile

print("== 19) v1.12 修复轮 ==")

# 19a. 速度事件驱动清零（核心修复: 旧版唯一清零点在 step, up 间隙 worker 不调 step
#      -> 速度跨按压累积到 1600 上限; 用户实测「特别快, 无法小距离移动」）
g = MG()
g.start("move", "RIGHT", 0.0)
npos = (100.0, 100.0)
for i in range(30):
    npos, _ = g.step(i / 60.0, npos, (0, 0, 5000, 5000))
check("v1.12 按住中速度>0", g.speed > 0.0, True)
g.stop("move", "RIGHT")
check("v1.12 stop 即清零", g.speed, 0.0)

# 离散按压流对照: 单步加速量 = accel*tick = 11.67; 修复后第二次按压从 0 重新起
g = MG()
npos = (100.0, 100.0)
g.start("move", "RIGHT", 0.0)
npos, _ = g.step(0.0, npos, (0, 0, 5000, 5000))
sp1 = g.speed
g.stop("move", "RIGHT")                 # up 到达（间隙内不调 step）
g.start("move", "RIGHT", 0.2)           # 下一次按压
g.step(0.2, npos, (0, 0, 5000, 5000))
check("v1.12 跨按压不累积(单步=11.67)", round(g.speed, 2), round(sp1, 2))
check("v1.12 对照旧版(旧版=23.33)", round(g.speed, 2) < 23.3, True)

# 看门狗扫除同样清零（UP 丢包兜底场景）
g = MG()
g.start("move", "DOWN", 0.0)
g.step(0.0, (0.0, 0.0), (0, 0, 5000, 5000))
check("v1.12 看门狗前 speed>0", g.speed > 0.0, True)
check("v1.12 看门狗超时自清", g.busy(1.3), False)
check("v1.12 扫除即清零", g.speed, 0.0)

# scroll_accum 随停清零
g = MG()
g.start("scroll", "UP", 0.0)
g.step(0.0, (0, 0), (0, 0, 100, 100))
g.stop("scroll", "UP")
check("v1.12 scroll stop 清 accum", g.scroll_accum, 0.0)

# 19b. MODE 提示分派（非 Win -> Tk 线程不可用, 优雅降级; 仅 DOWN）
check("v1.12 MODE ON(down)", mc("MOUSE:MODE:ON", "down"), "mode hud on (no-tk)")
check("v1.12 MODE OFF(down)", mc("MOUSE:MODE:OFF", "down"), "mode hud off (no-tk)")
check("v1.12 MODE up 忽略", mc("MOUSE:MODE:ON", "up"), "mode hint ignored (up)")

# 19c. REPORT 取证报告（重定向 STATE_DIR 到临时目录, 零副作用）
_tmpd = _tempfile.mkdtemp(prefix="wa-report-")
_old_state = ns["STATE_DIR"]
ns["STATE_DIR"] = _tmpd
try:
    r = mc("MOUSE:REPORT", "down")
    _rp = os.path.join(_tmpd, "mouse-report.json")
    rep = None
    if os.path.exists(_rp):
        rep = _json.load(open(_rp, encoding="utf-8"))
    check("v1.12 REPORT 写入", bool(r.startswith("report written:")) and rep is not None, True)
    if rep:
        check("v1.12 REPORT 版本", rep.get("version"), "1.16")
        check("v1.12 REPORT 计数为字典", isinstance(rep.get("counts"), dict), True)
        check("v1.12 REPORT last 为列表", isinstance(rep.get("last"), list), True)
        check("v1.12 REPORT click 计数在场", isinstance(rep.get("click_ok"), int) and isinstance(rep.get("click_fail"), int), True)
        check("v1.12 REPORT 探针键(仅Win)", ("sendinput_probe" in rep) or (not ns["IS_WIN"]), True)
    check("v1.12 REPORT up 忽略", mc("MOUSE:REPORT", "up"), "report ignored (up)")
finally:
    ns["STATE_DIR"] = _old_state
    _shutil.rmtree(_tmpd, ignore_errors=True)

# 19d. 取证统计（click ok/FAIL 分类与 ignored 不污染）
st = ns["_mouse_stat"]
_c0 = dict(st["counts"])
_k0, _f0 = st["click_ok"], st["click_fail"]
mc("MOUSE:LCLICK", "down")              # 非 Win -> "lclick FAIL"
check("v1.12 lclick FAIL 计数", (st["click_fail"], st["click_ok"]), (_f0 + 1, _k0))
mc("MOUSE:LCLICK", "up")                # ignored -> 不计 fail
check("v1.12 ignored 不污染 fail", st["click_fail"], _f0 + 1)
check("v1.12 counts 累计", st["counts"].get("MOUSE:LCLICK", 0) - _c0.get("MOUSE:LCLICK", 0), 2)
check("v1.12 last 非空", len(st["last"]) > 0, True)
ns["_glide"].stop_all()

# 19e. 源码约定静态守护（v1.12）
check("约定 v1.12 changelog", "v1.12 变更" in _srcv, True)
check("约定 速度事件清零注释", "事件驱动清零" in _srcv, True)
check("约定 _mouse_control_impl 改名", "def _mouse_control_impl(action, phase):" in _srcv, True)
check("约定 取证包裹签名保留", "def mouse_control(action, phase):" in _srcv, True)
check("约定 _hud_show/_hud_sound", ("def _hud_show(on):" in _srcv) and ("def _hud_sound(on):" in _srcv), True)
check("约定 _hud_open + pump 接入", ("def _hud_open(on):" in _srcv) and ('cmd.startswith("hud:")' in _srcv), True)
check("约定 _mouse_report_write", "def _mouse_report_write():" in _srcv, True)
check("约定 探针零位移", "零位移探针" in _srcv, True)
check("约定 _mouse_stat_bump", "def _mouse_stat_bump(action, result):" in _srcv, True)

# ---- 20) v1.13 ★ 跨模块 SendInput 类型冲突修复（元凶级 —— 治「OK 键完全无反应」）----
# 根因: ctypes.windll.user32 为进程级共享对象; win_receiver 与 win_actions 各定义
# 一套 INPUT 类并各设 SendInput.argtypes（后加载覆盖）→ 两套类不同一, win_actions
# 侧全部 SendInput 调用抛 TypeError 被 except 吞 → 鼠标点击/滚轮静默全灭。
# 修复: win_actions 结构定义上移通用层 + win_receiver 复用同一类对象。
print("== 20) v1.13 SendInput 类统一 ==")
_srcr = open(os.path.join(HERE, "win_receiver.py"), encoding="utf-8").read()

# 20a. 运行时核心断言: win_receiver 复用的 INPUT 类必须与其加载的 win_actions 同一对象
#      （ctypes 类型检查按"类对象"判型; 两套类不同一 = 13:39 全灭根因）
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_wr_ns = {"__file__": os.path.join(HERE, "win_receiver.py"), "__name__": "win_receiver_t20"}
exec(compile(_srcr, "win_receiver.py", "exec"), _wr_ns)
_wa2 = _wr_ns.get("win_actions")
if _wa2 is not None and hasattr(_wa2, "INPUT"):
    check("20a 类统一 INPUT", _wr_ns["INPUT"] is _wa2.INPUT, True)
    check("20a 类统一 KEYBDINPUT", _wr_ns["KEYBDINPUT"] is _wa2.KEYBDINPUT, True)
    check("20a 类统一 MOUSEINPUT", _wr_ns["MOUSEINPUT"] is _wa2.MOUSEINPUT, True)
    check("20a 类统一 HARDWAREINPUT", _wr_ns["HARDWAREINPUT"] is _wa2.HARDWAREINPUT, True)
    check("20a 类归属 win_actions", getattr(_wr_ns["INPUT"], "__module__", "?"), "win_actions")
    check("20a send_vk 可寻址", callable(_wr_ns.get("send_vk")), True)
else:                                    # win_actions 不可用 -> 兜底分支也须自洽
    check("20a 兜底分支 INPUT", isinstance(_wr_ns.get("INPUT"), type), True)
    check("20a 兜底分支字段", [f[0] for f in _wr_ns["INPUT"]._fields_], ["type", "u"])

# 20b. 兜底分支等价性: 强制 win_actions 不可用（sys.modules None 哨兵）——兜底类字段
#      必须与 win_actions 的类逐项一致（离线降级不失语义）
_save = sys.modules.get("win_actions")
sys.modules["win_actions"] = None        # import 命中 None -> ImportError -> 走兜底
_wr_ns2 = {"__file__": os.path.join(HERE, "win_receiver.py"), "__name__": "win_receiver_t20b"}
try:
    exec(compile(_srcr, "win_receiver.py", "exec"), _wr_ns2)
    if _wr_ns2.get("win_actions") is None:
        check("20b 兜底 INPUT 字段", [f[0] for f in _wr_ns2["INPUT"]._fields_], ["type", "u"])
        if _wa2 is not None:
            check("20b 兜底 mi 字段等价", [f[0] for f in _wr_ns2["MOUSEINPUT"]._fields_],
                  [f[0] for f in _wa2.MOUSEINPUT._fields_])
            check("20b 兜底 ki 字段等价", [f[0] for f in _wr_ns2["KEYBDINPUT"]._fields_],
                  [f[0] for f in _wa2.KEYBDINPUT._fields_])
            check("20b 兜底 hi 字段等价", [f[0] for f in _wr_ns2["HARDWAREINPUT"]._fields_],
                  [f[0] for f in _wa2.HARDWAREINPUT._fields_])
    else:
        check("20b 兜底分支触发(sys.modules 哨兵)", False, True)
finally:
    if _save is None:
        sys.modules.pop("win_actions", None)
    else:
        sys.modules["win_actions"] = _save

# 20c. win_actions 源码形态: 结构定义在通用层（先于 if IS_WIN:）+ 无块内重复
check("20c wa INPUT 先于 IS_WIN", 0 <= src.find("class INPUT(ctypes.Structure):") < src.find("if IS_WIN:"), True)
check("20c wa INPUT 唯一定义", src.count("class INPUT(ctypes.Structure):"), 1)
check("20c wa ULONG_PTR 唯一定义", src.count("ULONG_PTR = ctypes.c_ulonglong"), 1)
check("20c wa 无块内 INDENT 残留", "    class INPUT(ctypes.Structure):" not in src, True)
check("20c wa argtypes 引用同型", "POINTER(INPUT)" in src, True)

# 20d. win_receiver 源码形态: 复用分支 + 兜底分支 + 幂等声明
check("20d wr 复用分支", "INPUT = win_actions.INPUT" in _srcr, True)
check("20d wr 复用条件 hasattr", 'hasattr(win_actions, "INPUT")' in _srcr, True)
check("20d wr 兜底定义在场", _srcr.count("class INPUT(ctypes.Structure):"), 1)
check("20d wr 版本标识 v1.11", "remotehub-win receiver v1.11" in _srcr, True)

# 20e. 异常加固（v1.13: 同类问题今后直达 receiver.log, 不再静默）
check("20e mouse_click 落盘", "mouse_click error" in src, True)
check("20e mouse_button_click 落盘", "mouse_button_click error" in src, True)
check("20e _send_wheel 落盘", "_send_wheel error" in src, True)
check("20e _send_alt_tap 落盘", "_send_alt_tap error" in src, True)
check("20e alt_tap 无静默 pass", "_user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))\n        except Exception:\n            pass" not in src, True)

# 20f. REPORT 指纹 + changelog
check("20f input_class_module 字段", 'rep["input_class_module"]' in src, True)
check("20f wa changelog v1.13 历史保留", "v1.13 变更" in src, True)
check("20f wa VERSION 1.16", 'VERSION = "1.16"' in src, True)

# ---- 21) v1.14 电源键连击切换设备（HUD —— 配套 key_bridge v1.15 / T1 voice_fwd v2.7）----
# 协议: TARGET:SWITCH:ATV|MAC|WIN（仅 DOWN, 重发幂等）。win_receiver v1.10 起同 MOUSE:*
# 路由直呼 mouse_control; 非 Win 下 Tk 线程不可用 -> no-tk 优雅降级（真机显示「🎯 已切到 X」）。
print("== 21) v1.14 设备切换 HUD ==")

# 21a. 分派矩阵（非 Win: Tk 不可用 -> no-tk; 仅 DOWN 有效; 非法目标拒绝; 大小写宽容）
check("21a switch win(down)", mc("TARGET:SWITCH:WIN", "down"), "switch hud win (no-tk)")
check("21a switch mac(down)", mc("TARGET:SWITCH:MAC", "down"), "switch hud mac (no-tk)")
check("21a switch atv(down)", mc("TARGET:SWITCH:ATV", "down"), "switch hud atv (no-tk)")
check("21a up 忽略", mc("TARGET:SWITCH:ATV", "up"), "switch hud ignored (up)")
check("21a 非法目标拒绝", mc("TARGET:SWITCH:BOGUS", "down"), "ERR bad-target TARGET:SWITCH:BOGUS")
check("21a 大小写宽容", mc("target:switch:atv", "down"), "switch hud atv (no-tk)")
_hud_r = mc("TARGET:SWITCH:WIN", "down")
check("21a 命中专有分支(非 unknown 兜底)", _hud_r.startswith("switch hud"), True)

# 21b. 取证计数（同 MOUSE:* 一条管道, 计数可查）
check("21b 计数在场", ns["_mouse_stat"]["counts"].get("TARGET:SWITCH:WIN", 0) >= 1, True)

# 21c. win_actions v1.14 源码约定
check("21c SWITCH_NAMES 表", 'SWITCH_NAMES = {"atv": "ATV", "mac": "macOS", "win": "Windows"}' in _srcv, True)
check("21c _switch_hud_show", "def _switch_hud_show(name):" in _srcv, True)
check("21c _switch_hud_open", "def _switch_hud_open(name):" in _srcv, True)
check("21c _hud_open_text 抽取", "def _hud_open_text(txt):" in _srcv, True)
check("21c HUD 体系共用", ('def _hud_open(on):' in _srcv) and ('_hud_open_text("鼠标模式" if on else "键盘模式")' in _srcv), True)
check("21c pump swhud 接入", 'cmd.startswith("swhud:")' in _srcv, True)
check("21c 文案 🎯", '"🎯 已切到 "' in _srcv, True)
check("21c changelog v1.14", "v1.14 变更" in _srcv, True)
check("21c MOUSE:MODE 无回归", 'cmd.startswith("hud:")' in _srcv, True)

# 21d. win_receiver v1.10 源码形态
check("21d 路由双前缀", 'startswith(("MOUSE:", "TARGET:SWITCH:"))' in _srcr, True)
check("21d SWITCH 日志 tag", 'tag = "SWITCH" if action.startswith("TARGET:SWITCH:") else "MOUSE"' in _srcr, True)
check("21d 启动 banner v1.11", "remotehub-win receiver v1.11 starting" in _srcr, True)
check("21d selftest banner v1.11", "win_receiver v1.11 selftest" in _srcr, True)
check("21d changelog v1.10", "v1.10 变更" in _srcr, True)
check("21d 动作表列 TARGET:SWITCH", "TARGET:SWITCH:ATV|MAC|WIN" in _srcr, True)

# ---- 22) v1.15 FOCUS_INPUT 兜底点击（配套 T1 voice_fwd v2.8 / Mac lua v1.5）----
print("== 22) v1.15 兜底点击源码约定 ==")
check("22 changelog v1.15", "v1.15 变更" in _srcv, True)
check("22 click_at 注入参数", "def focus_input_strategy(uia, ctx, cache, click_at=None):" in _srcv, True)
check("22 兜底点击包装", "def _click_preserve_cursor(x, y):" in _srcv, True)
check("22 do_focus_input 接线", "click_at=_click_preserve_cursor" in _srcv, True)
check("22 NOEDIT+CLICK 结果串", "NOEDIT+CLICK@%d,%d" in _srcv, True)
check("22 app= 观测字段", "[winfix=%s app=%s]" in _srcv, True)
check("22 v1.14 changelog 历史保留", "v1.14 变更" in _srcv, True)

# ---- 23) v1.16 do_app_activate 观察日志（配套 10-14 排障盲点修复）----
print("== 23) v1.16 观察日志源码约定 ==")
check("23 changelog v1.16", "v1.16 变更" in _srcv, True)
check("23 activate 日志前缀", "app-activate" in _srcv, True)
check("23 activate front 记录", "front=%s" in _srcv, True)

print("")
print("== 结果: %d PASS / %d FAIL ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
