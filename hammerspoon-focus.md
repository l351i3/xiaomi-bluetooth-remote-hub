# Mac 焦点子系统（Hammerspoon + AX）— 遥控器「跳输入框 / 切换后焦点修复 / 点击焦点元素」全说明

> 2026-10-10 上线（v1.0；v1.1 增 clickFocused）。用户需求原话：「有时候切换到窗口它无法获得焦点怎么办？没法输入到搜索框里头。
> 有什么按键可以跳到输入框吗？」+（v1.1）「TAB 键可以切换到 WorkBuddy 的任务列表，但切到焦点之后按回车（OK 键）
> 没法触发点击，这个怎么解决？」本文 = 该子系统的权威文档（机制 / 实证 / 部署 / 局限 / 回滚）。
> 关联：`mac-key-bridge.md`（v1.9 通道挂接点）、`t1-webui.md`（v2.6 动作入口）、主源 `hammerspoon/remotehub_focus.lua`。

## 是什么

- **三个能力**：
  1. **`FOCUS_INPUT`（跳输入框）**：按键触发 → 修复前台窗口焦点 + 把键盘焦点设到窗口里的**首个可编辑元素**
     （聊天输入框 / 搜索框 / 编辑器）。遥控器 mac 份 **#41 直播键**默认绑定（可在网页改绑任意键）。
  2. **切换后焦点修复（assist）**：凡经 key_bridge 触发的 `APP:*` 应用切换 / AppPicker 选择打开成功后，
     **+0.45s 自动**做一次窗口聚焦修复（unmin + AXMain + AXRaise + AXFocused）——治「切过去了但键盘焦点没跟过来」。
  3. **`CLICK`（点击焦点元素，v1.1）**：按键触发 → 点击**当前键盘焦点元素**（AXPress 优先 / 坐标兜底）——
     治「TAB 切到任务条目后按回车无反应」（Electron 焦点元素不响应合成键，但支持 AX 层"点击"，与真实点击等效）。
     遥控器 mac 份 **OK 长按**生产绑定（短按仍是回车）。
- **执行者**：**Hammerspoon.app**（v1.1.1，常驻）。其辅助功能授权已存在（`hs.accessibilityState()=true`），
  **无需任何新 TCC 设置**；AX 操作全部以 Hammerspoon 的身份执行。
- **调用方式**：`/opt/homebrew/bin/hs -c '...'`（Hammerspoon 自带 CLI，走 message port）。

## 为什么需要（问题实证）

| 现象 | 实证（2026-10-10 探针） |
| --- | --- |
| macOS 14+ 应用激活**偶发静默丢弃** | `hs.application:activate()` 连续两次失败（前台不变）；`AXFrontmost` 强推也失败；`app_switch activate(.activateAllWindows)` 成功 → 故 **APP 切换主路径不变**，仅追加 assist 兜底 |
| Chromium/Electron 系（WorkBuddy/Obsidian）**AX 树不可靠** | 前台仅 ~9/70 节点、树里找不到输入框；`AXEnhancedUserInterface`/`AXManualAccessibility` 开关无效（仅 +1 节点） |
| 微信（com.tencent.xinWeChat）= **AX 黑洞** | 树 5 节点 + 24 探测点全 nil（内容层完全不可见） |
| 但**坐标 hit-test 可行** | `systemWide:elementAtPosition(x,y)` 在树遍历失败处**命中真实元素** —— WorkBuddy 聊天框 = `AXTextArea`，窗口比例 **fx=0.50 / fy≈0.85**（0.82–0.88 全宽带）；设 `AXFocused=true` 读回 true ✅ |
| Safari 阳性对照 | 树完整（241 节点，含 `AXTextField`「智能搜索栏」）→ 树遍历兜底策略对"树完整"应用仍有价值 |
| **TAB 焦点链上的元素不响应合成回车**（v1.1 实证） | WorkBuddy 任务条目 / 消息元素等：合成 ENTER 完全无反应（组件未实现键盘激活）；对照=模型选择器 AXComboBox 上 ENTER 有效（键注入本身无损）。**但这类元素几乎都支持 `AXPress`** —— `performAction("AXPress")` 与真实点击等效（任务条目往返双验证 ✅） |

**结论**：焦点检测/设置不能只靠树遍历；主策略 = **窗口修复（保底）+ 坐标 hit-test（主力）+ 树遍历（补漏）**。

## 链路全图

```
遥控器 #41 / OK长按（或任意改绑键）
  └─ T1 voice_fwd.py v2.3 ──UDP:8791──> Mac key_bridge.py v1.9
        ├─ "KEY FOCUS_INPUT DOWN" → do_focus_input()（0.6s 防抖, 线程内）
        ├─ "KEY CLICK DOWN"       → do_click()（0.6s 防抖, 线程内）
        └─ APP 动作成功后          → do_focus_assist()（异步）
              └─ /opt/homebrew/bin/hs -c 'dofile("~/.hammerspoon/remotehub_focus.lua").focusInput()|assistLater()|clickFocused()'
                    └─ Hammerspoon.app（AX 授权在此）
                          └─ remotehub_focus.lua（窗口修复 → 缓存 → 坐标网格 → 树遍历 → 设焦点读回；clickFocused 四段策略）
AppPicker.app v1.1（应用选择器 ENTER 激活成功后）── 同款 spawn assistLater()
```

## remotehub_focus.lua 策略（v1.0 / v1.1）

对外 API 四个：`focusInput()`（跳输入框）/ `clickFocused()`（点击焦点元素，v1.1）/ `focusWindow()`（立即窗口修复，调试用）/ `assistLater()`（+0.45s 调度）。

`focusInput()` 五阶段：

1. **窗口聚焦修复**（总是先做；对微信等无内容 AX 的应用即最终效果）：
   `AXMinimized=false`（如最小化）→ `AXMain=true` → `AXRaise` → `AXFocused=true`
2. **缓存点**：`~/.hammerspoon/remotehub_focus_cache.json`（bundleID → {fx,fy} 窗口比例坐标）——
   上次成功命中的点优先复查（布局未变的日常路径，最快最稳）
3. **坐标网格**：`GRID_Y`（12 行，**底部输入区优先** 0.85→0.82→0.88→…→0.12）× `GRID_X`（6 列，中位优先 0.5/0.62/0.74/0.38/0.86/0.26）
   —— 每点 hit-test 判 `EDITABLE`（AXTextArea/AXTextField/AXSearchField/AXComboBox/AXSecureTextField）
4. **树遍历**（深度 ≤14 / 预算 400 节点）：对 Safari 等"树完整"的应用补漏；Chromium 系会空转（可接受）
5. **设焦点 + 读回**：`AXFocused=true` 后读回确认；成功后**回写缓存**（fx/fy）。全失败报 `NOEDIT`（窗口修复仍已生效）

返回契约（单行文本，key_bridge 记日志）：`OK <app> role=... fx=.. fy=.. src=cache|grid|tree before=.. after=..` / `NOEDIT ...` / `ERR ...`。

`clickFocused()`（v1.1）四段策略 —— 点击**当前键盘焦点元素**（`systemWide:AXFocusedUIElement`）：

1. **自身 `AXPress`**（多数情况：任务条目=AXButton、输入框=AXTextArea、消息内按钮…）
2. **直接子元素 `AXPress`**（壳容器场景：如 Artifact tab 外壳 AXGroup → 子 AXRadioButton）
3. **向上 ≤6 层**找最近支持者
4. **坐标兜底**：焦点元素中心 `leftClick`（**尺寸门槛 w>8,h>4**，剔除 1px 垃圾坐标防误点）

返回契约：`OK press <role> t=<label> via=self|child|upN` / `OK click@x,y (坐标兜底)` / `NOFOCUS ...` / `FAIL ...`。
冒烟实录：`OK press AXTextArea via=self`（输入框场景，20:30）；UDP 端到端 `KEY CLICK DOWN → [click] OK`（20:31）。

## Hammerspoon 环境（一次性设置，已完成）

- **`~/.hammerspoon/init.lua`**（990B，备份 `init.lua.bak-20261010-190750`）——末尾追加 IPC 启用：
  ```lua
  local okIpc, errIpc = pcall(require, "hs.ipc")
  if not okIpc then hs.console.printStyledtext("remotehub: hs.ipc 加载失败: " .. tostring(errIpc)) end
  ```
  **不加载 `hs.ipc` 时 hs CLI 报 `can't access Hammerspoon message port`**（Hammerspoon 默认不开 message port）。
- 部署副本：`~/.hammerspoon/remotehub_focus.lua`（主源 `remote-hub/hammerspoon/remotehub_focus.lua`，双端 md5 核对纪律）。
- **权限**：辅助功能授权在 Hammerspoon.app 自身（用户早前已授；`hs.accessibilityState()` 读 true）。改动本 lua **纯脚本、不涉及签名/授权**。

## 部署与验证记录（2026-10-10 19:2x）

- key_bridge.py **v1.7 → v1.8**（7 处编辑：头注 / threading / HS 常量 / do_focus_input / do_focus_assist / APP 成功挂钩 / 主循环分支 + banner/STATUS 版本行）
  —— 重启（kill -9 → KeepAlive 拉新 pid 21106），banner `key_bridge v1.8 ... + FOCUS_INPUT(跳输入框)` ✅
- AppPicker.swift **v1.0 → v1.1**（ENTER 激活后 `spawnFocusAssist()`；`AppPicker.bak-20261010-1930` 备份；重编译替换）
- t1_webui **v2.4 → v2.5**（动作清单「★ 跳转输入框」；离线 50/50 + JS 18/18）→ 部署 T1 + banner v2.5 ✅
- 线上 mac 份 **#41 = FOCUS_INPUT**（POST API 配置；GET 复核）
- **冒烟（本机 UDP 注入, 19:24）**：
  ```
  [19:24:29] RX 127.0.0.1 -> KEY FOCUS_INPUT DOWN (已触发)
  [19:24:29]   -> [focus] 跳输入框 OK | OK WorkBuddy role=AXTextArea fx=0.50 fy=0.85 src=cache before=true after=true
  ```
  （= key_bridge launchd 上下文 → hs → Hammerspoon → AX 全链通；缓存命中）
- **待用户真机验收**：①遥控器 #41 → Mac 跳输入框；②切应用（主页键轮询/长按选择器打开）后键盘焦点跟手。

## 已知局限

- **微信等 AX 黑洞**：只能做窗口级修复（无输入框级）——`focusInput` 报 NOEDIT 但窗口聚焦已修复。
- **Chromium 系依赖坐标**：布局大改（如输入框挪位）后缓存点可能失效 → 自动落入网格重探（多花 ~0.5s），成功即更新缓存。
- **多窗口**：以「前台 App 的聚焦窗口」为目标（`AXFocusedWindow`→`AXMainWindow`→`AXWindows[1]`）；不处理"同应用换窗"。
- assist 是「**尽力而为**」：+0.45s 窗口修复，失败仅记日志（不重试、不影响切换本身）。
- **读回值 `before/after` 可能为 nil**（实测 19:39-19:43 若干次）：Chromium 系在焦点状态切换瞬间
  `AXFocused` 属性读取会返回 nil（而非 false/true）——**属时序怪癖，不影响功能**（用户实测生效）；
  副效应=该次不触发缓存更新（缓存已有值时无碍）。日志判读：**以 OK 行 + 实际效果为准**，勿因 nil 误判失败。

## 排障速查

```bash
# 手动跳输入框（当前前台 App）：
/opt/homebrew/bin/hs -c 'return dofile(os.getenv("HOME").."/.hammerspoon/remotehub_focus.lua").focusInput()'
# 手动点击焦点元素（当前焦点在哪就点哪；任务条目场景=打开该任务）：
/opt/homebrew/bin/hs -c 'return dofile(os.getenv("HOME").."/.hammerspoon/remotehub_focus.lua").clickFocused()'
# 手动窗口修复：
/opt/homebrew/bin/hs -c 'return dofile(os.getenv("HOME").."/.hammerspoon/remotehub_focus.lua").focusWindow()'
# 缓存查看/清空：
cat ~/.hammerspoon/remotehub_focus_cache.json     # 删除文件即全量重探（或删某 bundleID 单项）
# hs CLI 无响应排查（① IPC 模块 ② Hammerspoon 是否在跑）：
/opt/homebrew/bin/hs -c 'return "alive"'
```

- **hs CLI 超时坑**：内部工作超 ~30s 报 `error communicating with Hammerspoon: receive timeout`（大扫描会阻塞主线程）
  —— 长任务改用异步模式（`hs.timer.doAfter` + 结果写文件 + 外部轮询）。
- macOS 无 GNU `timeout`；需要限时时用 `perl -e 'alarm 8; exec @ARGV' …` 包裹。
- key_bridge 日志看 `remote-hub/logs/key_bridge.log` 里 `-> [focus] ...` 行。

## 回滚

```bash
# A) 只关"跳输入框"（最小改动）：网页把 mac 份 #41 改回空 / 或换绑其他动作 —— 无需动代码
# A2) 只关"点击焦点元素"：网页把 mac 份 #28 OK 的「长按」列改回空（短按回车不受影响）
# B) 回滚 key_bridge 到 v1.7（FOCUS 通道整体消失）：
cp remote-hub/key_bridge.py.v17.bak-20261010-1748 remote-hub/key_bridge.py && kill -9 $(pgrep -f key_bridge.py)
# C) 回滚 AppPicker 到 v1.0（linker-signed 直接替换即用）：
cp remote-hub/AppPicker.bak-20261010-1930 remote-hub/AppPicker.app/Contents/MacOS/AppPicker
# D) 还原 Hammerspoon init.lua（禁用 IPC 启用段，非必须）：
cp ~/.hammerspoon/init.lua.bak-20261010-190750 ~/.hammerspoon/init.lua
```

## 沿革

| 版本 | 时间 | 变更 |
| ---- | ---- | ---- |
| v1.0 | 10-10 19:2x | 首版：focusInput 五阶段 + assistLater + 缓存；key_bridge v1.8 / webui v2.5 / AppPicker v1.1 挂接 |
| v1.1 | 10-10 20:3x | `clickFocused()` 四段策略（self→child→up≤6→坐标兜底+尺寸门槛）；key_bridge v1.9 `do_click()` / webui v2.6 动作 `CLICK`；生产绑定 **OK 长按=CLICK**（用户需求「TAB 切焦点后回车点不动」） |
| 守卫 v1.0 | 10-10 19:5x | 健康守卫 `hs_health.py` + `com.remotehub.hs-health` 上线（见下节） |

---

## ★ 健康守卫（hs_health / com.remotehub.hs-health）— 2026-10-10 19:5x 上线

**决策出处**（用户原话）：「保持自动更新，然后加一个 B 自检脚本。核心就是用户感知最低最好，一旦出现什么故障主动报告，然后安排修复。如果能自动修复就更好了。」

**是什么**：`remote-hub/hs_health.py` v1.0 —— launchd 定时体检医生（**每 1 小时 + 登录时**各一次）：
- **12 项检查**：Hammerspoon 焦点域 8 项（App 版本 / CLI 链接 / 进程 / IPC / 辅助功能授权 / 焦点脚本一致性 / init.lua 块 / 脚本可加载）+ Mac 四服务存活（voice-bridge / atvv-receiver / key-bridge / cgpost-serve）
- **有异常**：能修的自动修 → 复检 → **macOS 通知报告**（「已自动修复」或「需人工处理 + 指引」）
- **全绿**：零打扰（日志仅一行心跳 `OK 12/12 hs=v1.1.1`）

**自动修复能力**：

| 故障 | 自动修复 | 备注 |
|---|---|---|
| hs CLI 符号链接断裂/悬空 | ✅ 重建 | 目标 = App 内 `Contents/Frameworks/hs/hs` |
| 焦点脚本缺失/被改 | ✅ 从主源重部署 | md5 核对 |
| init.lua 缺 IPC 块 | ✅ 幂等追加 | 修复前自动留档 `init.lua.autofix.bak` |
| Hammerspoon 未运行 | ✅ `open -a` 拉起 | 拉起后轮询等 IPC 就绪 |
| IPC 无响应（进程在） | ✅ `kill -TERM` 重启 app | 30 分钟防风暴窗口 |
| 四服务掉线 | ✅ `kickstart`；未加载则 `bootstrap` | launchd 上下文 bootstrap 实证可用 |
| AX 授权缺失 | ⚠️ 触发系统引导 + 通知用户勾选 | TCC 不允许代点（1 分钟人工） |
| App 缺失/损坏 | ❌ 通知（附重装指引） | `brew install --cask hammerspoon` |

**部署信息**：服务 `com.remotehub.hs-health`（plist 源 `mac-launchd/`；`RunAtLoad` + `StartInterval=3600`；参数 `--fix --notify --quiet`）；日志 `logs/hs_health.log`；状态 `state/hs_health_state.json`（`last_result`: OK/FIXED/PARTIAL/ISSUES）。

**日常操作**：
```bash
cd remote-hub
python3 hs_health.py                  # 手动看报告（不改任何东西）
python3 hs_health.py --fix            # 手动修复
launchctl kickstart gui/501/com.remotehub.hs-health   # 立即触发一次定时巡检（含修+通知）
```

**演练记录（全过 ✅，19:52-20:01）**：
1. 断 CLI 链接 → 检测 8/12 → 修复 12/12 → 链接复验 ✓
2. 删焦点脚本 → 检测 10/12 → 重部署 → md5 双端一致 ✓
3. init.lua 删块 → 修复后**逐字节还原**（md5 一致）✓
4. kill Hammerspoon → `open -a` 拉起（新 pid + IPC 就绪 + ax=true）✓
5. **bootout key-bridge → 守卫（launchd 上下文）自动 bootstrap 复活**（新 pid + pong）✓
6. 端到端：破坏 → kickstart 服务 → 自动修复 + 通知发出 ✓

**关键发现（运维纪律补充）**：
- `osascript quit app "Hammerspoon"` 被自动化权限拦（-10004）→ 守卫重启改用 `kill -TERM`（无权限依赖；先 TERM 等待，超时才 KILL）
- `launchctl kickstart` **从 WorkBuddy shell 可用**（修正先前「launchctl 全被拦」认知——只有 bootstrap/submit 类被拦）
- **`launchctl bootstrap` 在 launchd 上下文完全可用**（守卫自修服务实证）——WorkBuddy shell 的 `5: I/O error` 是上下文问题而非权限问题
- 守卫服务**自身**被 bootout 时无法自愈（无鸡生蛋）→ 手动兜底：SSH 本机会话 `launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.remotehub.hs-health.plist`

**回滚**：`launchctl bootout gui/501/com.remotehub.hs-health`（立即停用；删 plist 可防下次登录自启）。
