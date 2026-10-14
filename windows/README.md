# Windows（Windows）链路维护笔记 — 2026-10-14 v1.11 心跳 + v1.15 兜底点击 + v1.16 app 观测版

> 状态：**按键链 ✅**（T1 `voice_fwd.WIN_IP=WINDOWS_IP` 生效；PING 双口 PONG）；
> **语音音频链 ✅**；**扩展动作 v1.2 ✅ 已实机验收**（4/4；「最小化→还原」前台修复已合入上游）；
> **麦克风按需切换 v1.3 ✅ 已实机验收**（用户实测：按语音键→默认设备跳 CABLE Output、
> 松开 2s 自动跳回；本机直接 Ctrl+Win 不受影响）；
> **win_actions v1.10 ✅ 已上线并实测通过**（2026-10-12 14:22 用户实测：「Mac和Windows都测试了，基本没发现什么问题」；升级链 = 14:17:53 用户侧双击 bat 自助拉取。自 v1.7 起累积交付：v1.8 灰调配色〔用户侧部署确认 ✅〕/ v1.9 选中格图标融合 / **v1.10 ★ 长按电源键关闭当前应用**；含图标网格 + 崩溃根治 + 高 DPI + 光学尺寸归一 + 单元格固定尺寸 + 长名滚动 + 网格方向导航 + UWP 真实图标 + GUID 修复〔上游已含, 不会再被覆盖〕）；
> **v2.4 = 用户验收 ✅**（2026-10-12 实测：「Windows 上测试已经通过，新版的 Mac 任务栏菜单测试也正常了」；GUID 修复合入后 288/288、零新补丁）；
> **v2.3 = Windows 实机验收 ✅**（2026-10-11 23:51 报告：深炭配色 /「Windows …」静态截断 / 跑马灯 4 帧实拍 / 验收零新补丁；用户反馈「感觉好多了」）；
> **v2.2 = Windows 验证「理想收敛轮」✅**（其报告逐行核对确认上游已合入全部旧补丁、三件哈希一致、无需再打补丁）；
> **URL:/RUN: 扩展动作已交付**（T1 网页台 v2.10 可绑「打开网页…/执行命令…」）；
> **win 键位已与 mac 100% 对齐**（10-11 21:31，全量 diff=0：补 #28 长按 CLICK / #41 FOCUS_INPUT / #116 APP:workbuddy）。
> v1.11 更新以用户侧部署为准（推荐双击 `update-win-receiver.bat`）；T1:8000 分发 server 保留备用。
> **★ 鼠标模式（win_receiver v1.9 + win_actions v1.13）= ✅ 已上线 + 用户复测通过**（2026-10-13：
> 13:29 经 RUN 通道「零到场」远程升级（v1.7+v1.11）→ 用户实测报五问 → 同日三轮升级修复
> （v1.8+v1.12 → v1.9+v1.13）；**元凶 = 跨模块 SendInput 类型冲突**（两模块各定义 INPUT 类
> 共享 `ctypes.windll.user32`，argtypes 互相覆盖 → 鼠标点击/滚轮全静默失败；探针 `EXC TypeError`
> → 修复后 `ok(1)` 实证）；**15:1x 用户复测：鼠标速度正常 / OK 长按右键 / 主页 / 返回 全部 OK**）。
> **★ 设备切换 HUD（win_receiver v1.10 + win_actions v1.14）= ✅ 已上线 + 用户复测通过**（2026-10-13 15:1x：
> T1 电源键连击（1 击=ATV / 2 击=Mac / 3 击=Win）时本机弹「🎯 已切到 X」浮层；走 MOUSE:* 同通道；
> 15:4x 用户复测「可以切换了」）。
> **★ FOCUS_INPUT 兜底点击（win_actions v1.15）= ✅ 已上线**（2026-10-14 03:16 经 RUN 通道升级 +
> 03:18 端到端实证 `NOEDIT+CLICK@1920,1987 [winfix=raise app=lockapp.exe]`；详见下方 v1.15 节）。
> **★ presence 心跳（win_receiver v1.11）= ✅ 已上线**（2026-10-14 04:42 经 RUN 通道零到场升级；单代理报
> voice/key/audio 至 T1 :8790——T1 侧离线闸门 + 去硬编码 IP；`presence_beat.py` 随 update 脚本分发。
> **注意**：主档在 `remote-hub/presence_beat.py`，改后需同步本目录副本（随 8000 分发到 Win）。
> **★ win_actions v1.16 = ✅ 已上线**（2026-10-14 15:45 经 RUN 通道零到场升级〔第 6 次〕：
> `do_app_activate` 观测日志补强；四证闭环 = sha256 逐字节一致 + VERSION=1.16 + 进程重启 + selftest 全绿）。
> 鼠标模式 = 遥控器长按直播键切换：方向=滑行移光标 / OK 短=左键·长=右键 / 音量±=滚动 / 返回=退出
> / 模式内**电源·主页照常可用**（可随时跳出去打开应用）/ 开·关·模式内单按均弹 **HUD 浮层提示**
> （T1 `voice_fwd` v2.6 发 `MOUSE:MODE:*`；Mac 对等端 lua v1.3 + key_bridge v1.14 同日上线）。

## v1.16 变更（2026-10-14 15:4x）—— `do_app_activate` 观测日志（聚焦键最终落点可视，零到场第 6 次）

- **背景**：10-14 凌晨 FOCUS_INPUT 排查曾因 `do_app_activate` 无文件日志而无法判定「前台是谁」
  （v1.15 已加 `app=` 结果字段）——本轮把**激活动作本身**也补上落盘观测，闭合最后可观测性缺口。
- **变更**：`do_app_activate` 两处补 `_logv`——成功路径
  `app-activate '<q>': front=<k> -> <key> ok=<bool>`／未运行路径
  `app-activate '<q>': front=<k>, not-running -> launch`（均含 `front=` 当前前台键）。
- **测试**：`actions_offline_test.py` **462/462**（+3：v1.16 变更块 / app-activate / front 观测；
  版本守护断言同步 1.15→1.16）。
- **部署取证**：15:45 经 RUN 通道升级——post 指纹 `win_actions.py sha256=7CF0A6E6…` + 回传
  `VERSION = "1.16"` + 进程重启（`pid=23520 pythonw.exe`）+ `win_actions v1.16 loaded (uia=ready)`
  + selftest 全绿，四证闭环。

## v1.11 变更（2026-10-14）—— presence 心跳（在线注册 / T1 侧离线闸门）

- `presence_beat.start("win", [("voice",8788), ("key",8791), ("audio",8789)])` —— 启动即拍、
  每 2s 向 T1 :8790 注册（ACK/退避由库处理）；首拍即让 T1 学习本机 IP。
- T1 侧（voice_fwd v2.9 / atvv_service v1.2）据此：设备离线→暂停投递（消灭「假已发送」）、
  投递地址心跳 IP 优先（DHCP 变更自动跟上）；网页台主页可看在线状态点。
- 单代理形态（对齐 Mac presence-beater）：本进程代报全部 svc。
- 配套分发：`update-win-receiver.ps1` 增载 `presence_beat.py`（3 文件 → 4 文件）；加载失败
  仅降级「无心跳」，主链路不受影响。
- 测试：actions 459 / offline 22 / smoke 28 全绿；04:42 升级后 post 指纹 sha256 逐字节一致
  + T1 侧「win 上线」日志实证。

## v1.15 变更（2026-10-14）——★ FOCUS_INPUT 兜底点击（微信类应用可用）+ app 观测

- **背景（用户反馈）**：「无论在 Mac 还是在 Windows 上，鼠标模式下按焦点聚焦键不灵、不好使，
  甚至切换到键盘模式，焦点还是不好用」。直注实测：chrome / WorkBuddy / explorer / lockapp
  **四应用全部 `NOEDIT`**——不是微信特例，而是五段策略（窗口修复/缓存/网格/树）全 miss 后
  **无兜底动作**的普适缺陷（Win 侧根因；Mac 同源缺陷在 lua v1.5 同步修复 → **v1.6 深挖再修正：
  前台提升防遮挡 + 兜底落点距窗底 105px**，见 `hammerspoon-focus.md` 沿革 v1.6；
  鼠标模式内 #41 被 T1 吸收是另一根因，在 T1 voice_fwd v2.8 修复）。
- **win_actions v1.15**：五段全 miss（`elem is None`）时改为**底部中央兜底点击**
  （`(l+int(w*0.5), t+int(h*0.92))` —— 聊天/评论类输入区几何假设；y 钳制不超过 `b-4`），
  返回 `NOEDIT+CLICK@x,y (未找到输入框, 已兜底点击)`；点击失败则如实返回普通 `NOEDIT`（不谎报）。
  测试打桩可经新增第 4 参数 `click_at=None` 注入（None=旧行为，向后兼容）。
- **`_click_preserve_cursor(x, y)`**：兜底点击包装——点击前记录光标 → `mouse_click` → 恢复原位置
  （遥控器操作不应留下光标可见位移）。
- **`do_focus_input` 结果串新增 `app=<exe>` 观测字段**：治「NOEDIT 时不知道前台是谁」——
  `do_app_activate` 无文件日志，10-14 凌晨 03:03 四轮直注曾无法判定前台（教训登记）。
- **测试**：`actions_offline_test.py` **459/459**（+11 条：F2 全 miss 兜底点击 + 坐标 /
  F3 点击失败如实返回 / F4 矮窗 y 钳制 + §22 源码约定守护 7 条）。
- **部署取证**：03:16:5x 经 RUN 通道升级（pre/post 指纹 `win_actions.py size=143055` +
  `VERSION = "1.15"` + `win_actions v1.15 loaded (uia=ready)`）；03:18:32 端到端实证
  `EXT FOCUS_INPUT -> FOCUS_INPUT NOEDIT+CLICK@1920,1987 (未找到输入框, 已兜底点击) [winfix=raise app=lockapp.exe]`
  （锁屏态 3840×2160 虚拟屏 → 0.92 高度坐标 1987 正确 / `app=` 字段生效 / 新路径贯通）。
- **配套版本**：T1 `voice_fwd` v2.8（模式内 #41 放行 + 实时目标）+ Mac `remotehub_focus.lua` v1.5
  （同款兜底点击 `(0.5, 0.92)` + 光标恢复）→ **v1.6**（前台提升 + 距底 105px；Win 侧是否对称调整
  兜底坐标待用户复测后定）。

## v1.10 + v1.14 变更（2026-10-13）——电源键连击切换设备（HUD）

- **背景**：用户提出「每次在几个设备之间切换用网页还是有些麻烦」→ T1 电源键连击直切
  （**1 击=ATV / 2 击=Mac / 3 击=Win**；voice_fwd v2.7 / relay_min v0.11 双侧连击层；
  电源键短按原绑定「打开 workbuddy」不再保留，长按=关闭应用不变）。
  切到本机（win）、或从 win 切走（切到 atv 时提示发「旧目标端」）都会收到 `KEY TARGET:SWITCH:<X> DOWN`。
- **win_receiver v1.10**：`handle_key` 的 `MOUSE:*` 专用路由扩为 `("MOUSE:", "TARGET:SWITCH:")`
  双前缀——同通道直呼 `win_actions.mouse_control`（不进扩展动作 down-only 管道，无防抖；
  日志 tag 区分 MOUSE/SWITCH；旧版 win_actions 对未知动作安全忽略，前后兼容）。
- **win_actions v1.14**：`TARGET:SWITCH:ATV|MAC|WIN`（仅 DOWN）→ 复用 v1.12 HUD 体系
  （`_hud_open` 抽取通用 `_hud_open_text(txt)`，与模式 HUD 共用）弹「🎯 已切到 ATV/macOS/Windows」
  Tk 浮层（1.1s 自动消失 + 提示音；Tk 不可用静默降级 `no-tk`——切换本体在 T1 侧落盘，仅提示缺失）。
  非法目标/UP 忽略（`ERR bad-target` / `switch hud ignored (up)`）。
- **测试**：`actions_offline_test.py` **448/448**（+§21 23 条：分派矩阵 / 非法目标 / 大小写宽容 /
  非 Win no-tk 降级 / 取证计数 / win_actions + win_receiver 源码约定守护）。
- **部署**：经 RUN 通道升级（同既有流程；当日已上线，2026-10-13 15:4x 用户复测「可以切换了」✅）。

## v1.9 + v1.13 变更（2026-10-13）——★ 元凶级修复：跨模块 SendInput 类型冲突 + 模式 HUD + 滑行手感

- **根因（「OK 键完全没反应」的全部真相）**：`ctypes.windll.user32` 是**进程级共享对象**；
  `win_receiver` 与 `win_actions` **各自定义 INPUT 结构类**并各自设置 `SendInput.argtypes`
  （后加载的 receiver 覆盖）→ win_actions 侧全部 SendInput 调用（**点击 / 滚轮 / Alt tap**）
  以跨类指针被 ctypes 拒绝，抛 `TypeError: expected LP_INPUT instance instead of pointer to
  INPUT` 被 `except: return False` 吞 → **静默全灭**。键盘（receiver 自己的类）正常
  ——「鼠标能滑行、键盘可用，唯独点击毫无反应」之谜。
- **取证**：v1.12 内置 `MOUSE:REPORT` 探针（零位移 `MOUSEEVENTF_MOVE`，无害）经 RUN 通道回传
  `state/mouse-report.json` **一击命中**（`"EXC argument 2: TypeError..."`）。
- **修复**：win_actions v1.13 结构定义上移通用层（跨平台）+ win_receiver v1.9 **复用同一类对象**
  （全进程单类 = 两模块声明/调用全同型）；4 处静默 `except` 补 `_logv` 落盘；REPORT 增
  `input_class_module` 指纹（修复后恒为 `"win_actions"`）。**实机验证：探针 `EXC` → `ok(1)`**。
- **连带纠正**：`force_foreground` 注释「实测 Alt 敲击无效」实为同 bug——Alt tap 从未成功过，
  现恢复可用（前台锁定多一条解锁手段）。
- **v1.12 随行交付**：滑行速度**事件驱动清零**（治「特别快、无法小距离移动」——遥控器方向键是
  离散按压流，旧版唯一清零点在 `step()`，up 间隙内 worker 提前 continue 不调 step → 速度跨
  按压累积；现在 `stop()/_sweep()` 即清零，对齐 Mac lua `stopTimer` 语义；
  §19a 对照：11.67 vs 旧 23.33 px/step）；**模式 HUD**（`MOUSE:MODE:ON|OFF` → 复用 picker
  Tk 线程弹「鼠标模式/键盘模式」浮层 + MessageBeep；实机 `mode hud on/off (tk)` ✅）。
- **测试**：`actions_offline_test.py` **425/425**（+§19 速度/MODE/REPORT +§20 类统一运行时
  断言 27 条〔`win_receiver.INPUT is win_actions.INPUT` 等〕）；`offline_test.py` 22/22。
  升前/升后取证自动回传（证据存 `windows/forensics-2026-10-13/`）。

## v1.7 + v1.11 变更（2026-10-13）——鼠标模式（遥控器 dpad 模拟鼠标）

- **win_receiver v1.7**：`handle_key` 新增 `MOUSE:*` 前置分支（VK 查表 / picker 路由之前）
  → `handle_mouse` → `win_actions.mouse_control`。MOVE/SCROLL 是 **DOWN+UP 双向 hold 语义**
  （不能走扩展动作 down-only 管道，故独立分流）；不做防抖——重复 DOWN 是保活刷新（幂等），
  UP 是配对刹车（不可去重）。
- **win_actions v1.11**：`MouseGlide` 滑行积分器（策略层纯逻辑，离线可测）+ `mouse_control`
  分发入口 + `mouse_button_click`（当前位置左/右键 SendInput，不移动光标）+ `_send_wheel`
  （滚轮 `WHEEL_DELTA=120` / `SCROLL_NPS=10` notch/s 对齐 Mac 900px/s 观感）。滑行参数与
  Mac lua **逐条对齐**：700px/s² / 1600px/s 上限 / 1.2s 无刷新看门狗自停 / 斜向 √2 速
  （不归一化）/ 虚拟屏包围盒夹取 / 60Hz 常驻推进线程（懒启动）。
- **测试**：`actions_offline_test.py` **367/367**（+38：加速离散积分 / 速度上限 / 停止即停 /
  看门狗 / 对向相消 / 斜向 / 边界夹取 / 滚动速率与方向 / 保活刷新 / stop_all +
  `mouse_control` 分派矩阵 + 源码约定守护）。
- **部署（待 Windows 上线）**：照既有流程替换 `win_actions.py` + `win_receiver.py` 两件并重启
  计划任务（或将两文件放入更新包同目录后双击 `update-win-receiver.bat`）。无新增依赖、
  无注册表/权限变更。
- 键盘 / 语音 / 扩展动作 / picker 路由行为全部不变（v1.6 语义原样保留）。

## v1.10 变更（2026-10-12）——长按电源键「关闭当前应用」（`win_actions.py` v1.10）

- **功能**：遥控器长按电源键（#116）≥0.6s → 关闭**当前前台应用**。Mac 同日对等上线
  （`app_switch` v1.2 `close` + `key_bridge` v1.12；Mac 侧已生产路径实测 ✅）。
- **实现**：`WM_CLOSE` 优雅关闭（`SendMessageTimeoutW` + `SMTO_ABORTIFHUNG` 1.5s；从不
  `TerminateProcess`）→ 应用走自身退出流程（未保存内容弹保存确认）。UWP（ApplicationFrameHost）
  先取**真身子窗口**（`host_child_hwnd`）；桌面/任务栏等 shell 窗口**拒绝**；成功判定 = 窗口
  销毁**或**前台已切换（`close_poll` 轮询 ≤2s）；**防抖 2.0s**（对齐 Mac `CLOSE_DEBOUNCE`）。
- **键位**：keymap v2 `#116.long = "APP:CLOSE"`（单击仍为「打开 workbuddy」；长按由
  voice_fwd v2.3 状态机独立触发，与单击严格互斥——不会双击误触）。
- **测试**：`actions_offline_test.py` **329/329**（+23：`close_poll` 注入轮询 4 例 /
  分派与防抖 5 例 / 源码约定 14 项）。四套 **488 PASS**（329 + 28 + 89 + 42）。
- **施工与验收**：见 `TASK-close-app.md`（2a-2g）。

## picker v2.6 变更（2026-10-12）——选中格图标透明融合：双底色变体（`win_actions.py` v1.9）

- **用户六轮反馈**：「图标外围有一圈灰色底色，没有完美融合进 ui 里面，是不是图标没有用透明色？」（方向判断正确）
- **★ 根因（像素级实锤）**：Tk `PhotoImage` 不支持 alpha 通道 → 图标必须先按底色「实底合成」再显示。
  旧版只生成**非选中**变体（合成底 = 窗口灰 `ICON_BG #8a8a8a`）；图标处于**选中格**（填充 `#6c84af`）时，
  方块灰底在蓝底上外露成**一圈灰色**。v2.4 深色时代同缺陷已存在（`#151a21` 叠 `#1b2c48` 不显眼），换浅色后被放大。
  证据 = v2.4 实拍横向像素扫描：`#3b82f6`(蓝边框) → `#1b2c48`(选中填充 22px) → **`#151a21`(tile 灰底 22px)** → 图标内容 → `#151a21` → …
- **★ 修复 = 双底色变体**：图标管线加 `bg` 参数；新增 `ICON_BG_SEL = (0x6c,0x84,0xaf)`（= SEL 填充同色）；
  `_icon_photo_for(..., sel=True)` 生成选中变体；缓存键加 `bg` 维度；选择器构建时每图标生成两套 PhotoImage，
  `_paint` 选中切换时换用对应变体 → 透明区域分别贴合灰底/蓝底（对齐 Mac：NSImage alpha 天然透过选中 32% 蓝填充）。
- **测试**：`actions_offline_test.py` **306/306**（+15：SEL 底合成数学 / `_finish_icon_ppm` bg 变体端到端 / 7 项接入约定）；
  receiver 28 / webui 84 / JS 39 不变。四套 **457 PASS**（306+28+84+39）。
- **核验图**：`picker-v26-fix-preview.png`（本机按 v1.9 真实管线渲染「修复前 vs 修复后」；量化断言选中格透明角 = SEL 精确同色）。
- **验收**：见 `TASK-picker-fix.md` v2.6 §2（重点：**2h 选中格图标融合**，另有 2e 配色 + 2a-2g 回归）。
- **更新（推荐双击版）**：双击 `update-win-receiver.bat`（自动拉取最新 ps1 并本地执行；绕开 `irm|iex` 拦截）。
  命令行备用：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`。

## picker v2.5 变更（2026-10-12）——配色对齐 Mac：浅灰磨砂风格（`win_actions.py` v1.8）〔用户侧部署确认 ✅〕

- **用户五轮反馈**：「Windows 上选择器的颜色不太好看，我希望你把它改成跟 Mac 版是一样的，就是配色是灰色的。」
- **★ 配色对齐 Mac AppPicker（浅灰磨砂 HUD）**：v2.3 的深炭蓝（`#151a21` 底 + `#1b2c48` 选中）整体退役。
  按 Mac 实拍截图**逐像素采样**反推：底 → **`#8a8a8a`**（磨砂灰实色近似）；选中填充 → **`#6c84af`**
  （系统蓝 32% 叠灰底）；选中边框 → **`#017aff`**（macOS 系统蓝）；文字（提示行 / 占位字母 / 名称两态）
  → **`#141414` 近黑**（对齐浅色模式 labelColor）。**`ICON_BG` 同步 `(0x8a,0x8a,0x8a)`**。
- **测试**：`actions_offline_test.py` **291/291**（+3 条 v1.8 配色约定；composite 默认底期望同步更新）；
  receiver 28 / webui 84 / JS 39 不变。四套 **442 PASS**（291+28+84+39）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：**2e 配色（Mac 灰调）**，另有 2a-2g 回归）。
- **更新（推荐双击版）**：浏览器打开 `http://T1_IP:8000/update-win-receiver.bat` 下载一次 →
  以后每次更新只需**双击**该 bat（自动拉取最新脚本并本地执行；绕开 `irm|iex` 拦截；bat 本身无需重下）。
  命令行备用：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`。

## picker v2.4 变更（2026-10-11 深夜四期）——网格方向导航 + UWP 真实图标（`win_actions.py` v1.7）

- **用户四轮反馈**：①「两行的时候，上下键也是左右移动，这不符合操作直觉」；②「计算器图标不对，也就是说系统自带图标显示不对」。
- **★ ① 网格方向导航（「上下键也是左右移动」）**：旧版 ↑/↓ 与 ←/→ 同为线性 ±1（两行网格下 ↑↓ 视觉表现为横移）。
  新增 `grid_move` 纯逻辑：**↑/↓ = 垂直**（相邻行同列优先；末行该列不满时取最近列；首行 ↑ / 末行 ↓ 回绕另一端）；
  **←/→ = 行内水平**（行尾 → 下一行首、行首 → 上一行尾）；单行 / 单列时自动退化为线性（旧行为不变）。
- **★ ② UWP 真实图标 Shell 通路（「计算器图标不对」）**：根因 = UWP 真身 exe（WindowsApps\...\Calculator.exe）的
  **内嵌资源 ≠ 系统显示图标**（显示图标由 shell 从应用清单 / logo 资源解析；v2.1 只解决了宿主壳图标问题）。
  新增通路：窗口 AUMID（`SHGetPropertyStoreForWindow` → `PKEY_AppUserModel_ID`；回退 `GetApplicationUserModelId(pid)`）
  → `shell:AppsFolder\<AUMID>` → `IShellItemImageFactory.GetImage`（ICONONLY|SCALEUP）→ HBITMAP → RGBA
  → 复用既有后处理管线（裁白→补方→光学归一→合成→缩放）；UWP/包应用优先（触发 = 宿主进程或包应用路径
  〔`is_uwp_path`: WindowsApps / 沉浸式控制面板〕——覆盖全部系统自带应用）、任一环节失败自动回退 exe 内嵌。
  COM 全走 ctypes 手写 vtable（不引入 comtypes 依赖；GUID/PROPERTYKEY/PROPVARIANT/SIZE 结构 + `_guid` 解析离线可测）。
- **测试**：`actions_offline_test.py` **288/288**（+63：grid_move 33 / GUID 7 / 包应用路径 5 / 非 Win 安全 3 / 约定 15）；
  receiver 28 / webui 84 / JS 39 不变。四套 **439 PASS**（288+28+84+39）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：**2g 计算器图标 / 第 3 步网格方向移动**，另有 2a-2f 回归）。
- **更新**：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（接收端在跑/没在跑都可以）。

## picker v2.3 变更（2026-10-11 深夜三期）——配色重做 + 长名滚动 + receiver 防抖修复（`win_actions.py` v1.6 / `win_receiver.py` v1.6）

- **用户三轮反馈**：①「界面颜色不好看」；②「app 名称长的显示不全，要做成能滚动显示」。
- **★ ① 配色重做（暗色一体化 v2）**：底 `#23272e` → **`#151a21`**（深炭冷调、更沉稳有层次）；
  选中填充 `#2b4a7e` → **`#1b2c48`**（哑光深蓝、与 `#3b82f6` 亮蓝描边同调、与遥控台 active 同族）；
  名称双色——非选中 `#d7dee9` / 选中 `#ffffff`。**ICON_BG 同步 `(0x15,0x1a,0x21)`**（图标合成底色=窗口底）。
- **★ ② 长名滚动（「显示不全」）**：旧版 `name[:14]` 硬截断 + 文字被格边硬裁（「Windows 资源管理器」→「ndows 资源管」）。
  新增 `fit_prefix`（非选中：像素预算内截断 + `…`）与 `cycle_slice`（选中：`name + 3 空格` 环形跑马灯窗口），
  **选中项每 180ms 推进 1 字符滚动**；预算 = 格宽 − 10×缩放；本机真字体集成冒烟验证宽度全程 ≤ 预算。
- **③ `win_receiver.py` v1.6 防抖首击语义修复**：`now - _ext_last.get(action, 0.0) < d` 把「从未触发（默认 0.0）」
  在单调时钟从 0 起的环境误判为「d 秒内刚触发」→ 首击被吞；改 `None` 哨兵显式判定。
  双解释器（3.9 低时钟 / 3.13 正常）对照实测 + 防回归测试 2 项。
- **测试**：`actions_offline_test.py` **225/225**（+18：fit_prefix 6 / cycle_slice 7 / 约定 5 + 配色期望更新）；
  `receiver_smoke_test.py` **28/28**（+2 防抖首击）。四套 **376 PASS**（225+28+84+39）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：**2e 配色 / 2f 长名滚动**，另有 2a/2b/2c/2d 回归）。
- **更新**：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（接收端在跑/没在跑都可以）。

## picker v2.2 变更（2026-10-11 深夜二期）——二轮实测修复 + Windows 补丁正式合入（`win_actions.py` v1.5）

- **用户二轮反馈**：①「图标大小还是不一样」；②「左右切换的时候图标框大小也在变」。
- **★ ① 图标框/单元格尺寸恒定（「切换时框在变」根因）**：cell 子件走 **pack** 布局，但固定尺寸调的是
  `grid_propagate(False)`（只对 grid 子件生效）→ 从未生效 → cell 宽被应用名文本撑开
  （Tk 实验实锤：各 cell 请求宽 27/125/58/133px 不等）→ 蓝框忽大忽小 + 窄格图标被裁。
  修复 = `cell.pack_propagate(False)`（实测全部恒定 96×100）；附带 `pick_layout` 宽公式补每格
  grid padx（旧漏算致末列被裁 12px）+ 显示前按实际请求尺寸兜底校正窗口。
- **★ ② 光学尺寸归一 v2**：v2.1 的 trim+square_pad 只统一「画布」（圆形内容面积仅方形 78.5% → 看着偏小）。
  v2.2 `optical_fit_rgba`：按内容**有效面积**（alpha>8 像素数）开根归一到 `OPTICAL_REF×px`（0.84），
  配套**预乘双线性** `scale_rgba`（透明边缘不发黑）；放大上限 2.0 / 缩小下限 0.15 / 大边 ≤96% 钳制。
- **★ ③ Windows 补丁正式合入（三处阻断级）**：① `apps_from_windows` 补写 `exe_key`（原读取键名不匹配
  → 图标全退化为首字母占位且无日志）；② 键名双重兼容（`exe_key` → `key` 回退）；③ `PhotoImage` 改
  `base64.b64decode(...).decode("latin1")` + `format="PPM"`（Tk 8.6 不解码 base64）。
  防再回改：离线测试内置源码约定守护 5 项。
- **`win_audio_switch.py` v1.2**：COM 初始化改裸 Win32 `ctypes.windll.ole32.CoInitializeEx(None, 0x0)`
  （comtypes ≥1.4 下旧写法抛 TypeError 被吞 → 计划任务实例的麦克风切换恒失败）。
- **测试**：`actions_offline_test.py` **207/207**（+21：scale_rgba 预乘 6 / optical_fit 11 / 约定 4）；
  `audio_switch_offline_test.py` **74/74**（+1 约定）。四套合计 **356 PASS**（207+26+84+39）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：**2a 光学尺寸一致 / 2b 纯应用名 / 2c 设置齿轮 / 2d 图标框恒定**）。
- **更新**：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（接收端在跑/没在跑都可以）。

## picker v2.1 变更（2026-10-11 深夜）——上机实测三反馈修复（`win_actions.py` v1.4）

- **用户上机反馈**：①「图标大小不一」；②「只要显示应用名字就好，不要带一堆文字后缀」；③「设置明明有自己的图标，为什么用了个其他的图标」。
- **① 图标视觉尺寸归一**：`trim_rgba`（按 alpha 外接框裁空白 + 4% 透气边距；全透明/过小/满幅保守原样）
  → `square_pad_rgba`（透明补正方形、居中保比例）——图标内容撑满同一方框，网格视觉大小一致
  （根因：老式图标画布留白多、现代图标满幅，按同画布缩放后内容大小不齐）。
- **② 应用名净化**：`app_display_name()` 读 exe 版本资源 `FileDescription`（version.dll，中文语言块 0804 优先；
  退路 exe 主名去 `.exe`；按 exe_key 缓存）——不再显示 `main.py - Visual Studio Code` 式窗口标题。
- **③ UWP 真身图标**：`is_host_process()` 命中 `ApplicationFrameHost.exe` 时用 `host_child_pid()`
  （EnumChildWindows → 可见子窗口真实 PID）替换窗口归属——设置 = `SystemSettings.exe` 齿轮图标，不再是宿主壳通用图标。
- **测试**：`actions_offline_test.py` **186/186**（+29：is_host_process / choose_display_name / trim_rgba 11 / square_pad_rgba 7）。
  四套合计 **335 PASS**（186+26+84+39）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：**2a 图标大小一致 / 2b 纯应用名 / 2c 设置齿轮图标**）。
- **更新**：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（接收端在跑/没在跑都可以）。

## v1.5 变更（2026-10-11 晚）——APP:PICK 选择器 v2（图标网格 + 崩溃根治 + 高 DPI）

- **用户实测反馈**：①「试了几下就出错，弹出个窗口报错」；②「太难看了，要求跟 Mac 一样弄应用图标」；③ 硬性要求「考虑 windows 不同 dpi」。
- **崩溃根治（`win_actions.py` v1.3）**：旧版每次 PICK 新建/销毁独立 Tk 解释器，GC 在非创建线程回收
  → `Tcl_AsyncDelete: async handler deleted by the wrong thread` fatal（触发时机随 GC 不定 =「试几下才炸」）。
  v2 = **常驻 Tk 线程**（进程内唯一 root，每次只开关 Toplevel）+ 回调异常只记日志、绝不弹窗。
- **图标网格 UI**：6 列 × 64px 真实 exe 图标（`PrivateExtractIconsW` 按目标像素直出 → alpha 合成底色防黑边
  → PPM/PhotoImage；`SHGetFileInfoW` 兜底）；交互对齐 Mac AppPicker（初始选第 2 项 / 环绕移动 /
  OK 打开 / 返回取消 / 10s 自动取消 / 选中蓝框）。
- **高 DPI**：全布局按 `winfo_fpixels("1i")/96` 缩放（钳 1.0~3.0），图标按目标像素提取；多屏 = 光标所在显示器工作区居中（避开任务栏）。
- **`win_receiver.py` v1.5**：URL:/RUN: 动作值大小写保真（`action_raw` 原值走扩展动作，uppercase 仅用于查表）。
- **`update-win-receiver.ps1` v1.5**：支持「接收端未在运行」冷更新（进程 → 计划任务 → 默认目录三级定位；
  冷启动优先走计划任务）；新增 tkinter 检查；PING 失败自动附 `receiver.log` 尾巴。
- **测试**：`actions_offline_test.py` **157/157**（+52：pick_move 环绕 / pick_layout DPI 缩放钳制 /
  图标合成 / scale_rgb / ppm_encode）；`receiver_smoke_test.py` **26/26**；`webui_v2_test.py` **84/84**；
  `webui_js_test.mjs` **39/39**（合计 **306**）。
- **验收**：见 `TASK-picker-fix.md` §2（重点：图标网格 / 反复捶打 ≥6 次不崩 / DPI 缩放 / 日志行）。

## v1.4 变更（2026-10-11）——APP:PICK 选择器修复（按键直连路由 + 视觉重做）

- **用户实测反馈**：长按 home 弹出选择器「窗口难看」+「上下键无法切换」。
- **根因**：接收端为计划任务/后台上下文，其 tkinter 窗口无法保证获得 Windows 前台激活
  → 注入的 UP/DOWN 落到别的窗口（与 APP:CYCLE 前台锁定同类问题）。
- **修复（`win_actions.py` v1.1 + `win_receiver.py` v1.4）**：
  - **按键直连路由** `picker_route()`：选择器打开期间，UP/DOWN/ENTER/ESC/BACKSPACE
    由收包线程直接投递给选择器（队列 + 50ms 消费）——不依赖系统键盘焦点，100% 可靠；
    旧版 win_actions 无此接口时自动回退注入（getattr 保护）。
  - 视觉重做：暗色一体化（#23272e + #3b82f6，与网页遥控台同色系）、按内容精确定高、
    无滚动条、**手动 itemconfig 高亮（不依赖焦点态）**、标题/提示行、固定尺寸。
  - 抢前台降级为「尽力而为」（不再对自身窗口用最小化→还原闪屏）；鼠标点击/双击为第二通道。
- **测试**：`actions_offline_test.py` **88/88**（+17 路由用例）；`receiver_smoke_test.py` **21/21**（+5 routed 断言）。

## v1.3 变更（2026-10-11）——麦克风按需自动切换（方案 V）

- **新增 `win_audio_switch.py` v1.1**：COM 切系统默认录音设备（`IMMDeviceEnumerator` +
  `IPolicyConfig.SetDefaultEndpoint` 三 role 同切；设备名走 MMDevices 注册表）。
  - `switch_to_virtual()`：按下 → 默认设备切到 **CABLE Output**（幂等, fail-open, 先切后注入）；
  - `schedule_restore(2s)` / `cancel_pending_restore()`：松开 → 延迟切回；**连按自动取消**；
    gen 计数**双重检查**（拿锁后复核）——stale 定时器绝不会切掉新会话；
  - `recover_if_needed()`：崩溃自愈（`state/audio_switch.json` phase=switched → 启动切回原设备）。
- **win_receiver.py v1.3**：VOICE down **先切设备**（~200ms 预算, fail-open 不拦链路）**再注入** Ctrl+Win；
  VOICE up / watchdog 兜底释放后均调度 2s 切回；启动预热 COM + 自愈；selftest 加音频设备段。
- **update-win-receiver.ps1 v1.3**：3 文件（+`win_audio_switch.py`）+ 备份 + PING + selftest。
- **测试**：`audio_switch_offline_test.py` **73/73**（状态机全路径 + 调度/竞态, 含慢 set 竞态场景）；
  `receiver_smoke_test.py` **16/16**（语音链时序：先切后注入顺序断言 / 松开调度 / fail-open）。
- **前提**：微信输入法麦克风改「默认设备」（一次性, 用户操作；顺序要求见施工单 §4）。
- **更新**（Windows）：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（或施工单 §1B 等效步骤）。

## v1.2 变更（2026-10-11）——Mac 对等扩展动作（CLICK / FOCUS_INPUT / APP:*）

- **新增 `win_actions.py` v1.0**（两分层：ctypes 平台层 + 纯策略层, Mac 可打桩测试）：
  - `CLICK` 点击焦点元素 = Mac `remotehub_focus.clickFocused()` 四段移植
    （UIA Invoke 自身 → 直接子 → 向上≤6 → 坐标兜底+尺寸门槛 w>8,h>4）；
  - `FOCUS_INPUT` 跳输入框 = Mac 五阶段移植（窗口修复 → 缓存点 → 坐标网格底部优先
    → 树遍历 Edit→ComboBox → SetFocus 读回验证；Document 类型经尺寸启发式过滤页面根）；
  - `APP:*` = Mac `app_switch.swift` 移植：`CYCLE`（z 序快照+前台校验续期 30min 环推进）、
    `TOGGLE`（{prev,cur}）、`NEXT`（名称序）、`PICK`（tkinter 选择器：↑↓/OK/返回）、
    `APP:<名称>`（匹配链 exe精确→标题精确→exe包含→标题包含；未运行则 App Paths →开始菜单lnk →PATH →cmd start 启动）。
- **win_receiver.py v1.2**：未知动作不再丢弃 → 转 `win_actions.handle()`；收包线程快速防抖
  （CLICK/FOCUS=0.6s, APP=0.35s，对齐 Mac key_bridge）→ 独立 **action-worker 线程**执行
  （UIA 慢调用不阻塞收包）；`--selftest` 自检（平台/UIA/窗口/焦点元素；完整版写 `selftest.log`）。
  v1.1 语音链/键盘/日志全行为不变。
- **依赖**：`pip install uiautomation`（更新脚本自动装, 清华源+回退；失败仅 CLICK/FOCUS 降级, APP:* 不受影响）。
- **测试**：`actions_offline_test.py` **71/71**（FakeBackend 打桩：四段/五阶段/环推进/匹配链/尺寸启发/防抖表）。
- **更新**（Windows）：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`（自动装依赖 + 双文件替换 + 备份 `.bak-<TS>` + PING + selftest）。

## 音频链 v1.0（2026-10-11）——遥控器 MIC → Windows → CABLE Input

链路：`遥控器 MIC → BLE/ATVV → T1 atvv_service v1.1 → UDP:8789 双播 → win_audio_receiver → "CABLE Input" →（虚拟线）→ 输入法读 "CABLE Output"`

- **T1 侧**（已部署，md5 `a7dc5177…`）：`atvv_service.py` **v1.1** 单目标 → **双目标**（`DESTS = ((MACOS_IP,8789),(WINDOWS_IP,8789))`）；
  新增 `send_all()`：单目标失败不影响其他目标（错误日志按目标 60s 节流）。快照 `atvv_service.py.v10.bak-20261011-181024`（旧版 md5 `548ae9d2…`）。
  冒烟：双目标分发 ✓ / 单目标故障隔离 ✓ / 真实发送 ✓；banner `v1.1 启动 -> .19:8789, .18:8789`。
- **Win 侧**（✅ 已部署，10-11）：`win_audio_receiver.py` v1.0（自 Mac `atvv_receiver.py` v1.2 全链移植）：
  IMA ADPCM 解码 → 16k→设备率上采样 → HPF 80Hz → AGC(target 0.2/max 24/0.95 限幅) → `CABLE Input`；
  相对 Mac 版增强：**设备采样率自适应**（48k/44.1k 均可）、`--dry-run`（无声卡诊断链路）、`PING→PONG`、异步日志（win_receiver v1.1 同款）。
- **音频与按键目标解耦**：音频恒定双播（不受 voice_target 影响）；「按住 Ctrl+Win」触发注入仍按 target 单投。
  → 验收时必须先把遥控器目标切到 Windows。
- **测试**：`audio_offline_test.py` **26/26**（ADPCM 手工推算用例/上采样/HPF 直流抑制+通带/AGC 增益+限幅/serve UDP 端到端+PING+容错）。
- **部署**：先装 VB-Cable（重启）→ `irm http://T1_IP:8000/update-win-audio.ps1 | iex`（幂等：依赖→下载→替换→启动→PING）。
  验收步骤见 `TASK-win-audio.md` §2.5。

## v1.1 变更（2026-10-11）——修「按键延迟特别大」

- **根因**：v1.0 每条消息 **2 次日志 open/write/close 全在收包线程串行**（RX 行 + 处理行）+ `print` 控制台输出
  → 微基准（macOS/APFS）：v1.0 风格 3.9ms/消息 vs v1.1 风格 0.0008ms，**差 4871×**；Windows+Defender 下更大；
  且控制台输出在窗口最小化/快速编辑模式下可能引发秒级阻塞（v1.0 曾用 `python` 前台时）。
  ※ 深度复盘补充：该延迟为毫秒级隐患；用户实测「延迟特别大」的主因是 BLE HOG 断连循环（已在 T1 侧修复），v1.1 仍建议更新。
- **修复**：
  - 异步日志（`queue.Queue` maxsize=4000 + 独立日志线程 + 文件句柄常开行缓冲）；队列满**丢弃日志、绝不阻塞链路**；
  - 收包线程零 IO：`recvfrom -> SendInput -> 入队`；RX 明细行默认不记（`--debug` 打开）；
  - 控制台输出默认关闭（`--debug` 才打；banner/FATAL 例外）；
  - socket 接收缓冲加大 256KB（防突发积压）；
  - **语音键兜底释放**：`VOICE down` 后 60s 未见 `up` 自动补释放（防 UDP 丢包卡住 Ctrl+Win）。
- **测试**：离线 **22/22**（+7：异步落盘 / RX 静默 / 队列溢出不抛 / 风暴后注入正常 / 兜底触发 / 释放序列 / 未超时不误触发）。
- **更新方法**（Windows 上 PowerShell）：`irm http://T1_IP:8000/update-win-receiver.ps1 | iex`
  （自动：找进程 → 下载 .new → 停旧 → 替换 → 重启 → PING 自检；脚本全 ASCII 兼容中文系统）。
- 基线数据：v1.0 期 PING RTT（T1→.18）n=20 min 6.2 / avg 7.1 / max 11.6 ms（含单次日志写盘）；
  更新 v1.1 后可从 T1 复测同分布对比。

## 链路架构

```
遥控器（RC003，BLE 连 T1）
  ├─ 语音键按住 ─→ T1 voice_fwd ─UDP:8788─→ Windows win_receiver ─→ SendInput 按住 Ctrl+Win（微信输入法语音）
  ├─ 普通键      ─→ T1 voice_fwd ─UDP:8791─→ Windows win_receiver ─→ SendInput 键注入（KEY <动作> DOWN/UP）
  └─ 麦克风音频  ─→ T1 atvv_service v1.1 ─UDP:8789 双播─┬→ Mac atvv_receiver（BlackHole）
                                                        └→ Windows win_audio_receiver ─→ CABLE Input（VB-Cable）
```

- T1 侧：`voice_fwd` v2.3 按 target 单投（atv→relay；mac→MACOS_IP；win→WINDOWS_IP）；
  `atvv_service` v1.1 音频双播（与 target 无关）。
- Win 侧：`win_receiver.py` 双口监听（8788 语音 / 8791 按键）；`win_audio_receiver.py` 单口（8789 音频）；均 PING→PONG、均不设 SO_REUSEADDR（双实例保护）。
- 动作集（Windows 端）：键盘 `ENTER/ESC/TAB/SPACE/BACKSPACE/UP/DOWN/LEFT/RIGHT/PAGEUP/PAGEDOWN`
  + **扩展** `CLICK / FOCUS_INPUT / APP:CYCLE / APP:TOGGLE / APP:NEXT / APP:PICK / APP:<名称>`
  （v1.2；与 Mac key_bridge 语义/防抖对齐）。

## 文件清单（本目录）

| 文件 | 用途 |
|---|---|
| `win_receiver.py` | 按键/语音触发接收端主程序（跑在 Windows；**v1.11** presence 心跳（单代理报 voice/key/audio）+ **v1.10** TARGET:SWITCH 设备切换路由 + **v1.9** ★ SendInput 类统一修复 + MOUSE:* 路由 + 防抖首击修复 + 选择器 v2 + URL/RUN 保真 + 麦克风切换） |
| `win_audio_switch.py` | **默认录音设备按需切换**（**v1.2**；方案 V：按下→CABLE / 松开延迟切回 / 自愈；v1.2 = COM 初始化裸 Win32 修复） |
| `win_actions.py` | **扩展动作实现**（CLICK/FOCUS_INPUT/APP:*/URL:/RUN:/MOUSE:*/TARGET:SWITCH:*；**v1.16** app-activate 观测日志 + v1.15 FOCUS_INPUT 兜底点击 + app 观测 + v1.14 设备切换 HUD + v1.13 ★ SendInput 类统一修复 + v1.12 速度清零/HUD/取证 + v1.11 滑行引擎 + v1.10 长按关闭 + picker v2 系列外观） |
| `actions_offline_test.py` | **扩展动作离线测试**（**462/462**；FakeBackend 打桩 + 布局/图标/名称/UWP/包应用路径/光学/长名截断滚动/网格导航/close_poll 关闭轮询/设备切换 HUD/聚焦兜底点击/v1.16 观测日志 纯逻辑 + 源码约定守护, 无需 Windows） |
| `audio_switch_offline_test.py` | **麦克风切换离线测试**（**74/74**；打桩设备层 + 真实 Timer 调度 + COM 初始化约定） |
| `receiver_smoke_test.py` | **接收端时序冒烟**（**28/28**；先切后注入/松开调度/fail-open/picker 路由/URL·RUN 原值/**防抖首击低时钟**） |
| `update-win-receiver.ps1` | 按键链更新脚本（**v1.10**：冷更新支持 + tkinter 检查 + 3 文件（receiver v1.6 / actions v1.10 / audio_switch v1.2）+ 备份 + PING + selftest） |
| `TASK-win-actions.md` | **扩展动作施工单**（已完成；给 Windows 本机 WorkBuddy） |
| `TASK-mic-switch.md` | **麦克风切换施工单**（v1.3；已施工验收；含 §1B 等效步骤 + §3 UDP 直发验收） |
| `TASK-picker-fix.md` | **选择器施工单**（**v2.6**；图标网格 + 崩溃根治 + 高 DPI + 光学归一 + 单元格固定尺寸 + 灰调配色 + 选中格图标融合 + 长名滚动 + 网格方向导航 + UWP 真实图标, 验收 §2） |
| `TASK-close-app.md` | **v1.10 施工单**（★ 长按电源键关闭当前应用 + v1.8/v1.9 累积外观；§1 施工 / §2 验收 2a-2g / §3 回滚） |
| `win_audio_receiver.py` | **音频接收端**（跑在 Windows；遥控器语音→CABLE Input；v1.0） |
| `update-win-audio.ps1` | **音频链部署/更新脚本**（幂等：依赖→下载→替换→启动→PING） |
| `TASK-win-audio.md` | **音频链施工单**（给 Windows 本机 WorkBuddy） |
| `audio_offline_test.py` | 音频链离线测试（**26/26**；需 numpy，不依赖声卡） |
| `selftest_send.py` | 本机自测（9 测试包 + PING） |
| `win_ping.py` | **连通性诊断**（从 T1/Mac 发起：`python3 win_ping.py [host]`；三端口 8788/8791/8789） |
| `offline_test.py` | 按键链离线逻辑测试（打桩 SendInput；**22/22**） |
| `TASK-windows-deploy.md` | 按键链部署说明（首轮施工单） |
| `win-package-http-access-20261011.log` | 分发期 HTTP 访问日志（归档） |

## 现状

- **win 份键位（现网，10-11 21:31 起与 mac 100% 对齐）**：`#28 OK=短按 ENTER/长按 CLICK` / `#158 返回=BACKSPACE+连发` / `#127 菜单=ESC+连发` / `#41 直播=FOCUS_INPUT` / `#114 音量-=TAB/长按 PAGEDOWN` / `#115 音量+=SPACE/长按 PAGEUP` / `#102 主页=短按 APP:CYCLE/长按 APP:PICK` / `#103-#108 方向键+连发` / **`#116 电源=连击切设备（1 击=ATV / 2 击=Mac / 3 击=Win；长按=关闭当前应用）`**；`#63 语音 locked`（语音链专用）。
- 语音触发键：微信输入法 = 按住 **Ctrl+Win**（`win_receiver.py: VOICE_MODS` 可改；若输入法换绑需同步改）。
- 音频出口：VB-Cable `CABLE Input`（win_audio_receiver 写入）→ `CABLE Output`（虚拟线另一端）。
- 输入法麦克风：v1.3 起设为「**默认设备**」，由接收端按需切换（语音会话=CABLE Output / 平时=真麦）。
- 实测基线（2026-10-11）：Mac→.18 UDP RTT：8788/8791 PONG 均 9ms；扩展动作验收 4/4；
  **v1.3 麦克风切换用户实测通过**（按语音键→默认设备跳 CABLE Output / 松开 2s 跳回 / 本机 Ctrl+Win 用系统麦）；
  **v1.5 选择器 v2 已分发** → **v2.1 三修复** → **v2.2 二轮修复 + 补丁合入 ✅ Windows「理想收敛轮」验证**
  （其报告逐行核对：上游三补丁齐全、三件哈希一致、无需再打补丁）→ **v2.3 配色 + 长名滚动 ✅ Windows 实机验收**
  （23:51 报告：跑马灯 4 帧实拍 / 验收零新补丁）→ **v2.4 网格方向导航 + UWP 真实图标 ✅ 用户验收**
  （2026-10-12「Windows 上测试已经通过」；配 win_actions v1.7）→ **v1.10 升级包（v1.8/v1.9/v1.10 三合一）✅ 已上线并实测通过**
  （14:17:53 自助拉取 → 14:22 用户实测两端通过；含 ★ 长按电源键关闭当前应用，施工单留档 `TASK-close-app.md`）。
- **鼠标模式（2026-10-13）**：13:29 远程升级上线（v1.7+v1.11）→ 用户首测五问 → **修复轮完成**
  （v1.8+v1.12 → v1.9+v1.13，同一日三轮升级）；元凶 = 跨模块 SendInput 类型冲突
  （探针 `EXC TypeError` → `ok(1)` 实证）；配套 T1 voice_fwd v2.6（模式 HUD/放行键）+
  Mac lua v1.3 / key_bridge v1.14；施工单 `TASK-mouse-mode.md`（§6 修复轮）；
  **15:1x 用户复测通过**（鼠标速度 / OK 长按右键 / 主页 / 返回全部 OK）。
- **设备切换（2026-10-13 15:1x）**：T1 电源键连击（1=ATV / 2=Mac / 3=Win）→ 本机 HUD
  「🎯 已切到 X」（win_receiver v1.10 + win_actions v1.14；同 MOUSE:* 路由）；
  当日已上线，**15:4x 用户复测「可以切换了」✅**。
- **FOCUS_INPUT 兜底点击（2026-10-14）**：五段全 miss → 底部中央 `(0.5, 0.92)` 兜底点击
  （win_actions v1.15 实装；Mac lua v1.5 同款 → **v1.6 再修正：前台提升 + 距底 105px + fail-skip**）；
  03:16 经 RUN 通道升级、03:18 锁屏态端到端实证
  `NOEDIT+CLICK@1920,1987 [winfix=raise app=lockapp.exe]`；待用户遥控器复测（微信聊天场景）。

## 维护入口

- **改键位**：`http://T1_IP:8765/keymap` → 「Windows」tab（v2.9 起自动跳到当前激活目标）。
- **诊断连通性**：T1 或 Mac 上 `python3 win_ping.py`（三端口各 3s 超时；8789 超时=音频端未跑是正常）。
- **按键端重启（Windows 上）**：`python win_receiver.py`（日志 `receiver.log`）；开机自启=计划任务 `remotehub-win-receiver`。
- **音频端重启（Windows 上）**：`pythonw win_audio_receiver.py`（日志 `audio_receiver.log`；`--dry-run` 无卡诊断；`--list` 看设备）。
- **音频端更新（推荐路径）**：T1 开分发 → Windows `irm http://T1_IP:8000/update-win-audio.ps1 | iex`（幂等，首次部署同此命令）。
- **音频链验收**：目标切 Windows（网页台）→ 按住遥控器语音键说话 → 出字；日志见 `session start/end frames=N`。
- **按键端更新（最新 = v1.15 聚焦兜底点击 + v1.14 设备切换 HUD + v1.13 类统一修复 + v1.12 速度清零/HUD + v1.11 滑行引擎 + v1.10 长按关闭 + 鼠标模式 + picker v2.6 外观 + 选择器 v2 + URL·RUN 动作 + 麦克风切换 + 扩展动作）**：Windows `irm http://T1_IP:8000/update-win-receiver.ps1 | iex`
  （被本机策略拦截时走 `TASK-mic-switch.md` §1B 等效步骤；**接收端未在运行也可直接跑**，脚本自动冷部署）
  → 自检 `python win_receiver.py --selftest`（打印平台/UIA/窗口/焦点元素/**音频设备**）。
- **扩展动作验收**：见 `TASK-win-actions.md` §3（UDP 直发三命令）；日志行 `EXT CLICK -> ...` / `EXT FOCUS_INPUT -> ...` / `EXT APP:CYCLE -> ...`。
- **URL:/RUN: 动作**（v1.5 新增）：网页台 keymap 绑「打开网页…/执行命令…」（值不含空格、≤500 字符）；
  日志行 `EXT URL -> ...` / `EXT RUN -> ...`；Mac 侧 key_bridge v1.11 同构已实弹验证。
- **麦克风切换验收**：见 `TASK-mic-switch.md` §3（UDP 直发 A-E 快照）；日志行 `mic switch -> ...` / `delayed restore -> ...`。
- **选择器验收（v2.6）**：见 `TASK-picker-fix.md` §2（长按 home → 图标网格 / **2h 选中格图标融合** / 2e 浅灰配色 /
  2g 计算器图标 / 第 3 步网格方向移动 / 2f 长名滚动 / 2a 光学尺寸一致 / 2d 图标框恒定 / **反复捶打 ≥6 次不崩** / DPI 缩放）；
  日志行 `picker open: N apps, sel=K, dpi=...% (WxH)` / `KEY UP DOWN -> picker (routed)`。
- **长按关闭验收（v1.10）**：见 `TASK-close-app.md` §2（2a 长按电源关应用 / 2b 单击只开 workbuddy / 2c 防抖 / 2d 桌面拒绝 / 2e 保存确认 / 2f-2g 回归）；
  日志行 `EXT APP:CLOSE -> close[…] -> … ok (…)` / `KEY APP:CLOSE debounced (2.00s window)`。

## 分发（T1:8000）

```bash
# T1 上（施工窗口开着；完事 kill）
cd /root/remote-hub/windows && nohup python3 -m http.server 8000 --bind T1_IP >> /tmp/http8000.log 2>&1 < /dev/null &
# 关闭： pkill -f "[h]ttp.server 8000"
```
