#!/usr/bin/env python3
"""t1_webui.py — T1 控制面板 v2.16 (2026-10-14)

v2.16（10-14）: 主页新增「设备在线状态」条 —— 消费 presence 心跳注册制（T1 :8790）:
   ATV / macOS / Windows 三设备状态点（绿=在线 / 灰=离线+最后在线秒数 / 黄=未知）,
   3s 轮询 GET /api/presence（读 state/presence.json; 缺失/过期/损坏 → available=false,
   前端降级「未知」, 永不阻塞页面其余功能）。配套 presence v1.0 心跳注册 + voice_fwd
   v2.9 / atvv_service v1.2 离线闸门（本页纯只读消费, 不参与判定）。

v2.15（10-13）: ATV 语音键解锁（配置驱动）—— 用户反馈「ATV 配置页语音键不可设、
   描述不对」。atv 份 #63 去锁定 + single 默认 __LAUNCH__:com.google.ios.youtube
   （保持原行为一键开 YouTube）+ note 重写; 配合 relay v0.12（语音键改走通用
   keymap 分派）网页改绑即生效（可改 home/menu/极空间等任意 ATV 动作）。
   mac/win 份 #63 保持锁定（按住说话, 语音链专用, 交 voice_fwd）。
v2.14（10-13）: 三份动作清单新增 TARGET:SWITCH「★ 电源（连击切设备）」—— 电源键 #116
   连击切换遥控目标（1 击=ATV / 2 击=macOS / 3 击=Windows; 免开网页）。执行端:
   Mac/Win 目标 = voice_fwd v2.7 TargetSwitcher（长按=关闭当前应用不变）;
   ATV 目标 = relay v0.11（1 击=电视电源不变 / 2 击=Mac / 3 击=Windows）。
   三份 keymap 默认 #116.single 已更新为该值; 下拉改回具体动作 = 立即退回普通键语义。
   ATV 下拉 __POWER__ 改标注「电源切换（立即，无连击）」以与新项区分。
v2.13（10-13）: mac/win 动作新增 MOUSE:TOGGLE「★ 鼠标模式开/关」—— 长按直播键切换
   鼠标模式（voice_fwd v2.5 模式层本地消化；模式内 方向=滑行移光标 / OK=点击(短左长右) /
   音量±=滚动 / 返回=退出）。keymap 生产绑定 = #41 long（两份 keymap 已同步）。
   接收端: Mac key_bridge v1.13 / Windows win_receiver v1.7+win_actions v1.11。
v2.12（10-12 21:3x）: 文案同步 —— 主页 win 卡片与描述移除已过时的「（链路待部署）」
   标注（Windows 转发链路 10-11 已上线并实机验收：语音键 = 按住说话、键位与 mac
   100% 对齐）。无功能变更。
v2.11（10-12 14:1x）: mac/win 动作新增 APP:CLOSE「★ 关闭当前应用」—— 长按电源键关闭
   当前前台应用（Mac app_switch v1.2 close: NSRunningApplication.terminate 优雅退出;
   Windows win_actions v1.10: WM_CLOSE 优雅关闭）。生产绑定 = #116 电源键 long ——
   单击仍为「打开 workbuddy」, 长按 0.6s 仅触发关闭（voice_fwd v2.3 状态机严格互斥,
   无双触发）。下拉文案特判（extLabel: APP:CLOSE →「关闭当前应用（长按电源键）」）。
v2.10（10-11 21:5x）: mac/win 动作新增 URL:<网址> / RUN:<命令> —— 遥控一键「打开网页 /
   执行命令」（Mac key_bridge v1.11: open / /bin/sh; win_actions v1.2: startfile / cmd /c）。
   下拉新增「打开网页…/执行命令…」自定义输入（prompt → URL:<值>/RUN:<值>, 复用
   「打开应用…」同款的选项内联模式; 页面保存时哨兵防残留）。校验: mac/win 前缀放行 +
   禁空格 + 值 ≤500 字符; ATV 拒绝。值不含空格 = UDP 协议按空白分词的硬约束
   （含空格命令请写成脚本文件后填其路径）。仅 DOWN 触发（UP 忽略, 对齐 APP:/CLICK 语义）。
v2.9（10-11 17:2x）: /keymap 初始 tab 跟随「当前激活目标」——页面加载时先取
   /api/state，如当前目标=mac 则直接高亮 macOS 配置页（此前硬编码 ATV）。
   取不到/异常时回退 atv（不影响其余功能）。背景: 用户反馈"进入按键配置页时，
   高亮的应该是当前激活的设备，而不是总是 ATV"。
v2.8（10-10 21:1x）: mac/win 动作新增 PAGEUP「★ 上一页」/ PAGEDOWN「★ 下一页」——
   翻页（看长回复/网页滚动）; 由 Mac key_bridge v1.10 注入键码 116/121。
   提示: SPACE（空格式滚动）在焦点不在输入框时本就能滚屏, 翻页键为更明确语义。
v2.7（10-10 20:5x）: 配置回写加固 —— POST /api/keymap 增加「配置指纹」校验：
   GET 返回 rev（当前配置语义级 sha256 前 12 位）；页面保存时回传加载时的 rev；
   服务端比对不符（或缺失）→ 409 拒绝并提示“请刷新页面后重试”。
   目的: 杜绝 18:52 类「旧页面用旧逻辑回写覆盖新字段」事故（部署新 UI 后
   未刷新的页面再保存时会被安全拦截，而不是静默覆盖）。保存成功响应返回新 rev
   （前端更新，连续保存不误报）；bot/终端写入需先 GET 取 rev 再 POST。
v2.6（10-10 20:3x）: mac/win 动作新增 CLICK「★ 点击（激活当前焦点元素）」——
   对键盘焦点元素执行 AXPress（Mac key_bridge v1.9 经 Hammerspoon 执行;
   元素不支持时坐标点击兜底）。背景: WorkBuddy 等 Electron 应用里 TAB 可达
   元素（任务列表条目等）不响应合成 ENTER（组件未实现键盘激活），但 AXPress
   与真实点击等效（实测往返双验证）。生产场景: 音量-=TAB 切到任务 → CLICK
   点击它（建议绑 OK 长按 / 用户自选）。校验: KB_ACTIONS += CLICK。
v2.5（10-10 19:3x）: mac/win 动作新增 FOCUS_INPUT「★ 跳转输入框」——
   遥控器单按触发 Mac key_bridge v1.8 的焦点动作（经 Hammerspoon AX 层）:
   修复前台窗口焦点 + 聚焦窗口内首个可编辑元素（聊天输入框/编辑器等）。
   背景: “切换后窗口有时不获得焦点、没法输入到输入框”（Chromium 系应用 AX 树
   不可靠, 走坐标探测——机制详见 key_bridge v1.8 与 remotehub_focus.lua）。
   校验: 与键盘动作同白名单（KB_ACTIONS += FOCUS_INPUT）。
v2.4（10-10 18:4x）: 长按列新增「⟳ 按住连发」选项 —— 把「连发（repeat）」能力从
  仅 API 可写变为 UI 可自助配置（此前写死在个别键上）; 选它 = 按住时单击动作连续
  重复（如 BACKSPACE 单按删一个 / 按住连续删），与「长按动作」在同一列二选一;
  连发键的长按列不再禁用（显示该项）; 保存时 repeat 由长按列派生; 服务端接受哨兵
  __REPEAT__（等价 repeat=true，并清 long/double 互斥项）。
v2.3（10-10 17:5x）: ①mac/win 长按（long）解禁 —— 下拉可选（voice_fwd v2.3 执行:
  按住满 0.6s 触发 long / 未满松开补发 single）; ②动作新增 APP:PICK（应用选择器,
  主页长按生产绑定）与「打开应用…」自定义输入（前端 prompt → APP:<名>）; ③双击仍不可用。
v2.2（10-10 16:5x）: mac/win 下拉新增 APP:CYCLE（全应用轮询 —— 连续按沿冻结快照
  环状推进, 主页键 #102 生产绑定; 由 app_switch v1.1 cycle 实现）。
v2.1（10-10 15:3x）: mac/win 新增「应用动作」选项 —— APP:TOGGLE（最近两应用间跳）/
  APP:NEXT（循环下一个）/ APP:<名称>（打开/切换到该应用）。由 Mac key_bridge v1.5
  经 app_switch 工具执行（NSWorkspace 激活, 非键盘注入, 无需 TCC）。校验=前缀放行
  （含空格非法——会破坏 UDP 协议解析）。背景: 「组合键合成」用户态不可行(Task#30),
  应用切换走「直接激活」语义。

服务两个页面（端口 8765，局域网内任意设备浏览器可开）:
  GET  /                    三按钮主页 —— 遥控器行为目标切换（ATV / Mac / Windows）
  GET  /keymap              三 tab 按键配置页（ATV / Mac / Windows 各一份 13 键配置）
API:
  GET  /api/state           当前目标
  GET  /api/presence        设备在线快照（presence.json 只读; 降级安全）
  GET  /api/keymap          当前 v2 配置 + 各目标动作清单
  POST /api/voice_target    {"target": "atv|mac|win"}  写 voice_target 状态文件
  POST /api/keymap          {"target","hold_threshold","double_window","keys"}
                            校验后原子写入 keymap.json 对应目标份（relay/voice_fwd 下一次按键热重载）
  POST /api/keymap/reset    {"target": "atv|mac|win"}  恢复该目标默认；不带 target=全部恢复

配置 v2 结构: {version:2, hold_threshold, double_window,
              targets: {atv|mac|win: {keys: {"code": {label, single, double, long, repeat, locked?, note?}}}}}
  - atv 份动作 = pyatv 动作 + 特例(__POWER__/__LAUNCH__:.../TARGET:SWITCH)（小写）
  - mac/win 份动作 = 键盘动作（大写: ENTER/ESC/UP/DOWN/LEFT/RIGHT/SPACE/TAB/BACKSPACE/
    PAGEUP/PAGEDOWN/FOCUS_INPUT/CLICK/MOUSE:TOGGLE/TARGET:SWITCH）
    + 应用动作（APP:TOGGLE / APP:NEXT / APP:CYCLE / APP:PICK / APP:CLOSE / APP:<名称>, 见上说明）
    + 一次触发动作（URL:<网址> / RUN:<命令>, v2.10; 仅 DOWN 触发）
    · 长按自 v2.3 支持（voice_fwd v2.3 执行）; v2.4 长按列可选「⟳ 按住连发」（=repeat 连发）;
      双击仍不支持（置空）; 语音键 63: atv 份可配置（v2.15 解锁, 默认「打开 YouTube」）,
      mac/win 份锁定（按住说话语音输入, 不参与键位映射）
状态交换均为文件（voice_target / keymap.json），读端为 relay_min.py 与 voice_fwd.py，
本服务崩溃不影响遥控/语音链路；反之亦然。
安全：局域网内无鉴权（与现有链路一致），勿暴露到公网。
运行: systemctl restart t1-webui（或 /usr/bin/python3 -u /root/remote-hub/t1_webui.py）
"""
import hashlib
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "keymap.json")
CFG_DEFAULT_PATH = os.path.join(HERE, "keymap.default.json")
VOICE_TARGET_PATH = os.path.join(HERE, "voice_target")
PORT = 8765
TARGETS = ("atv", "mac", "win")

# ---------- 动作清单（下拉 & 服务端校验；与 relay_min.py / voice_fwd.py 分派一致） ----------
ATV_STANDARD = ["up", "down", "left", "right", "select", "menu", "home", "home_hold",
                "volume_up", "volume_down", "skip_forward", "skip_backward"]
ATV_SPECIAL = ["__PLAY_PAUSE__", "__APP_SWITCH__", "__POWER__", "TARGET:SWITCH"]
LAUNCH_PREFIX = "__LAUNCH__:"
KB_ACTIONS = ["ENTER", "ESC", "UP", "DOWN", "LEFT", "RIGHT", "SPACE", "TAB", "BACKSPACE",
              "PAGEUP", "PAGEDOWN", "FOCUS_INPUT", "CLICK", "MOUSE:TOGGLE", "TARGET:SWITCH"]
# v2.5: +FOCUS_INPUT=跳输入框（key_bridge v1.8）; v2.6: +CLICK=点击焦点元素（v1.9）;
# v2.8: +PAGEUP/PAGEDOWN=翻页（key_bridge v1.10）; v2.13: +MOUSE:TOGGLE=鼠标模式开关
# （voice_fwd v2.5 模式层本地消化——不转发; 生产绑定 #41 长按）;
# v2.14: +TARGET:SWITCH=电源连击切换设备（voice_fwd v2.7 / relay v0.11 本地消化——
# 仅绑 #116 单击有意义; 绑其它键时被明确忽略并记日志）
# v2.1: mac/win 的「应用动作」前缀 —— 由 Mac key_bridge v1.5 经 app_switch 工具执行
# （APP:TOGGLE=最近两应用间跳; APP:NEXT=名称序循环; APP:CYCLE=全应用轮询〔主页键生产绑定〕;
#   APP:<名称|bundleID>=打开/切换到该应用）
APP_PREFIX = "APP:"
# v2.10: mac/win 的「一次触发」扩展动作前缀 —— URL:<网址> 打开默认浏览器 /
# RUN:<命令> 执行命令（Mac key_bridge v1.11 / win_actions v1.2 执行; 仅 DOWN 触发）。
# 值不含空格 = UDP 协议按空白分词的硬约束；值长上限 EXT_VALUE_MAX（防超长包体）。
URL_PREFIX = "URL:"
RUN_PREFIX = "RUN:"
EXT_VALUE_MAX = 500
# v2.4: 长按列哨兵 ——「⟳ 按住连发」。语义 = repeat=True（按住时单击动作连续重复，
# 0.12s 节流），与长按动作互斥（同一列二选一）。前端保存时转译为 repeat 布尔，
# 哨兵本身不落盘；服务端兜底接受。
REPEAT_SENTINEL = "__REPEAT__"
REPEAT_OPT = [REPEAT_SENTINEL, "⟳ 按住连发（连续重复）"]

ATV_CHOICES = [
    ["", "— 无 —"],
    ["up", "方向上"], ["down", "方向下"], ["left", "方向左"], ["right", "方向右"],
    ["select", "确认"],
    ["menu", "返回（menu）"],
    ["home", "主屏"],
    ["home_hold", "控制中心（长按主页效果）"],
    ["__PLAY_PAUSE__", "播放/暂停"],
    ["__APP_SWITCH__", "应用切换器"],
    ["volume_up", "音量+"], ["volume_down", "音量-"],
    ["skip_forward", "快进"], ["skip_backward", "快退"],
    ["__POWER__", "电源切换（立即，无连击）"],
    ["TARGET:SWITCH", "★ 电源（连击切设备：1 击=电视电源 · 2 击=Mac · 3 击=Windows）"],
    [LAUNCH_PREFIX + "com.zentraedi.zspaceTV", "打开极空间"],
    [LAUNCH_PREFIX + "com.google.ios.youtube", "打开 YouTube"],
]
CUSTOM_APP = "__CUSTOM_APP__"   # v2.3: 前端「打开应用…」自定义输入占位值（不落盘, 前端转成 APP:<名>）
CUSTOM_URL = "__CUSTOM_URL__"   # v2.10: 「打开网页…」占位值（前端转成 URL:<网址>）
CUSTOM_RUN = "__CUSTOM_RUN__"   # v2.10: 「执行命令…」占位值（前端转成 RUN:<命令>）
KB_CHOICES = [
    ["", "— 无 —"],
    ["ENTER", "回车"], ["ESC", "Esc（打断）"],
    ["UP", "方向上"], ["DOWN", "方向下"], ["LEFT", "方向左"], ["RIGHT", "方向右"],
    ["SPACE", "空格"], ["TAB", "Tab"], ["BACKSPACE", "退格"],
    ["FOCUS_INPUT", "★ 跳转输入框（聚焦输入框 · 修复失焦）"],
    ["CLICK", "★ 点击（激活当前焦点元素 · 任务/列表项）"],
    ["MOUSE:TOGGLE", "★ 鼠标模式开/关（长按直播; 方向=移光标 · OK=点击 · 音量=滚动）"],
    ["TARGET:SWITCH", "★ 电源（连击切设备：1 击=ATV · 2 击=Mac · 3 击=Windows; 长按=关闭应用）"],
    ["PAGEUP", "★ 上一页（PageUp）"],
    ["PAGEDOWN", "★ 下一页（PageDown）"],
    ["APP:CYCLE", "★ 切换应用 · 全部轮询（连按依次遍历）"],
    ["APP:TOGGLE", "★ 切换应用 · 最近两个间跳（≈⌘Tab）"],
    ["APP:NEXT", "★ 切换应用 · 循环下一个（名称序）"],
    ["APP:PICK", "★ 应用选择器（唤出列表 · 左右选 · OK 打开）"],
    ["APP:CLOSE", "★ 关闭当前应用（长按电源键）"],
    [CUSTOM_APP, "打开应用…（自定义输入）"],
    [CUSTOM_URL, "打开网页…（自定义输入）"],
    [CUSTOM_RUN, "执行命令…（自定义输入）"],
    ["APP:微信", "打开/切换到 微信"],
    ["APP:飞书", "打开/切换到 飞书"],
    ["APP:Obsidian", "打开/切换到 Obsidian"],
    ["APP:Safari", "打开/切换到 Safari"],
]
CHOICES_BY_TARGET = {"atv": ATV_CHOICES, "mac": KB_CHOICES, "win": KB_CHOICES}

KEY_ORDER = ["116", "63", "102", "158", "103", "108", "105", "106", "28", "115", "114", "41", "127"]


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


# ---------- 状态文件 ----------
def read_target():
    try:
        with open(VOICE_TARGET_PATH) as f:
            t = f.read().strip()
        return t if t in TARGETS else "mac"
    except Exception:  # noqa: BLE001
        return "mac"


def read_presence_snapshot():
    """v2.16: 设备在线快照（主页状态条数据源）。
    降级安全: presence 模块不可用 / 快照缺失 / 过期 / 损坏 → available=False（页面显示未知）。"""
    try:
        import presence as _p
        snap = _p.read_state(os.path.join(HERE, "state", "presence.json"))
    except Exception as e:  # noqa: BLE001
        return {"available": False, "devices": {}, "error": repr(e)}
    if not snap:
        return {"available": False, "devices": {}}
    now = time.time()
    devs = {}
    for role in ("atv", "mac", "win"):      # 固定展示三设备
        d = (snap.get("devices") or {}).get(role) or {}
        if not d:
            continue
        devs[role] = {"state": d.get("state") or "unknown", "ip": d.get("ip"),
                      "age": round(now - float(d.get("last_seen") or 0), 1)}
    return {"available": True, "devices": devs}


def write_target(t):
    atomic_write_text(VOICE_TARGET_PATH, t + "\n")


def atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def read_json_file(path):
    with open(path) as f:
        return json.load(f)


def normalize_cfg(cfg):
    """v2 (targets) 直用；v1 (单份 keys) 视为 atv"""
    if isinstance(cfg.get("targets"), dict):
        return cfg
    if isinstance(cfg.get("keys"), dict):
        return {"version": 2,
                "hold_threshold": cfg.get("hold_threshold", 0.6),
                "double_window": cfg.get("double_window", 0.3),
                "targets": {"atv": {"keys": cfg["keys"]}, "mac": {"keys": {}}, "win": {"keys": {}}}}
    raise ValueError("keys/targets 缺失")


def read_cfg_safe():
    for p in (CFG_PATH, CFG_DEFAULT_PATH):
        try:
            return normalize_cfg(read_json_file(p))
        except Exception:  # noqa: BLE001
            continue
    return {"version": 2, "hold_threshold": 0.6, "double_window": 0.3,
            "targets": {t: {"keys": {}} for t in TARGETS}}


def read_default_cfg():
    return normalize_cfg(read_json_file(CFG_DEFAULT_PATH))


def calc_rev():
    """v2.7: 配置指纹（防旧页面回写）——当前配置的语义级 sha256 前 12 位。
    与文件格式无关（规范化序列化）；内容不变则 rev 不变，内容一变 rev 必变。"""
    blob = json.dumps(read_cfg_safe(), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


# ---------- 配置校验 ----------
def valid_action_for(target, a):
    if a in (None, ""):
        return True
    if target == "atv":
        if a in ATV_STANDARD or a in ATV_SPECIAL:
            return True
        return a.startswith(LAUNCH_PREFIX) and len(a) > len(LAUNCH_PREFIX)
    # mac/win: 键盘动作 + APP: 应用动作 + URL:/RUN: 一次触发动作
    # （前缀放行；含空格非法——会破坏 UDP 协议解析；URL/RUN 值长 ≤EXT_VALUE_MAX）
    if a.startswith(APP_PREFIX):
        return len(a) > len(APP_PREFIX) and " " not in a
    if a.startswith((URL_PREFIX, RUN_PREFIX)):
        v = a[4:]
        return len(v) > 0 and " " not in v and len(v) <= EXT_VALUE_MAX
    return a in KB_ACTIONS


def norm_action_for(target, a):
    if a in (None, ""):
        return None
    if not valid_action_for(target, a):
        raise ValueError(f"非法动作({target}): {a!r}")
    return a


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def validate_keys_for(raw_keys, dkeys, target, cur_keys=None):
    """以 default 该目标键表为骨架（locked/label 来源）；逐键校验。
    字段取值优先序: 本次提交 > 当前配置 > 默认（未提及的字段保留当前值）。
    mac/win: 单击/长按; 双击置空。v2.4: long 接受哨兵 __REPEAT__（长按列「按住连发」）
    → repeat=True、long=None; repeat 与 long/double 互斥（repeat 优先，清空对方）。"""
    cur_keys = cur_keys or {}
    out = {}
    for code, dk in dkeys.items():
        base = dict(dk)
        if dk.get("locked"):
            out[code] = base
            continue
        rk = raw_keys.get(code) or {}
        ck = cur_keys.get(code) or {}

        def pick(f):
            return norm_action_for(target, rk.get(f, ck.get(f, dk.get(f))))

        base["single"] = pick("single")
        base["double"] = pick("double") if target == "atv" else None   # 双击: mac/win 不支持
        lraw = rk.get("long", ck.get("long", dk.get("long")))
        long_repeat = (lraw == REPEAT_SENTINEL)          # v2.4: 长按列选「⟳ 按住连发」
        base["long"] = None if long_repeat else norm_action_for(target, lraw)
        repeat = long_repeat or bool(rk.get("repeat", ck.get("repeat", dk.get("repeat", False))))
        base["repeat"] = repeat
        if repeat:
            # 连发与 长按/双击 互斥
            base["double"] = None
            base["long"] = None
        out[code] = base
    return out


def validate_and_normalize(raw, target, cur_cfg, default_cfg):
    """输入 = 前端收集的 {hold_threshold, double_window, keys:{code:{single,double,long}}}
    输出 = 完整 v2 配置（只替换 target 份；其余目标保留当前值）。"""
    if target not in TARGETS:
        raise ValueError("target 必须是 atv/mac/win")
    if not isinstance(raw, dict):
        raise ValueError("body 必须是 JSON 对象")
    raw_keys = raw.get("keys", {})
    if not isinstance(raw_keys, dict):
        raise ValueError("keys 必须是对象")

    d_targets = default_cfg.get("targets", {})
    c_targets = cur_cfg.get("targets", {})
    dkeys = d_targets.get(target, {}).get("keys", {})
    if not dkeys:
        raise ValueError(f"默认配置缺少 targets.{target}.keys")

    out_targets = {}
    for t in TARGETS:
        if t == target:
            cur_keys = c_targets.get(t, {}).get("keys", {}) or {}
            out_targets[t] = {"keys": validate_keys_for(raw_keys, dkeys, t, cur_keys)}
        else:
            ck = c_targets.get(t, {}).get("keys")
            if isinstance(ck, dict) and ck:
                out_targets[t] = {"keys": ck}
            else:
                out_targets[t] = {"keys": d_targets.get(t, {}).get("keys", {})}

    try:
        ht = clamp(float(raw.get("hold_threshold", cur_cfg.get("hold_threshold", 0.6))), 0.3, 2.0)
        dw = clamp(float(raw.get("double_window", cur_cfg.get("double_window", 0.3))), 0.15, 0.6)
    except (TypeError, ValueError):
        raise ValueError("hold_threshold / double_window 必须是数字") from None
    return {"version": 2, "hold_threshold": round(ht, 2), "double_window": round(dw, 2),
            "targets": out_targets}


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "T1Ctrl/2.0"

    # ---- helpers ----
    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > 131072:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def log_message(self, fmt, *args):
        log("http %s %s" % (self.address_string(), fmt % args))

    # ---- GET ----
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, PAGE_HOME, "text/html; charset=utf-8")
        elif path == "/keymap":
            self._send(200, PAGE_KEYMAP, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(200, {"voice_target": read_target()})
        elif path == "/api/presence":
            self._json(200, read_presence_snapshot())
        elif path == "/api/keymap":
            self._json(200, {"cfg": read_cfg_safe(), "rev": calc_rev(), "choices": CHOICES_BY_TARGET,
                             "order": KEY_ORDER, "repeat_opt": REPEAT_OPT})
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    # ---- POST ----
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._read_body() or {}
        if path == "/api/voice_target":
            t = body.get("target")
            if t not in TARGETS:
                return self._json(400, {"ok": False, "error": "target 必须是 atv/mac/win"})
            try:
                write_target(t)
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"ok": False, "error": f"写入失败: {e!r}"})
            log(f"voice_target -> {t}")
            return self._json(200, {"ok": True, "voice_target": t})
        if path == "/api/keymap":
            # v2.7: 配置指纹校验 —— 拒绝过期快照回写（防 18:52 旧页面覆盖新字段类事故）
            cur_rev = calc_rev()
            if body.get("rev") != cur_rev:
                log(f"keymap.json 拒绝写入（配置指纹不符: 送来={body.get('rev')!r} 当前={cur_rev!r}）")
                return self._json(409, {"ok": False, "error": "stale",
                                        "msg": "配置已变化（可能在其他页面/终端操作过），请刷新页面后重试",
                                        "rev": cur_rev})
            try:
                target = body.get("target", "atv")
                default_cfg = read_default_cfg()
                cfg = validate_and_normalize(body, target, read_cfg_safe(), default_cfg)
                atomic_write_text(CFG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
            except Exception as e:  # noqa: BLE001
                return self._json(400, {"ok": False, "error": str(e)})
            log(f"keymap.json 已更新（{target} 份; relay/voice_fwd 下一次按键热重载）")
            return self._json(200, {"ok": True, "rev": calc_rev()})
        if path == "/api/keymap/reset":
            target = body.get("target")
            try:
                default_cfg = read_default_cfg()
                if target in TARGETS:
                    out = json.loads(json.dumps(read_cfg_safe()))     # 深拷贝当前
                    out["targets"][target] = default_cfg["targets"][target]
                elif target is None:
                    out = default_cfg
                else:
                    return self._json(400, {"ok": False, "error": "target 必须是 atv/mac/win"})
                atomic_write_text(CFG_PATH, json.dumps(out, ensure_ascii=False, indent=2) + "\n")
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"ok": False, "error": str(e)})
            log(f"keymap.json 已恢复默认（{'全部' if target is None else target + ' 份'}）")
            return self._json(200, {"ok": True})
        self._send(404, "not found", "text/plain; charset=utf-8")


# ---------- 页面 ----------
CSS = """
:root { --bg:#0f1114; --panel:#181c21; --panel2:#20262e; --fg:#e8ecf1; --dim:#8b949e;
        --acc:#3b82f6; --ok:#22c55e; --warn:#f59e0b; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body { margin:0; padding:20px 16px 96px; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, "PingFang SC", "Noto Sans SC", "Segoe UI", sans-serif; }
h1 { font-size:22px; margin:4px 0 2px; }
.sub { color:var(--dim); font-size:13px; margin:0 0 14px; }
.cards { display:flex; flex-direction:column; gap:12px; }
.card { text-align:left; background:var(--panel); color:var(--fg); border:1.5px solid #2a3038;
  border-radius:14px; padding:18px 16px; font-size:16px; cursor:pointer; transition:.15s; width:100%; }
.card b { display:block; font-size:18px; margin-bottom:4px; }
.card span { color:var(--dim); font-size:13px; }
.card.active { border-color:var(--acc); background:#16233a; }
.card.active b::after { content:" ● 当前"; color:var(--acc); font-size:12px; font-weight:600; margin-left:8px; }
.state { color:var(--dim); font-size:13px; margin-top:16px; min-height:20px; }
.devbar { display:flex; gap:10px 16px; flex-wrap:wrap; align-items:center; margin:16px 0 0;
  padding:11px 14px; background:var(--panel); border-radius:12px; font-size:13px; color:var(--dim); }
.devbar .dev { display:inline-flex; align-items:center; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; background:#6b7280; }
.dot.online { background:var(--ok); box-shadow:0 0 6px rgba(34,197,94,.45); }
.dot.offline { background:#6b7280; }
.dot.unknown { background:var(--warn); }
.foot { position:fixed; left:16px; right:16px; bottom:16px; }
.foot a { display:block; text-align:center; background:var(--panel2); color:var(--fg); padding:14px;
  border-radius:12px; text-decoration:none; font-size:15px; }
.tabs { display:flex; gap:8px; margin-bottom:12px; }
.tab { flex:1; text-align:center; padding:12px 6px; background:var(--panel); border:1.5px solid #2a3038;
  border-radius:12px; color:var(--fg); font-size:14px; cursor:pointer; transition:.15s; }
.tab.active { border-color:var(--acc); background:#16233a; font-weight:600; }
.row { background:var(--panel); border-radius:14px; padding:12px 14px; margin-bottom:10px; }
.row.locked { opacity:.78; }
.kname { font-size:15px; font-weight:600; margin-bottom:8px; }
.kname small { color:var(--dim); font-weight:400; margin-left:6px; font-size:12px; }
.cells { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }
.cells label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--dim); }
.cells select { width:100%; background:var(--panel2); color:var(--fg); border:1px solid #2a3038;
  border-radius:8px; padding:9px 6px; font-size:13px; appearance:none; }
.cells select:disabled { opacity:.45; }
.note { color:var(--warn); font-size:12px; margin-top:8px; }
.bar { position:fixed; left:16px; right:16px; bottom:16px; display:flex; gap:10px; }
.btn { flex:1; border:0; border-radius:12px; padding:14px; font-size:15px; background:var(--panel2);
  color:var(--fg); cursor:pointer; text-align:center; text-decoration:none; }
.btn.primary { background:var(--acc); color:#fff; font-weight:600; }
.toast { position:fixed; left:50%; bottom:88px; transform:translateX(-50%) translateY(10px);
  background:rgba(30,35,42,.96); border:1px solid #2a3038; color:var(--fg); padding:10px 18px;
  border-radius:10px; font-size:14px; opacity:0; pointer-events:none; transition:.2s; z-index:9; }
.toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
"""

PAGE_HOME = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>T1 控制台</title>
<style>%%CSS%%</style>
</head>
<body>
<h1>T1 控制台</h1>
<p class="sub">遥控器行为目标 · 点一下即切换（语音键 + 按键都按该目标生效）</p>
<div class="cards">
  <button class="card" data-t="atv"><b>ATV</b><span>语音键 = 开 YouTube · 按键 = 控制 Apple TV</span></button>
  <button class="card" data-t="mac"><b>macOS</b><span>语音键 = 语音输入 · OK=回车 · 返回=Esc · 方向=方向键</span></button>
  <button class="card" data-t="win"><b>Windows</b><span>语音键 = 语音输入 · 键位同 Mac</span></button>
</div>
<p class="state" id="state">加载中…</p>
<div class="devbar" id="devbar"><span class="dev">设备状态加载中…</span></div>
<div class="foot"><a href="/keymap">按键配置（三目标）</a></div>
<div class="toast" id="toast"></div>
<script>
const NAMES = { atv:'ATV', mac:'macOS', win:'Windows' };
const DESC = {
  atv:'语音键 = 一键开 YouTube · 按键 = 控制 Apple TV',
  mac:'语音键 = 转发 Mac 语音输入 · OK=回车 · 返回=Esc · 方向=方向键',
  win:'语音键 = 转发 Windows 语音输入 · 键位同 Mac' };
let toastTimer;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 1800);
}
async function refresh() {
  try {
    const s = await (await fetch('/api/state')).json();
    document.querySelectorAll('.card').forEach(el => el.classList.toggle('active', el.dataset.t === s.voice_target));
    document.getElementById('state').textContent = '当前目标：' + (NAMES[s.voice_target] || s.voice_target) + ' · ' + (DESC[s.voice_target] || '');
  } catch (e) { document.getElementById('state').textContent = '读取状态失败'; }
}
document.querySelectorAll('.card').forEach(el => el.addEventListener('click', async () => {
  const t = el.dataset.t;
  try {
    const r = await (await fetch('/api/voice_target', { method:'POST', body: JSON.stringify({ target:t }) })).json();
    if (r.ok) { await refresh(); toast('已切换到 ' + (NAMES[t] || t)); }
    else toast('失败：' + (r.error || ''));
  } catch (e) { toast('请求失败'); }
}));
async function refreshPresence() {
  const el = document.getElementById('devbar');
  try {
    const p = await (await fetch('/api/presence')).json();
    if (!p.available) { el.innerHTML = '<span class="dev"><span class="dot unknown"></span>设备状态未知（presence 未运行）</span>'; return; }
    const order = ['atv','mac','win'];
    el.innerHTML = order.map(r => {
      const d = p.devices[r] || { state:'unknown' };
      const st = ['online','offline','unknown'].indexOf(d.state) >= 0 ? d.state : 'unknown';
      const label = st === 'online' ? '在线' : st === 'offline' ? ('离线 ' + Math.round(d.age || 0) + 's') : '未知';
      return '<span class="dev"><span class="dot ' + st + '"></span>' + NAMES[r] + ' ' + label + '</span>';
    }).join('');
  } catch (e) { el.innerHTML = '<span class="dev"><span class="dot unknown"></span>设备状态读取失败</span>'; }
}
refresh(); setInterval(refresh, 5000);
refreshPresence(); setInterval(refreshPresence, 3000);
</script>
</body>
</html>
"""

PAGE_KEYMAP = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>按键配置 · T1</title>
<style>%%CSS%%</style>
</head>
<body>
<h1>按键配置</h1>
<p class="sub">三个目标各自一份键位；遥控器按键按「当前目标」（主页切换）取用 · 保存后下一次按键生效</p>
<div class="tabs">
  <button class="tab" data-t="atv">ATV</button>
  <button class="tab" data-t="mac">macOS</button>
  <button class="tab" data-t="win">Windows</button>
</div>
<p class="sub" id="hint"></p>
<div id="grid">加载中…</div>
<div class="bar">
  <a class="btn" href="/">返回</a>
  <button class="btn" id="reset">恢复本页默认</button>
  <button class="btn primary" id="save">保存</button>
</div>
<div class="toast" id="toast"></div>
<script>
let CFG = null, CHOICES = null, ORDER = [], TAB = 'atv', REPEAT_OPT = null, REV = null;
const TNAMES = { atv:'ATV', mac:'macOS', win:'Windows' };
let toastTimer;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
}
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function extLabel(v) {
  return v === 'APP:CLOSE' ? '关闭当前应用（长按电源键）'
    : v === 'TARGET:SWITCH' ? '★ 电源（连击切设备）'
    : v.startsWith('APP:') ? '打开/切换到 ' + v.slice(4)
    : v.startsWith('URL:') ? '打开网页 ' + v.slice(4)
    : v.startsWith('RUN:') ? '执行 ' + v.slice(4) : v;
}
function opts(list, selected) {
  const cur = selected || '';
  const parts = list.map(([v, name]) => '<option value="' + v + '"' + (v === cur ? ' selected' : '') + '>' + name + '</option>');
  if (cur && !list.some(([v]) => v === cur)) {
    parts.push('<option value="' + esc(cur) + '" selected>' + esc(extLabel(cur)) + '</option>');
  }
  return parts.join('');
}
function sel(code, f, val, disabled, list) {
  return '<select data-code="' + code + '" data-f="' + f + '" data-prev="' + esc(val || '') + '"'
    + (disabled ? ' disabled' : ' onchange="customApp(this)"') + '>' + opts(list, val) + '</select>';
}
const CUSTOM_META = {
  '__CUSTOM_APP__': { prefix:'APP:', ask:'输入要打开的应用名（不能含空格；支持简称，如 Chrome / 微信 / 飞书）：', err:'应用名不能含空格' },
  '__CUSTOM_URL__': { prefix:'URL:', ask:'输入要打开的网址（不能含空格；示例 https://www.baidu.com）：', err:'网址不能含空格' },
  '__CUSTOM_RUN__': { prefix:'RUN:', ask:'输入要执行的命令（不能含空格；含空格请写成脚本文件后填其路径）：', err:'命令不能含空格' },
};
const CUSTOM_SENTINELS = Object.keys(CUSTOM_META);
function customApp(el) {
  const meta = CUSTOM_META[el.value];
  if (!meta) { el.dataset.prev = el.value || ''; return; }
  const prev = el.dataset.prev || '';
  const v = prompt(meta.ask, '');
  const name = (v || '').trim();
  if (name && !/\\s/.test(name)) {
    const val = meta.prefix + name;
    if (!Array.from(el.children || []).some(c => c.value === val)) {
      const o = document.createElement('option');
      o.value = val; o.textContent = extLabel(val);
      el.appendChild(o);
    }
    el.value = val; el.dataset.prev = val;
  } else {
    if (name) toast(meta.err);
    el.value = prev;
  }
}
function render() {
  document.querySelectorAll('.tab').forEach(el => el.classList.toggle('active', el.dataset.t === TAB));
  const kb = (TAB !== 'atv');
  document.getElementById('hint').textContent = kb
    ? '当前编辑：' + TNAMES[TAB] + ' · 单击 + 长按列（「⟳ 按住连发」= 按住连续触发；或选动作 = 0.6s 后触发一次）· 双击不可用'
    : '当前编辑：ATV · 单击/双击/长按（0.6s）· 长按列可选「⟳ 按住连发」· 配置“双击”后该键单击将有 0.3 秒判定延迟';
  const keys = ((CFG.targets || {})[TAB] || {}).keys || {};
  const choices = CHOICES[TAB] || [];
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  for (const code of ORDER) {
    const k = keys[code];
    if (!k) continue;
    const locked = !!k.locked, repe = !!k.repeat;
    const dis = (f) => locked || (f === 'double' && (kb || repe));   // v2.4: 长按列不再因连发禁用
    const row = document.createElement('div');
    row.className = 'row' + (locked ? ' locked' : '');
    row.innerHTML =
      '<div class="kname">' + k.label + '<small>#' + code + (repe ? ' · 按住连发' : '') + (k.long ? ' · 长按' : '') + (kb ? ' · 键盘' : '') + '</small></div>' +
      '<div class="cells">' +
        '<label>单击' + sel(code, 'single', k.single, dis('single'), choices) + '</label>' +
        '<label>双击' + sel(code, 'double', k.double, dis('double'), choices) + '</label>' +
        '<label>长按' + sel(code, 'long', k.long || (repe ? REPEAT_OPT[0] : ''), dis('long'), [choices[0], REPEAT_OPT].concat(choices.slice(1))) + '</label>' +
      '</div>' +
      (k.note ? '<div class="note">' + k.note + '</div>' : '');
    grid.appendChild(row);
  }
}
async function load() {
  try {
    const d = await (await fetch('/api/keymap')).json();
    CFG = d.cfg; CHOICES = d.choices; ORDER = d.order; REV = d.rev;
    REPEAT_OPT = d.repeat_opt || ['__REPEAT__', '⟳ 按住连发'];
    render();
  } catch (e) { document.getElementById('grid').textContent = '加载失败：' + e; }
}
async function save() {
  const keys = {};
  document.querySelectorAll('select[data-code]').forEach(s => {
    const c = s.dataset.code, f = s.dataset.f;
    (keys[c] = keys[c] || {})[f] = s.value || null;
  });
  for (const code of Object.keys(keys)) {
    // v2.4: repeat 由「长按」列派生 —— 选「⟳ 按住连发」= repeat=true（与 long/double 互斥清空）
    for (const f of ['single', 'double', 'long']) {
      if (CUSTOM_SENTINELS.includes(keys[code][f])) keys[code][f] = null;   // 防自定义占位残留（APP/URL/RUN）
    }
    if (keys[code].long === REPEAT_OPT[0]) {
      keys[code].long = null; keys[code].double = null; keys[code].repeat = true;
    } else {
      keys[code].repeat = false;
    }
  }
  const body = { target: TAB, hold_threshold: CFG.hold_threshold, double_window: CFG.double_window, keys, rev: REV };
  try {
    const resp = await fetch('/api/keymap', { method:'POST', body: JSON.stringify(body) });
    const r = await resp.json();
    if (r.ok) { REV = r.rev; toast('已保存（' + TNAMES[TAB] + '）· 下一次按键生效'); load(); }
    else if (resp.status === 409) toast('⚠ ' + (r.msg || '配置已变化，请刷新页面后重试'));
    else toast('保存失败：' + (r.error || ''));
  } catch (e) { toast('请求失败'); }
}
async function reset() {
  if (!confirm('恢复「' + TNAMES[TAB] + '」的默认键位？（该目标当前修改将丢失）')) return;
  try {
    const r = await (await fetch('/api/keymap/reset', { method:'POST', body: JSON.stringify({ target: TAB }) })).json();
    if (r.ok) { toast('已恢复 ' + TNAMES[TAB] + ' 默认'); load(); } else toast('失败：' + (r.error || ''));
  } catch (e) { toast('请求失败'); }
}
document.querySelectorAll('.tab').forEach(el => el.addEventListener('click', () => { TAB = el.dataset.t; render(); }));
document.getElementById('save').addEventListener('click', save);
document.getElementById('reset').addEventListener('click', reset);
// v2.9: 初始 tab = 当前激活目标（/api/state）；取不到时回退默认 atv
async function boot() {
  try {
    const s = await (await fetch('/api/state')).json();
    if (['atv', 'mac', 'win'].includes(s && s.voice_target)) TAB = s.voice_target;
  } catch (e) { /* 回退 atv */ }
  load();
}
boot();
</script>
</body>
</html>
"""

PAGE_HOME = PAGE_HOME.replace("%%CSS%%", CSS)
PAGE_KEYMAP = PAGE_KEYMAP.replace("%%CSS%%", CSS)


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log(f"t1_webui v2.16 启动: http://0.0.0.0:{PORT}/ (voice_target={read_target()})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
