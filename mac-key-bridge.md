# Mac 侧「遥控器按键」注入桥 key_bridge — 2026-10-14（v1.15 / serve 常驻 + 应用动作/选择器 v1.3 + 焦点修复/点击焦点/翻页 + URL·RUN + 关闭/鼠标模式·模式 HUD + 设备切换 HUD + 焦点兜底〔lua v1.6〕版）

## 是什么

遥控器按键（目标=Mac 时）→ T1 `voice_fwd.py` v2.0 → UDP **:8791** → 本服务 → 键盘注入。  
键位（用户 10-09 拍板）：**OK=回车、返回=Esc、方向=方向键**（配置在 T1 `:8765 /keymap` 的 Mac tab）。  
**真机验收已通过 ✅**（2026-10-10 13:24，用户实测确认「可以了」）。  
**v1.5 新增「应用动作」**（15:3x）：按键可执行 `APP:TOGGLE`（切换应用）/`APP:<名称>`（打开/切换应用）——见下方专节。  
**v1.6 新增「全应用轮询 CYCLE」**（16:5x）、**v1.7 新增「应用选择器 PICK」**（17:4x）：主页键 #102 = **短按轮询 / 长按唤出选择面板**（左右选 + OK 打开 + Esc 取消）——见下方专节。  
**v1.8 新增「焦点修复 / 跳输入框」**（19:2x，用户反馈「切换窗口有时无法获得焦点、无法输入」）：`FOCUS_INPUT` 动作（T1 mac 份 #41 直播键默认绑定「★ 跳转输入框」）+ 应用切换后自动焦点修复 —— 经 **Hammerspoon** 执行 AX 操作，见下方专节与 `hammerspoon-focus.md`。  
**v1.9-v1.11 新增**（10-10 20:3x ~ 10-11 21:5x）：`CLICK` 点击焦点元素 / 翻页键 `PAGEUP(116)`·`PAGEDOWN(121)` / `URL:`·`RUN:` 动作——各见下方专节。  
**10-12 修订**：VERSION 常量单一来源化（修 STATUS 残留 v1.8；实测 `STATUS v1.11` ✅）；AppPicker **v1.3** 长名滚动（对齐 Windows）。  
**v1.12 新增（10-12 14:0x）**：`APP:CLOSE`「关闭当前应用」（**长按电源键 #116** 生产绑定；app_switch v1.2 `close` = 优雅退出 + Finder 保护；CLOSE 专用强防抖 2.0s + 免 focus assist）——见下方专节。  
**v1.13 新增（10-13）**：**鼠标模式**（`MOUSE:*` 动作，遥控器 dpad 模拟鼠标）——T1 `voice_fwd` v2.5 模式层产生，本桥经 Hammerspoon `remotehub_focus.lua` v1.2 执行（滑行/滚动/点击）；端到端实测 8 PASS（真实光标位移/松开即停/看门狗自停）——见下方专节。
**v1.14 新增（10-13 14:2x）**：`MOUSE:MODE:ON|OFF` **模式 HUD 后端**（→ lua v1.3 `mouseHud` 浮层；仅 DOWN；全链冒烟 `OK hud on/off` ✅）——配套 T1 `voice_fwd` v2.6，治用户首测「按了不知道生效没有」。
**v1.15 新增（10-13 15:2x）**：`TARGET:SWITCH:ATV|MAC|WIN` **设备切换 HUD 后端**（→ lua v1.4 `switchHud` 浮层；仅 DOWN；复用鼠标串行 worker）——配套 T1 `voice_fwd` v2.7 / `relay_min` v0.11 **电源键连击**（1 击=ATV / 2 击=Mac / 3 击=Win；切到 atv 时提示发旧目标端=本端必见）。lua 实机应答 `OK hud switch:win` ✅。
**lua v1.5 更新（10-14 03:0x）**：本桥脚本**零改动**（焦点链路 `hs -c do_focus_input` 不变）；`focusInput()` 五段全 miss **兜底点击 `(0.5, 0.92)` + 光标原位恢复**（报 `NOEDIT+CLICK@x,y`）——治用户反馈「鼠标模式下按焦点聚焦键不灵 + 键盘模式也不灵」（另一根因 = T1 `voice_fwd` v2.8 模式内放行 #41）。详见 `hammerspoon-focus.md` 沿革 v1.5。
**lua v1.6 更新（10-14 03:4x，承用户复查「还是不行」深挖）**：本桥脚本**仍零改动**；lua 侧修复三号根因——① **前台提升 `ensureFrontApp`**（目标窗被遮挡时合成点击/键盘被顶层窗截胡；activate + z 序校验）；② 兜底坐标 `0.92 比例` → **距窗底 105px**（0.92 实测落输入框下方按钮行）；③ 提升失败 `front=fail-skip` 跳过点击。实机注入字符验证 ✓。详见 `hammerspoon-focus.md` 沿革 v1.6。

## 链路全图（目标=mac）

```
RC003 遥控器 ──BLE──> T1
  ├─ relay_min.py v0.10   （target=mac → 全部按键忽略）
  └─ voice_fwd.py v2.0
       ├─ 语音键 63: "VOICE down/up"      → Mac:8788 voice_bridge（输入法语音，既有）
       └─ 普通键:    "KEY <动作> DOWN/UP"  → Mac:8791 key_bridge v1.5
                                              ├─ 键盘动作 · 主路径  UNIX dgram /tmp/cgpost.sock
                                              │    → cgpost serve 常驻进程（CGPost.app 内二进制，CGEventPost）
                                              ├─ 键盘动作 · 兜底    launchctl submit → cgpost key <nxkc> <0|1>
                                              │    （serve 失联熔断 15s 期间启用；1s 后 remove 防幽灵重启）
                                              └─ 应用动作 "KEY APP:xxx DOWN" → app_switch 工具（切换/轮询）/ AppPicker.app（v1.7 选择器）
                                                   （NSWorkspace 激活, 非键盘注入, 无需 TCC）
```

## ★ 为什么是 serve 常驻（v1.4 核心结论）

- 旧形态（≤v1.3）= `launchctl submit` **每事件起独立进程**：「快生快灭」致合成事件**偶发投递丢失**  
  （对照实验实证：双进程 key 模式丢约一半——key109 仅到 UP / key111 仅到 DOWN）
- serve 常驻进程保持**单一 CGEventSource 生命周期** → 实测 4 组 down/up（间隔 0.05~0.4s）**16/16 全捕获、零丢失**  
  （监听器时间线与 serve 日志逐条对齐）
- 与两开源参考（mi-ao / MIC-RC003-Windows）的「常驻 App + 标准授权 + CGEventPost」形态**同构**（对照收官）

## 服务清单（Mac launchd，本链条相关）

| 服务                     | label                                                        | 说明                                                                |
| ---------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------- |
| key_bridge.py **v1.15** | `com.remotehub.key-bridge`                                   | UDP :8791 收键 → 双路径注入 + 选择器路由 + **焦点修复/CLICK/URL·RUN/关闭/鼠标模式·模式 HUD/设备切换 HUD**（KeepAlive）                                   |
| cgpost serve 常驻        | `com.remotehub.cgpost-serve`                                 | **v1.4 新增**（第 4 个 Mac 服务）；UNIX `/tmp/cgpost.sock`；CGEventPost 主通道 |
| hs_health.py **v1.0**  | `com.remotehub.hs-health`                                    | **19:5x 新增（第 5 个）**：每小时巡检 Hammerspoon 焦点域 + 四服务存活；异常自动修复 + 发通知；详 `hammerspoon-focus.md`「健康守卫」节 |
| （语音链）                  | `com.remotehub.voice-bridge` / `com.remotehub.atvv-receiver` | 见 `voice-diagnosis-2026-10-10.md`                                 |

## 服务实现（key_bridge.py v1.4）

- 文件：`remote-hub/key_bridge.py`；launchd：`~/Library/LaunchAgents/com.remotehub.key-bridge.plist`
- 日志：`remote-hub/logs/key_bridge.log`（注入进程输出 → `logs/key_bridge_inject.log`）
- 协议（UDP 文本，与 voice_bridge 同风格）：
  - `KEY <NAME> DOWN` / `KEY <NAME> UP`（T1 → 本服务）
  - `RAW <nxkc> DOWN|UP`（诊断：直注原始 keycode，不查键表）
  - `ping` → `pong`；`status` → 状态行（`serve=up/down, idle…`）
- 键表（macOS NX keycode）：`ENTER=36 ESC=53 UP=126 DOWN=125 LEFT=123 RIGHT=124 SPACE=49 TAB=48 BACKSPACE=51`
- **注入双路径（v1.4）**：
  - 主路径 serve：UNIX dgram `/tmp/cgpost.sock`，`KEY <nxkc> <0|1>` → `OK`（超时 0.5s）
  - 兜底 submit：serve 失联 → 置 `_serve_down_until` **熔断 15s**，期间走  
    `launchctl submit -l com.remotehub.key.<ts>.<seq> -- cgpost key <nxkc> <0|1>`（1s remove；唯一 label 防积累）
  - 日志可辨路径：`[serve]` / `[submit兜底]`
- **★ UNIX dgram 显式 bind 坑（勿再简化）**：macOS 上匿名/仅 connect 的 UNIX datagram socket **收不到服务端回复**——  
  客户端 socket 必须**显式 bind** 到本地路径（本服务 `UDS_LOCAL=/tmp/key_bridge_cli.sock`）才能收到 `OK`。  
  此前所有「PING 超时」谜团皆因此，**与沙箱无关**。
- 守卫：**卡键自愈 20s**（DOWN 后无活动 → 补发 UP）+ 启动清扫历史 `com.remotehub.key.*` job
- 连发语义：T1 侧 0.12s 节流补发 DOWN（macOS 对合成键不做系统级自动 repeat）

## ★ 应用动作通道（v1.5，10-10 15:3x）——「切换应用 / 打开应用」

**背景**：用户需求「按键→切换应用（类似 cmd+tab）/ 打开某应用」。「组合键合成」已实证不可行（见下节调查），  
本功能改&#x8D70;**「直接激活」语义**——不合成 ⌘Tab，用 NSWorkspace API 直接激活应用，**效果等价且更强**。

- 工具：`remote-hub/app_switch.swift`（编译产物 `app_switch`，**无需任何 TCC 权限**）
  - `activate <名称>`：切换到已运行应用（bundleID/名称模糊匹配，中文名可用）；未运行则 `open -a` 启动
  - `toggle`：最近两个应用间跳（≈ cmd+tab 快速点按；状态在 `state/app_switch.json` 的 {prev, cur}）
  - `next`：按名称序（localizedStandardCompare）循环下一个（≈ 按住 ⌘ 连按 ⇥ 的简化等价）
  - `close`：**关闭当前前台应用**（v1.2, 10-12）——`NSRunningApplication.terminate()` 优雅退出
    （等价 Cmd+Q；未保存内容弹保存确认）；**Finder 拒绝关闭**（系统组件保护）
  - `list` / `front`：诊断（列出常规应用 / 打印当前前台）
- 协议（UDP :8791）：`KEY APP:<后缀> DOWN`（**仅 DOWN 触发一次；UP 忽略**；`APP_DEBOUNCE` 0.35s 防抖挡连发/重复包）
  - `APP:TOGGLE` / `APP:NEXT` / `APP:<名称|bundleID>`（如 `APP:微信`、`APP:Safari`）
  - `APP:CLOSE`（v1.12；**CLOSE 专用强防抖 2.0s**——关闭后前台必变，防重复包连关第二个应用）
  - ⚠ 动作名不得含空格（会破坏 UDP 协议解析；webui 校验端已拒止）——带空格名称请用 bundleID
- T1 侧配置：`:8765 /keymap` Mac tab 下拉新增 6 项（t1_webui **v2.1**：TOGGLE/NEXT/微信/飞书/Obsidian/Safari；校验前缀放行）
- **实测（10-10 15:30-15:40，全程 front 对账）**：
  - 普通上下文：activate / toggle 前台切换成功（WorkBuddy ↔ 微信往返、NEXT→豆包、中文名激活均过）
  - **launchd 上下文（关键）**：key_bridge 调 app_switch `rc=0` 切换成功——**无 TCC 门控**（对照：键盘注入受投递身份门控）
  - 防抖实测：0.15s 内重复包被忽略；往返切换后 state 正确更新
  - webui 离线测试 **28/28**（含 6 项 APP: 新用例：接受/中文名/空后缀拒/空格拒/ATV 拒/choices）
- **真机验收（待用户）**：主页键（#102）已绑定 `APP:TOGGLE`（15:35 经 webui API 写入；全字段 diff **恰 1 处变更**，其余 203 字段零意外）
  - 当前切换基准：state = {cur: WorkBuddy, prev: 微信}——用户首次按主页键应切到微信（再按切回）
  - T1 落盘/热重载已就绪（voice_fwd 下一次按键自动热重载；无需重启服务）
  - 后续沿革：**16:56 改绑 `APP:CYCLE`**（v2.2；CYCLE 真机验收 ✅ 17:0x）；**17:42 改绑 短按 `APP:CYCLE` / 长按 `APP:PICK`**（v2.3；PICK 经用户实测多轮打磨——AppPicker 已迭代至 v1.3，见下节）

## ★ 应用选择器通道（v1.7，10-10 17:4x）——「主页键长按唤出」

**用户需求原话**：「主页键按住之后能不能用左右键选打开某一个应用？现在只能一个个轮询一遍，有点太麻烦了。」

- **触发**：T1 `voice_fwd` v2.3 长按（#102 `long=APP:PICK`，按住满 0.6s）→ `KEY APP:PICK DOWN` → 本服务
  `do_app("pick")` → `open -a AppPicker.app`（**已显示则忽略**；标志 = `/tmp/apppicker.sock` 存在）
- **路由**（选择器显示期间）：`LEFT/RIGHT/UP/DOWN/ENTER/ESC` 的 **DOWN** 经 UNIX dgram 转发给 AppPicker
  （**不注入系统**）；**UP 吞掉**（防裸 up 泄漏到前台应用）；socket 消失后 `PICKER_GRACE=1.0s` 内仍吞 UP 收尾
- **AppPicker.app**（源码 `remote-hub/AppPicker.swift`，Swift+AppKit 直接编译）：
  - `LSUIElement`（无 Dock 图标）+ `nonactivatingPanel`（**不抢前台焦点**）
  - 应用列表 = CGWindowList z-order（≈最近使用序；不足 2 个回退名称序）；网格图标+名称；**初始高亮第 2 个**（≈上一个应用）
  - 移动（**v1.2 网格导航**）：`↑/↓` = 垂直（相邻行同列优先; 该列缺失取最近列; 首/末行回绕另一端）; `←/→` = 行内线性环绕; 单行/单列退化为线性；`ENTER` = NSWorkspace 激活选中；`ESC` 取消；**10s 无操作自动取消**
  - 防双实例（socket 存在即退出）；退出必 `unlink` socket；日志 `/tmp/apppicker.log`
- **实测**：冒烟（7 应用显示/高亮移动/ENTER 激活访达/ESC 取消/socket 自清理）+ 端到端模拟
  （T1 形态 UDP 包 → pick 启动 → 路由 → 吞 up → ESC cancel，双端日志逐环对上）
- **v1.2（10-12）网格方向导航**：修用户实测「两行以上时 ↑↓ 也左右移动」——`gridMove` 逐语义对齐 Windows picker v2.4（`win_actions.grid_move`）；测试 = Swift 源码函数提取编译（`remote-hub/apppicker_grid_test.py`，33 用例全绿）；本机 socket 注入冒烟 5/5（DOWN 垂直/回绕、LEFT/RIGHT 线性）；前档 `AppPicker.bak-20261012-1250`；**用户复测 ✅ 10-12**
- **v1.3（10-12）长名滚动**：修用户实测「app 名称长的显示不全」——对齐 Windows picker v2.3+（`fit_prefix`/`cycle_slice` 语义）：非选中超宽名 = 像素预算内截断 + 「…」（极窄保底 1 字）；选中超宽名 = 「名称 + 3 空格」环形跑马灯（180ms/字符，切换选中从头部重滚）；预算 `NAME_BUDGET = CELL_W - 12`；实现 = `nameFont`/`measureName` + marquee DispatchSource + `.byClipping`
  - 测试：`remote-hub/apppicker_name_test.py`（Swift 源码提取，**16/16**）+ grid 回归 33/33；编译 `94765dd7…` 部署 ✅（socket 冒烟通过 + 截屏目视复核：浅灰底/蓝框/近黑字）
  - 备份：前档 `AppPicker.bak-20261012-1348`（= v1.2 `d10135a6…`）
- **真机验收**（10-10 面板功能 ✅；v1.2 网格导航 ✅ 10-12 复测；v1.3 长名滚动 🟡 待复验）：目标切 Mac → 长按主页键 ~1s → 面板 → 方向键选（↑↓ 垂直 / ←→ 横向；**长名选中自动跑马灯**）→ OK 打开（Esc/10s 取消）；短按主页键 = 仍为轮询

## ★ 焦点修复通道（v1.8，10-10 19:2x）——「跳输入框 / 切换后焦点修复」

**用户需求原话**：「有时候切换到窗口它无法获得焦点怎么办？没法输入到搜索框里头。有什么按键可以跳到输入框吗？」

- **背景**：macOS 14+ 应用激活存在「偶发静默丢弃」（`hs.application:activate()` / `AXFrontmost` 强推均实测失败）；
  Chromium/Electron 系应用（WorkBuddy/Obsidian）**AX 树不可靠**（前台仅 ~9/70 节点，输入框不在树里）；
  微信 = **AX 黑洞**（5 节点 + 24 探测点全 nil）。→ 原生 AX 遍历不足以解决，改用 **Hammerspoon + 坐标 hit-test**。
- **通道**：`FOCUS_INPUT`（UDP `KEY FOCUS_INPUT DOWN`）→ key_bridge v1.8（**线程内**执行, 0.6s 防抖, 不阻塞 UDP 循环）
  → `/opt/homebrew/bin/hs -c 'dofile("~/.hammerspoon/remotehub_focus.lua").focusInput()'` → AX 操作在 **Hammerspoon.app 内**执行
- **切换后自动修复**：`APP:*` 动作成功时（及 AppPicker v1.1 ENTER 激活后）异步调 `assistLater()`
  → hs 侧 `+0.45s` 执行窗口修复（unmin + AXMain + AXRaise + AXFocused）
- **三层策略 / 实现在 `remotehub_focus.lua`**（详见 `hammerspoon-focus.md`）：窗口修复 → 缓存点 → 坐标网格 → 树遍历兜底 → 设焦点读回
- **冒烟实证**（19:24，本机 UDP 注入）：
  `[focus] 跳输入框 OK | OK WorkBuddy role=AXTextArea fx=0.50 fy=0.85 src=cache before=true after=true`
- **T1 配套**：t1_webui **v2.5**（动作清单新增「★ 跳转输入框」）；mac 份 **#41 直播键**默认绑定该动作
- **已知局限**：微信等 AX 黑洞仅能做窗口级修复（无输入框级）；Chromium 系依赖坐标命中（布局大改后缓存点可能需重探）

## ★ CLICK 通道（v1.9，10-10 20:3x）——「点击当前焦点元素」

**用户需求原话**：「我把音量减号键定义成 TAB 键，通过这个 TAB 键可以切换到 WorkBuddy 的任务列表，但是切到焦点之后我摁回车键（也就是 OK 键），没法触发焦点，也就是说执行不了点击的命令。这个怎么解决？」

- **根因（实证）**：WorkBuddy（Electron）里 TAB 可达的焦点元素（任务条目 / 消息元素）**不响应合成回车**——
  组件未实现键盘激活；对照实验=模型选择器（AXComboBox）上合成 ENTER 有效（键注入本身无损）。
  **但这类元素几乎都支持 AX 层 `AXPress`** —— `performAction("AXPress")` 与真实鼠标点击**完全等效**
  （任务条目"统计模型用量"↔"接手zcode恢复t1" **往返双验证** ✅）。
- **通道**：`CLICK`（UDP `KEY CLICK DOWN`，**仅 DOWN 触发**，UP 忽略）→ key_bridge v1.9 `do_click()`
  （**线程内**执行, 0.6s 防抖）→ `hs -c 'dofile("~/.hammerspoon/remotehub_focus.lua").clickFocused()'`
- **四段策略 / 实现在 `remotehub_focus.lua` v1.1**（self `AXPress` → 直接子元素 → 向上 ≤6 层 → 坐标兜底+尺寸门槛；详见 `hammerspoon-focus.md`）
- **冒烟实证**（20:30-20:31）：
  `[click] 点击焦点元素 OK | OK press AXTextArea t= via=self`（输入框场景）
  + UDP 端到端 `RX -> KEY CLICK DOWN (已触发) → [click] OK`（发 `KEY CLICK DOWN` 模拟 T1）
- **T1 配套**：t1_webui **v2.6**（动作清单新增「★ 点击（激活当前焦点元素 · 任务/列表项）」）；
  voice_fwd v2.3 长按机制直接支持（`long=CLICK` 经 tick 触发转发）；**生产绑定 #28 OK 长按=CLICK**（短按回车不变）
- **使用**：TAB（音量-）切到任务/列表项焦点（焦点环亮起）→ **长按 OK（0.6s）** → 点击打开
- **已知局限**：个别元素 AXPress 无效也无有效坐标时报 FAIL（如右侧 1px 折叠 Artifact tab 子元素——边缘场景）；
  坐标兜底仅在无 AXPress 时启用（尺寸门槛防误点）

## ★ 翻页通道（v1.10，10-11 12:2x）——「PageUp / PageDown」

- **场景**：遥控器当翻页器——长按翻页（浏览长文档 / 列表 / 对话流）。
- **新增键表项**：`PAGEUP: 116` / `PAGEDOWN: 121`（macOS 原始 PageUp/PageDown 键码，无 Fn 修饰）。
- **通道**：与普通键盘动作**同一管线**（CGEventPost 主路径 + submit 兜底），无新机制；
  UDP 冒烟：`KEY PAGEDOWN DOWN` → `[serve] key PAGEDOWN(121) down OK` ✅（PAGEUP 116 同理）。
- **T1 配套**：t1_webui **v2.8**（动作清单/下拉新增「★ 上一页 / ★ 下一页」）；voice_fwd v2.3 长按机制直接支持，无需改动。
  **生产绑定（mac 份，现网）**：**#114 音量-长按 = PAGEDOWN**（下翻）/ **#115 音量+长按 = PAGEUP**（上翻）——单击行为均不变。（v1.10 部署初版曾为 #41 长按 = PAGEDOWN，后调整至 #114；win 份已同构对齐）
- **使用（现网）**：**长按（0.6s）** 音量- = 下一页；**长按** 音量+ = 上一页。
- 注：#127 菜单键因 `repeat=true`（连发与长按互斥，校验端清 long）未能采用，改用空闲长按位的 #41/#115。

## ★ URL / RUN 通道（v1.11，10-11 21:5x）——「打开网页 / 执行命令」

- **场景**：遥控器当万能键——一键打开某网址（仪表盘/网课/文档）、一键跑某命令（脚本/快捷动作）。
- **协议**：`KEY URL:<网址> DOWN` / `KEY RUN:<命令> DOWN`——**仅 DOWN 触发**（UP 忽略）；
  **per-value 防抖 0.6s**（重复 DOWN 同值忽略，不同值立即放行）；**值不含空格**（UDP 空格分词硬约束）。
- **实现（key_bridge.py v1.11）**：
  - `URL:<网址>` → `open <网址>` 拉起默认浏览器（per-url 防抖表 `_url_last`）；
  - `RUN:<命令>` → `/bin/sh -c <命令>` 后台执行（per-cmd 防抖表 `_run_last`；cwd=用户主目录）；
  - 错误路径全部捕获记日志（不崩、不阻塞注入主循环）。
- **T1 配套**：t1_webui **v2.10**（「打开网页…/执行命令…」入口 + 校验）；voice_fwd v2.3 通用透传无需改动。
- **实弹验证**（22:0x）：`KEY RUN:touch /tmp/...` 探针执行 ✅（首跑一次未落盘为瞬态，留观察项）；
  `KEY URL:https://example.com` → Safari 置前台 ✅；防抖/UP 忽略 ✅（`[key_bridge] URL ...` 日志）。
- **同类交付**：Windows 侧 win_receiver v1.5（大小写保真）+ win_actions v1.2/1.3 同构实现（随
  `update-win-receiver.ps1` v1.5 一并分发）。

## ★ 关闭当前应用通道（v1.12，10-12 14:0x）——「长按电源键关闭」

- **场景**：远程「关掉眼前的应用」——长按电源键（#116）≥0.6s 触发 `APP:CLOSE`（Mac + Windows 双端对等）。
- **协议**：`KEY APP:CLOSE DOWN`（UP 无动作；**CLOSE 专用强防抖 2.0s**——关闭后前台必变，
  防重复包连关第二个应用；对齐 Windows win_actions v1.10 `debounce_for`）。
- **实现（key_bridge.py v1.12）**：`do_app` 路由 `close` → `app_switch close`；
  **免 focus assist**（关闭动作无「切换后修复焦点」需求）；返回详情进日志。
- **app_switch v1.2 `close`**：`NSWorkspace.frontmostApplication.terminate()`（= 优雅退出，
  等价 Cmd+Q——应用走自身保存/确认流程，不丢数据；**Finder 为系统组件，拒绝关闭**）；
  输出 `OK close -> <名称> [bid] pid=N` / `FAIL close: terminate() 被拒 -> …`。
- **T1 配套**：keymap v2 三份 `#116.long = "APP:CLOSE"`（单击仍为 `APP:workbuddy`；长按由
  voice_fwd v2.3 状态机独立触发，**与单击严格互斥**、无双触发）；t1_webui **v2.11**
  （下拉含「★ 关闭当前应用（长按电源键）」+ extLabel 文案特判）。
- **实测（10-12）**：生产路径 `KEY APP:CLOSE DOWN` → TextEdit 关闭 ✅
  （`[app] CLOSE OK rc=0 | OK close -> 文本编辑 [com.apple.TextEdit] pid=45277`，1.5s 后进程已退出）。
  注：WorkBuddy shell 沙箱内直接运行 `app_switch close` 的退出请求会被拦截（返回 true 但未送达，
  且进程呈半死态）——**生产路径（key_bridge launchd 上下文）不受影响**。
- **同类交付**：Windows `win_actions` v1.10（`WM_CLOSE` 优雅关闭 + UWP 真身子窗口 + shell 拒绝；
  随 `update-win-receiver.ps1` 分发，施工单 `windows/TASK-close-app.md`）。

## CGPost.app（注入器，v0.2，冻结）

- 路径：`remote-hub/CGPost.app/Contents/MacOS/cgpost`（源码 `cgpost.c`）
- ⚠ **勿改名/移动/重编译**——TCC 按「App Bundle 身份（Bundle ID 级记录）」匹配；改动前先读 cgpost.c 头注冻结约定
- serve 协议：`KEY <kc> <0|1>` → `OK\n`；`PING` → `PONG v2\n`；`STATUS` → 权限行；  
  实例探测（connect+PING 300ms → 已有实例则退出，防双开）
- 授权：辅助功能列表（`CGRequestPostEventAccess()` 从 launchd 上下文**静默不弹窗**，必须用户手动加入）
- 历史沿革（为什么从 iohid_post 换过来）：
  - **v1.2**（12:33）：裸键从 IOHIDPostEvent 改走 CGEventPost —— **IOHIDPostEvent 对裸键 kr=0 但事件不进系统事件流**  
    （监听器 14s 零捕获；修饰键/flags 形态才有效，语音链 ropt 注入不受影响）
  - **v1.3**（12:58）：裸二进制 cgpost 被 macOS 26/27 TCC 拒（`Failed to match existing code requirement`——  
    「手动＋添加」的裸二进制记录无法与进程匹配）→ 换 **App Bundle 形态**后 launchd 上下文 **PostEvent/AX/Listen 三项全 1** ✅
  - cgpost 是**独立新二进制**（未动 iohid_post——其 TCC 绑 cdhash/路径，动了会毁语音链）

## 诊断（serve 客户端已归档 `remote-hub/cgpost_cli.py`）

```bash
python3 remote-hub/cgpost_cli.py PING            # → PONG v2
python3 remote-hub/cgpost_cli.py STATUS          # → 权限行
python3 remote-hub/cgpost_cli.py "KEY 107 1"     # 手动发键 DOWN
# serve 崩溃急救：launchctl kickstart -k gui/501/com.remotehub.cgpost-serve
```

## 版本时间线

| 版本       | 时间        | 变更                                                 |
| -------- | --------- | -------------------------------------------------- |
| v1.0     | 02:24     | 初版：launchctl submit → `iohid_post key <nxkc> 0\|1` |
| v1.1     | 12:2x     | 排障增强（注入日志捕获 + RAW 探针）                              |
| v1.2     | 12:33     | 裸键 IOHIDPostEvent 失效 → cgpost（CGEventPost）         |
| v1.3     | 12:58     | 裸二进制 TCC 被拒 → CGPost.app App Bundle 形态（用户手动授权）     |
| **v1.4** | **13:1x** | **serve 常驻主路径 + 15s 熔断 submit 兜底**（16/16 零丢失；验收通过） |
| v1.5     | 15:3x     | 应用动作通道（`APP:TOGGLE/NEXT/<名称>` → app_switch；真机验收 ✅ 16:44）   |
| v1.6     | 16:5x     | `APP:CYCLE` 全应用轮询（主页键 #102 改绑；CYCLE 验收 ✅ 17:0x）              |
| **v1.7** | **17:4x** | **`APP:PICK` 应用选择器 + picker 按键路由**（长按主页唤出；用户实测使用中，AppPicker 已随之迭代至 v1.3） |
| **v1.8** | **19:2x** | **焦点修复通道：`FOCUS_INPUT` 跳输入框 + APP 切换后 assistLater**（Hammerspoon/AX；冒烟过，真机验收 ✅ 19:43） |
| **v1.9** | **20:3x** | **`CLICK` 点击当前焦点元素**（`clickFocused()` 四段策略；UDP 冒烟 ✅ 20:31；生产绑定 #28 OK 长按=CLICK） |
| **v1.10** | **10-11 12:2x** | **翻页键表：`PAGEUP(116)` / `PAGEDOWN(121)`**（UDP 冒烟 ✅；初版绑定 #41 直播长按=PAGEDOWN / #115 音量+长按=PAGEUP——**后下一页调整至 #114 音量-长按**） |
| **v1.11** | **10-11 21:5x** | **`URL:<网址>` / `RUN:<命令>` 动作**（仅 DOWN 触发 + per-value 防抖 0.6s；launchd kickstart 重启 ✅；实弹：RUN 探针 / URL 开浏览器 ✅） |
| **v1.11 修订** | **10-12** | **VERSION 常量单一来源化**（banner/STATUS 共用；修 STATUS 残留 v1.8 → 重启生效实测 `STATUS v1.11` ✅；前档 `.bak-20261012-1348-preVersionFix` = `03042dcd…`） |
| **v1.12** | **10-12 14:0x** | **`APP:CLOSE` 关闭当前应用**（长按电源键生产绑定；app_switch v1.2 `close`；CLOSE 强防抖 2.0s + 免 focus assist；launchd kickstart 重启 → `STATUS v1.12` 实测；生产路径实弹 TextEdit 关闭 ✅） |
| **v1.13** | **10-13 13:1x** | **鼠标模式 `MOUSE:*` 分支**（MOVE / SCROLL / LCLICK / RCLICK → lua v1.2 鼠标执行器；串行 worker 保序；`mouse_channel_test.py` 8 PASS（真实光标）） |
| **v1.14** | **10-13 14:2x** | **`MOUSE:MODE:ON\|OFF` 模式 HUD 后端**（→ lua v1.3 `mouseHud`；仅 DOWN；全链冒烟 `OK hud on/off` ✅；配套 voice_fwd v2.6 —— 治用户首测「按了不知道生效没有」） |
| **v1.15** | **10-13 15:2x** | **`TARGET:SWITCH:ATV\|MAC\|WIN` 设备切换 HUD 后端**（→ lua v1.4 `switchHud`；仅 DOWN；复用鼠标串行 worker，日志 tag 区分 `[hud]`/`[mouse]`；lua 实机应答 `OK hud switch:win` ✅；配套 T1 voice_fwd v2.7 / relay_min v0.11 电源键连击） |

备份：`key_bridge.py.v11.bak-20261010-1233`（iohid_post 形态）/ `key_bridge.py.v12.bak-20261010-1258`（指向裸 cgpost，授权不生效，仅留档）/ `key_bridge.py.v15.bak-20261010-1649`（v1.5 前档）/ `key_bridge.py.v16.bak-20261010-1748-rebuilt`（v1.6——升级时漏备份，后从会话存档的 8 个 v1.7 编辑对反向重建，经"版本标记+编译+往返回溯"三重校验）/ `key_bridge.py.v17.bak-20261010-1748`（v1.7 上线后字节快照 = v1.8 前档；经 diff 全量核验「差异仅 v1.8 专属」）**/ **`key_bridge.py.v18.bak-20261010-2035-rebuilt`（v1.8——升级 v1.9 时漏存快照，20:35 从 v1.9 反向重建：8 步替换全断言命中 + 语法 OK + 零 CLICK 残留 + 与 v1.7 全量 diff「差异仅 v1.8 专属」双重校验）** / `key_bridge.py.v19.bak-20261010-2035`（v1.9 上线后字节快照，md5 `256a4276…` 与运行版一致）** / `key_bridge.py.v110.bak-20261011-1224`（v1.10 上线后字节快照，banner 键表 11 项）** / `key_bridge.py.v111.bak-20261011-2212`（v1.11 上线后字节快照；v1.11 前档 = `.bak-20261011-2157-preUrlRun`，与 v110 快照同哈希 `db47a8de…`）** / `key_bridge.py.bak-20261012-1348-preVersionFix`（VERSION 单一来源化前档 = `03042dcd…`）；AppPicker 前档 `AppPicker.bak-20261010-1930`、**`AppPicker.bak-20261012-1250`（v1.2 前档 = v1.1 `a2f0ac6c…`）**、**`AppPicker.bak-20261012-1348`（v1.3 前档 = v1.2 `d10135a6…`，sha256 `f42b3528…`）**；AppPicker v1.3 现网 `05c0c19e…`（备份链 v1.0→v1.3 四代经 nm 符号表逐代核验）；**`key_bridge.py.bak-20261012-1358-preV112`（v1.12 前档 = v1.11 终版——逆向重建，与 `.bak-20261012-1348-preVersionFix` 快照全量 diff「仅剩 VersionFix 3 处」精确获证）；key_bridge **v1.12 现网 `d4977ee3…`**；app_switch **v1.2 二进制 `0f0a5294…`**（前档 `app_switch.v11.bak-20261012-1357` = v1.1〔133808B〕；源码重建 `app_switch.swift.v11.bak-20261012-1358` 编译冒烟通过）；`close_app_test.py`（18 项 / 双解释器 3.9+3.13 各 18/18）`1ab965f0…`**

## 部署记录（2026-10-10 13:12-13:15）

1. `com.remotehub.cgpost-serve.plist` 写入 `remote-hub/mac-launchd/` + `~/Library/LaunchAgents/`
2. bootstrap 经 SSH 本机会话绕过（WorkBuddy shell 直连报 `5: I/O error`）：  
   临时 key → `ssh -i … username@localhost 'launchctl bootstrap gui/501 <plist>'` → rc=0, running  
   （**该临时 key 已于收尾清理**；需要时按此流程重建）
3. key_bridge v1.4 经 `launchctl kickstart -k` 重载（KeepAlive 自愈路径同验）

## 验证记录（全过 ✅）

- 端到端 A：serve 路径 8 键序列 **8/8 全捕获**（监听器无丢失）
- 熔断 B：打停 serve → `[submit兜底]` rc=0 注入成功 → 恢复 serve 后自动回主路径
- 自愈 C：`kill -9` serve → KeepAlive ~4s 重启（pid 变更、`(never exited)`）
- 16/16：四组 down/up（0.05~0.4s 间隔）全部捕获（serve 形态关键实证）
- **真机验收**（13:24）：遥控器 ENTER down/up 序列进日志，用户确认全通过
- 跨机：T1→Mac:8791 ping/pong 通；`status` = `serve=up`

## ★ 组合键能力调查（Task#30，2026-10-10 14:00–14:25）——结论：用户态全路线否决 ❌

**起因**：用户提出「按键只能绑定有限的几个键值……需要按某个键打开应用、发常用组合键（如 Cmd+Shift+X）」。  
**本调查只回答一个前提问题**：现有注入通道（cgpost serve / iohid_post）能否合成**组合键**（修饰键+主键）？  
**结论**：不能。**单裸键（现行 v1.4 通道）完好；组合键经五条用户态路线全部实证否决**——机制根因 =  
应用/系统的**快捷匹配读取真实修饰键状态机（HID report 驱动 / 硬件寄存器）**，纯合成事件只能伪造事件流的  
flags 字段，无法伪造状态机本身。

### 五路线否决表（全部实测，非推断）

| # | 路线                         | 做法                                                                    | 结果                                                                                                             | 铁证                                                                                                                                               |
| - | -------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| α | 纯序列（cgpost serve）          | 发「⌘down → 主键 down/up → ⌘up」键盘事件序列                                     | ❌ 修饰键**不更新 HID 状态机**（`CGEventSourceFlagsState` 全程无 CMD 位）；主键被当**裸字符**打入（输入法候选条实锤 "ac"、"W|v"）                   | `keylisten1/2.txt`：`type=10 key=9 flags=[]`（flags 全空）                                                                                            |
| β | iohid_post 持有变体            | HID 层 KEYDOWN/FLAGSCHANGED 的 rcmd-hold                                | ❌ HID 层修饰键同样立不起状态机；**副产品：FLAGSCHANGED 事件能清除残留 flags 位**（0x20000000 神秘位消失实证）                                    | `cg_state_probe.py` 采样全程 Cmd_L=0                                                                                                                 |
| γ | 虚拟 HID 设备（IOHIDUserDevice） | 新建虚拟键盘设备写 HID report                                                  | ❌ OS 策略封死：`IOHIDUserDeviceCreateWithProperties` 创建失败（shell/SSH 均败，非沙箱）；加 entitlement 签名后进程 **SIGKILL（rc=137）** | `vhid_test.c` / `vhid_ent.plist`                                                                                                                 |
| δ | CGEventPost 带显式 flags      | 重编译 iohid_post 加 `gkeyf`/`gcombo` 模式（`CGEventSetFlags`+`CGEventPost`） | **半通半败**：事件**携带完整 flags 进入系统事件流**（监听器实锤）但**应用层快捷匹配不触发**（全合成 ⌘+⌃+⇧+3 系统截屏热键亦不响应）→ 匹配读的是**真实状态机**，非事件 flags 字段   | `keylisten3.txt`：`type=12 key=55 flags=[CMD] srcPid=74004` → `type=10 key=9 flags=[CMD]` → `type=11` → `type=12 flags=[]`（完整序列上线，TextEdit 静默无粘贴） |
| ε | System Events 按键自动化        | `keystroke "v" using command down`（osascript）                         | ❌ `-10004 权限违例`（需 GUI 授权的自动化权限）；换新标记复测确认通道不可用（首测一次哨兵命中为巧合，不采信单次结果）                                             | 复测无第二次粘贴（MARKER2-888）                                                                                                                            |

### 附带收获（跨任务复用）

- **★ TCC 对 CGEventPost 的投递身份门控**：`/tmp` 下新建测试二进制（cgpost2）`CGPreflightPostEventAccess=1`  
  但**事件根本不上线**（监听器零捕获）；launchd 上下文的白名单资产（`cgpost serve`）正常上线。  
  → **投递能力绑定「已授权进程身份」，preflight 查询结果不算数**。
- **★ iohid_post 路径授权耐受重编译**：加 gkeyf/gcombo 模式重编译后 `check` 仍 `PostEvent access = 0 (granted)`  
  ——**路径型 IOHID PostEvent 授权与 cdhash 无关**（对照：CGPost.app 为 Bundle ID 型授权，重编译有毁授权风险，仍维持冻结）。  
  这是本轮**首次突破"不重编译"边界**（先备份 sha256 留档）。
- 修饰键状态机 vs 事件 flags 的分离 = 组合键合成不可行的机制级根因（见上）。

### iohid_post 现状（变更留档）

- 已上线**带 gkeyf/gcombo 扩展**的重编译版（原位、授权存活已验证）；两模式保留（供诊断类用途），日常生产仍走 cgpost serve。
- 回退：`iohid_post.bak-20261010-precombo`（sha256 `81db49dd…8ce23`，原件完好）。
- 用法：`gkeyf <nxkc> <0|1> <flags>`（单键带 flags）/ `gcombo <mainkc> <modflag> [gap_ms]`（⌘down→主键→⌘up 带 flags）  
  ——**注意：对真实应用无效**（δ 结论），仅可用于事件流/监听器类诊断。

### 对「按键动作扩展」设计的分流结论（回答用户原始问题）

- `APP:<目标>`（打开应用）/ `URL:<链接>` / `RUN:<命令>`：**不受本调查影响，全部可做**——用 `open -a` / `open` / 脚本实现，**不需要按键注入**。
- `COMBO:<MOD+KEY>`（组合键）：**用户态三通道全闭**。若必须，仅剩三条重路线（均需用户裁决）：
  1. **GUI 授权 System Events**（ε 复活）——用户在「系统设置→隐私与安全性→自动化」手动授权；能力受自动化 API 限制、注入身份依赖 osascript；
  2. Apple `com.apple.developer.hid.virtual.device` entitlement 申请（需开发者账号 + Apple 审批，不现实）；
  3. 驱动级方案（Karabiner-Elements / Hammerspoon 式，需系统扩展权限，重）。

### 证据索引

`attic/combo-investigation-20261010/`（8 文件）：`cgpost2.c`（TCC 身份门控实证件）/ `vhid_test.c` + `vhid_ent.plist`（γ 路线与 SIGKILL 实证）/ `iohid_post_test.c` / `combo_seq_test.py`（序列注入+防悬挂测试工具）/ `keylisten1/2/3.txt`（三轮监听器原始数据）。

## v1.13 鼠标模式（MOUSE:* — 遥控器 dpad 模拟鼠标；2026-10-13）

**语义**（T1 `voice_fwd` 模式层产生——v2.5 引入 / v2.6 补模式 HUD 提示与电源·主页放行；长按直播键 #41 开/关）：

| 动作 | 语义 | lua 调用 |
|---|---|---|
| `MOUSE:MOVE:UP/DOWN/LEFT/RIGHT` | 滑行移动（**按住**：DOWN 启动 / 保活刷新 / UP 停止） | `mouseStart/mouseStop("<dir>")` |
| `MOUSE:SCROLL:UP/DOWN` | 连续滚动（同上 hold 语义） | `scrollStart/scrollStop("<dir>")` |
| `MOUSE:LCLICK` / `MOUSE:RCLICK` | 当前光标位置点击（**仅 DOWN**） | `mouseClick("left"/"right")` |

**实现要点**：
- 路由：`name.startswith("MOUSE:")` → `mouse_dispatch`（收包线程仅入队, µs 级）→
  **专用串行 worker**（顺序敏感: start/保活/stop 不可乱序; 队列满丢弃 —— 保活语义天然容丢,
  UP 丢失由 lua 侧 1.2s 看门狗兜底刹车）。
- 执行：`hs -c 'dofile("~/.hammerspoon/remotehub_focus.lua").mouseStart("up")'` ——
  鼠标状态挂 `_G.REMOTEHUB_MOUSE` 单例跨 hs 调用存活（hs CLI 每次重新 dofile）。
- 滑行参数（与 Windows 端逐条对齐）: 加速 700px/s² / 上限 1600px/s / 60Hz / 1.2s 无刷新
  自停 / 多方向叠加不归一化（斜向 √2 速）/ 字符键「轻点=精准微调」（速度自 0 线性加速）。
- T1 侧保活节奏 **0.4s**（`MOUSE_KEEPALIVE`, 3 倍于看门狗窗口）—— 掉线/断流即自动刹车。
- 不做防抖: 重复 DOWN = 保活刷新（幂等）; UP = 配对刹车（不可去重）。

**测试**：逻辑层 `_mouse_cmd` 映射 12 例（key_bridge）；lua 执行器 **12 PASS**（`mouse_channel_test.py`，含 v1.3 `mouseHud` 段）;
**UDP→key_bridge→hs→真实光标端到端 8 PASS**（2026-10-13: 右移实测 126px@0.6s、松开即停、
看门狗自停、点击/滚动实执行、非法方向优雅忽略）。

## 排障要点（★ 方法论，2026-10-10 事故复盘）

- **发现不对劲 → 先截图**：`screencapture` 必须在**沙箱上下文**执行（ssh 链无屏幕录制权限 →  
  `could not create image from display`）；区域放大 `screencapture -R x,y,w,h`
- **操作 GUI 前先验证前提**：目标 App 是否前台（`NSWorkspace.frontmostApplication` / 截图确认）——  
  曾盲操作事故：System Settings 未前台时其对话框无键盘焦点，合成按键全被前台 app 消费（用户严厉纠偏：  
  「先要判断操作前提是否成立」）
- 注入无效分层排查：① T1 日志 `KEY 28 -> mac ENTER`（转发）② key_bridge.log 收包 + `[serve]…OK`  
  ③ serve 日志 `CGEventPost(key=…, DOWN) 已投递` ④ 监听器实测事件进流
- TCC 条目维护：辅助功能列表中本链条 **仅需 2 条**——`CGPost.app`（开）+ `iohid_post`（开，语音链用）。


⚠ **勿用「移除」自动化批量清理**——曾连带误删 iohid_post（机制：删除作用于「当前选中集」，残留/自动迁移的  
额外选中行会被连坐；恢复法：「＋添加」→ 打开对话框 → `Cmd+Shift+G` 粘路径 → Return ×2；  
防复发校验要求见 `attic/tcc-cleanup-tools-20261010/tcc_remove.swift` 头注）

## 回滚

```bash
# A) 停用 serve（v1.4 自动降级：熔断后全走 submit 兜底，无需改代码）
launchctl bootout gui/501/com.remotehub.cgpost-serve 2>/dev/null; true
#    重新启用 = SSH 本机会话 bootstrap（见「部署记录」）
# B) 回滚注入器到 iohid_post 形态（裸键在其上不可用，仅历史留档）：
#    key_bridge.py.v11.bak-20261010-1233（BIN=iohid_post）
# C) 整链停用（T1 侧无需改动：target≠mac 时 voice_fwd 不会向 8791 发）
launchctl bootout gui/501/com.remotehub.key-bridge 2>/dev/null; true
```

## 已知边界 / 后续

- **组合键（⌘+X 类）用户态不可行 ❌**（Task#30 全路线否决，见上节）；动作扩展分流：`APP/URL/RUN` 可做（无需按键注入），`COMBO` 待用户裁决
- mac 份长按自 10-10 v2.3 支持（如主页键：短按 `APP:CYCLE` / 长按 `APP:PICK`）；双击仍不支持；音量键暂无键盘注入方案（需媒体键 NX_SYSDEFINED，后续按需）
- 修改键表需同步两处：本文件 `KEYMAP` + T1 网页动作清单（`t1_webui.py: KB_ACTIONS/KB_CHOICES`）
- **FOCUS_INPUT / 焦点修复**（v1.8）：依赖 Hammerspoon 常驻 + `hs.ipc`（详见 `hammerspoon-focus.md`）；hs 不在时仅 `[focus] FAIL` 记日志，不影响按键主链路
- **Windows 侧同构链路 ✅ 已上线**（10-11 接线：`voice_fwd.py: WIN_IP=WINDOWS_IP`；接收端 `win_receiver` v1.6 + `win_actions` v1.10）——按键注入 + 语音音频链（麦克风按需切换 v1.3）均已实机验收；win 键位与 mac 100% 对齐（非待办）
