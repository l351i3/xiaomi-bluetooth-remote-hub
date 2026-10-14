# T1 网页遥控台（:8765）交付说明 — 2026-10-14（v2.17 遥控器电量版；v2.0 真机验收 13:24 ✅）

## 是什么

- `http://T1_IP:8765/` —— **三按钮主页：遥控器行为目标切换**（点一下即生效）
  - 〔ATV〕语音键 = 默认一键开 YouTube（v2.15 起可自由改绑）；其余按键 = 控制 Apple TV
  - 〔Mac〕语音键 = 转发 macOS 语音输入；按键 = 键盘注入（OK=回车 / 返回=Esc / 方向=方向键）
  - 〔Windows〕同上（转发链路已上线 ✅：语音键 = 转发 Windows 语音输入；键位与 Mac 100% 对齐）
  - 〔设备状态条〕主页顶部三设备在线状态点（绿=在线 / 灰=离线 / 黄=未知，3s 刷新）——设备离线期间按键暂停投递，回来自动续
- `http://T1_IP:8765/keymap` —— **三 tab 按键配置页**（ATV / macOS / Windows 各一份 13 键配置）
- 手机/任意局域网设备浏览器可用；**保存热生效（下一按键起）、不重启、不断 BLE**

## v2.17 变更（2026-10-14 15:5x）—— 遥控器电量显示（用户需求）

- **需求**（用户原话）：「现在连到 T1 上，我并不知道蓝牙遥控器还有多少电，所以在 T1 控制台上加这么一个电量显示」。
- **功能**：主页设备状态条追加「🎮 遥控器 🔋 N%」（10s 轮询 `GET /api/remote`；电量 ≤20% 黄 / ≤10% 红）。
  数据源 = BlueZ D-Bus 缓存属性（`busctl --json=short get-property org.bluez
  /org/bluez/hci0/dev_<遥控器> org.bluez.Battery1 Percentage`；RC003 支持 Battery Service），
  **零蓝牙流量**（只读缓存，对遥控器零打扰）。
- **降级安全**：遥控器未连接 / 未上报电量（BLE 休眠时属正常）/ busctl 不可用 →
  `available=false` → 显示「休眠中／电量未知」；页面其余行为零改动。
- **测试**：`webui_v2_test.py` **121/121**（+10：三态 fake busctl〔fail/ok/disc〕+ 降级 + 主页元素）。
- **部署**：T1 15:51 上线（双端 sha256 全等）；`/api/remote` 实测 `{"available": true, "connected": true, "percent": 100}`。

## v2.16 变更（2026-10-14）—— 主页「设备在线状态条」（presence 心跳可视化）

- **功能**：主页新增设备状态条——ATV / macOS / Windows 三个状态点（绿=在线 / 灰=离线+
  最后在线秒数 / 黄=未知），3s 轮询 `GET /api/presence`；数据源 = `state/presence.json`
  （presence 心跳注册制，30s 写盘快照；90s 过期 → 降级「未知」，不影响页面功能）。
- **降级安全**：presence 服务未运行 / 快照缺失 / 损坏 → `available=false` → 前端显示
  「设备状态未知（presence 未运行）」；页面其余行为零改动。
- **测试**：`webui_v2_test.py` **111/111**（+10：组装/降级/过期/主页元素）。
- **部署**：T1 04:47 上线（t1-webui 重启；`/api/presence` 实测三设备 online）。

## v2.15 变更（2026-10-13 16:2x）—— ATV 语音键解锁（配置驱动）

- **背景**：用户反馈「ATV 配置页语音键不可设、描述不对」——atv 份 #63 长期 `locked: true`
  不可编辑 + note 写成「语音链专用」；实际上语音键在 ATV 上应可自由设置。
- **功能**：atv 份 #63 **去锁定** + single 默认置 `__LAUNCH__:com.google.ios.youtube`
  （**保持原行为一键开 YouTube**）+ note 重写；网页上可自由改绑任意 ATV 动作
  （如 home / menu / 打开极空间 / 其它应用），清空=关闭该键。mac/win 份 #63 **保持锁定**
  （按住说话, 语音链专用, 交 voice_fwd）。
- **执行端**：`relay_min` v0.12 配合改造——语音键删除硬编码特判，**走通用 keymap 分派**
  （核心一句话：以前锁死是因为行为写死在代码里，现在完全由配置决定）。
- **测试**：`webui_v2_test.py` **101/101**（+1 净增：atv 63 解锁可改 + mac 63 锁定保护）。
- **部署**：T1 16:25 上线（relay v0.12 + webui v2.15 重启 + keymap 三配置同步）；
  `relay_logic_test.py` **31/31**（+2：改绑跟随 / 清空无动作）。

## v2.14 变更（2026-10-13 15:1x）—— 新增动作「★ 电源（连击切设备）」（TARGET:SWITCH）

- **功能**：mac / win / atv **三 tab 下拉**均新增 `TARGET:SWITCH`；生产绑定 = **#116 电源键 single**
  （原「打开 workbuddy」（mac/win）与「电视电源」（atv）不再保留；**长按关闭应用不变**）：
  **1 击=ATV · 2 击=Mac · 3 击=Win**（连击窗口 0.5s；第 3 击立即提交；长按 ≥0.6s 中止计数）。
- **执行端**：`voice_fwd` v2.7（mac/win 态）/ `relay_min` v0.11（atv 态）双侧连击层——
  **网关式启用**（keymap `#116.single` 即本动作；改回任意动作即退回普通键语义，零代码改动）。
  切换即时生效 + 目标端弹「🎯 已切到 X」提示浮层（Mac lua v1.4 / Win win_actions v1.14）。
- **实现（t1_webui v2.14）**：`KB_ACTIONS` + `KB_CHOICES` 放行（mac/win 份）；`ATV_SPECIAL` 放行
  （atv 份）；extLabel 特判「★ 电源（连击切设备）」；`__POWER__` 选项标注改「电源切换（立即，无连击）」。
  keymap 两份 #116.single 已置 `TARGET:SWITCH` + note 注记（现网即刻生效）。
- **测试**：`webui_v2_test.py` **100/100**（+11：choices 文案 / 三份 POST 接受且落盘 / 默认值 /
  #116 note / extLabel 特判）。

## v2.13 变更（2026-10-13）——新增动作「★ 鼠标模式开/关」（MOUSE:TOGGLE）

- **功能**：mac/win 下拉新增 `MOUSE:TOGGLE`；生产绑定 = **#41 直播键 long**（单击仍为
  「跳转输入框」；长按 0.6s 切换鼠标模式开/关）。动作由 `voice_fwd` 模式层**本地消化**
  （不转发网络包；v2.5 引入，v2.6 修复轮补模式 HUD 提示 + 电源/主页放行）：模式内 方向=滑行移光标 /
  OK 短=左键·长=右键 / 音量±=滚动 / 返回=退出。
- **实现（t1_webui v2.13）**：`KB_ACTIONS` 放行 `MOUSE:TOGGLE` + `KB_CHOICES` 下拉项（长按列
  直接可见——下拉由 choices 派生）。keymap 两份（`keymap.json` / `keymap.default.json`）
  #41 long 已同步置 `MOUSE:TOGGLE`（mac/win 对齐；atv 不变）。
- **测试**：`webui_v2_test.py` 89 全绿 + `key_fwd_logic_test.py` 79（含 #41 现网集成断言；v2.6 修复轮后共 **104**）。

## v2.12 变更（2026-10-12 21:3x）——win 卡片文案同步（移除「链路待部署」）

- **背景**：win 卡片与状态描述长期标注「（链路待部署）」——该标注已过时；Windows 转发链路
  10-11 已上线并实机验收（按键链 + 语音音频链；键位与 Mac 100% 对齐）。
- **改动**：主页 win 卡片 `<span>` 与 `DESC.win` 均移除「（链路待部署）」（纯文案，无逻辑变更）。
- **实现（t1_webui v2.12）**：`f6e06376…`；备份 `t1_webui.py.bak-20261012-2129-preV212`。

## v2.11 变更（2026-10-12 14:1x）——新增动作「★ 关闭当前应用（长按电源键）」（APP:CLOSE）

- **功能**：mac/win 下拉新增 `APP:CLOSE`；生产绑定 = **#116 电源键 long**（单击仍为「打开
  workbuddy」；长按由 voice_fwd v2.3 状态机独立触发，与单击严格互斥）。Mac
  `app_switch` v1.2 `close`（terminate 优雅退出）/ Win `win_actions` v1.10（WM_CLOSE 优雅关闭；
  2.0s 强防抖；`windows/TASK-close-app.md`）。
- **实现（t1_webui v2.11）**：`KB_CHOICES` 新增项 + extLabel 特判（「关闭当前应用（长按电源键）」）；
  校验沿用 APP: 前缀放行（atv 拒绝）。`fc864869…`；备份 `t1_webui.py.bak-20261012-1412-preV211`。
- **keymap**：三份 `#116.long="APP:CLOSE"` 已下发（`33da9a4b…`）；rev `5f7dd9a08976`
  （**旧页面保存将被 409 拦截——需刷新**）。
- **测试**：`webui_v2_test.py` **89/89**（+5）/ `webui_js_test.mjs` **42/42**（+3，线上）。

## v2.10 变更（2026-10-11 21:5x-22:0x）——新增动作「打开网页… / 执行命令…」（URL: / RUN:）

- **需求**：三端能力对齐——除 CLICK/APP:* 外，补「键 → 打开任意网址」「键 → 跑任意命令」两个通用动作
  （Mac key_bridge v1.11 / Windows win_actions v1.2 同构交付）。
- **协议**：动作串 `URL:<网址>` / `RUN:<命令>`——**仅 KEY down 触发**、0.6s per-value 防抖；
  **值不得含空格**（UDP 按空白分词是硬约束）、长度 ≤500 字符；T1 校验：mac / win 份放行，ATV 份拒绝。
- **实现（t1_webui v2.10）**：
  - `valid_action_for`：`URL:`/`RUN:` 前缀 → 后缀非空 + 无空格 + ≤500（否则 400 拒写）；
  - 前端 choices 各 +2：「打开网页…」「执行命令…」→ 点击弹 prompt 输值（值含空格当场拒绝并提示）；
  - `customApp` 泛化为 `CUSTOM_META` 三险哨兵（`__CUSTOM_APP__`/`__CUSTOM_URL__`/`__CUSTOM_RUN__`）；
    save 时清残留哨兵；opts 回显统一 `esc()`；`extLabel()` 显示缩略标签。
- 测试：离线 **84/84**（新增 URL/RUN 接受 / 大小写保真 / 空后缀 / 带空格 / ATV 拒绝 / >500 拒绝 /
  恰 500 接受 / 哨兵拒绝 / choices 断言矩阵）+ 前端 JS **39/39**（save 清哨兵 / URL 透传 /
  customApp 三路径 / opts 转义；顺带修正 JS harness 未模拟 Python 求值的历史问题）。
- 部署：T1 已上线（sha256 双端一致 `14bef4a25082fbc0bfe2e82c8b57f242e6ea0d8cf05093690c4f45166db970a2`；
  banner `t1_webui v2.10`；备份 `t1_webui.py.v29.bak-20261011-2200`）；
  live 冒烟：choices 含两入口 ✅、POST `RUN:bad cmd` / `URL:`（空值）→ **400 拒写且 rev 不变** ✅。
- ⚠ **用户浏览器需刷新 `/keymap` 页面**（旧页面无这两项；v2.7 起 rev 指纹亦会拦截旧页面回写）。
- 下一步（已就绪）：Mac 侧 key_bridge v1.11 已实弹验证（RUN 探针 / URL 打开）；Windows 侧随
  `update-win-receiver.ps1` v1.5 一并交付（win_receiver v1.5 大小写保真 + win_actions v1.3）。

## v2.9 变更（2026-10-11 17:2x）——`/keymap` 初始 tab 跟随「当前激活目标」

- **用户需求原话**：「进入按键配置页的时候，高亮选中的配置页应该是当前激活的设备。比如当前是macos，那配置页也应该是macos，现在总是atv」
- **实现**：`/keymap` 页 JS 启动流程改为 `boot()`——先 `fetch('/api/state')` 取当前激活目标，
  `TAB = s.voice_target`（白名单 `['atv','mac','win']` 校验，非法值忽略）→ 再 `load()` 渲染；
  请求异常 / 字段缺失 → **静默回退默认 atv**（不阻塞页面）。
- **效果**：切到 Mac 后打开配置页 → 直接停在 「macOS」tab（红字高亮 + 对应 13 键配置），无需手动点。
- 测试：离线 **73/73**（+5：POST voice_target=win / GET state 回读 win / 还原 atv / 页面含 `boot()` / 页面引用 `/api/state`）
  + 前端 JS **25/25**（+4：初始 tab=当前目标 mac / win 场景 / state 取不到回退 atv / 渲染行数对账）。
- **真浏览器实渲染验收**：Mac Chrome headless 实渲染 `/keymap` → **「macOS」tab 高亮选中**（当前激活=mac）✅；
  截图存档 `remote-hub/v29-keymap-verify.png`。（踩坑备注：WorkBuddy 沙箱内 Chrome 嵌套沙箱失败，须脱离沙箱 + `--headless=new --no-sandbox`。）
- 部署：T1 双端 md5 一致（`1a0e5abf9da76316f8391d5249bb0151`）；banner `t1_webui v2.9 启动 (voice_target=mac)`；
  备份 `t1_webui.py.v29.bak-20261011-172417`（=v2.8 内容，md5 `9b695645…`，可一键回滚；已同步 Mac 本地档链 v23→v29）。
- ⚠ **用户浏览器需刷新 `/keymap` 页面**（旧页面仍是"永远停在 atv"的老逻辑）。

## v2.8 变更（2026-10-11 12:2x）——新增动作「★ 上一页 / 下一页」（PAGEUP / PAGEDOWN）

- **场景**：把遥控器当翻页器——长按翻页（浏览长文档 / 列表 / 对话流）。
- **新增动作 `PAGEUP` / `PAGEDOWN`**（mac / win 动作清单；ATV 份拒绝——ATV 无此概念）：
  「★ 上一页（PageUp）」（keycode 116）/「★ 下一页（PageDown）」（keycode 121）。
- **实现**：Mac `key_bridge` **v1.10** 键表 +2（116/121）；T1 `voice_fwd` 通用透传无需改动；
  长按机制（v2.3）直接复用——`long=PAGEUP/PAGEDOWN` 由长按 tick（0.6s 阈值）触发转发。
- **生产配置**（mac 份，占用空闲长按位，单击行为不变）：
  - **#41 直播 长按 = PAGEDOWN**（下翻；短按仍 FOCUS_INPUT 跳输入框）
    - ⚠ 现网注记（后续调整）：下一页已移至 **#114 音量- 长按**；#41 长按位为空——本行为 v2.8 部署当时状态，现网以 keymap 为准
  - **#115 音量+ 长按 = PAGEUP**（上翻；短按仍 SPACE）
  - ⚠ 首个尝试（#127 菜单长按=PAGEDOWN）被**校验端拒绝**：连发与长按互斥（`repeat=true` 的键 `long` 被清空，
    见 `validate_keys_for`）——改用有空闲长按位的 #41/#115。
- **使用法（现网）**：**长按（0.6s）** #114 音量- = 下一页（PAGEDOWN）/ **长按** #115 音量+ = 上一页（PAGEUP）；短按行为不变。（v2.8 初版为 #41 长按=下一页，后调整）
- 测试：离线 **68/68**（+5：mac 接受 PAGEDOWN / mac 接受 PAGEUP / choices 含两项 / atv 拒绝 / win 接受）
  + 前端 JS **21/21**（沿用 v2.7 加固断言）；
  实机冒烟：GET rev ✅、choices 含两项 ✅、UDP `KEY PAGEDOWN DOWN` → `[serve] key PAGEDOWN(121) down OK` ✅。
- 部署：T1 双端 md5 一致（`9b695645…`）；备份 `t1_webui.py.v28.bak-20261011-1224`（v2.7 前档 `t1_webui.py.v27.bak-20261010-2109`）；
  **同步 `keymap.default.json` = 现网生产配置**（mac 份 6 处滞后一并修正：`TAB` / `SPACE+PAGEUP` / `APP:workbuddy`
  / `BACKSPACE+repeat` / `ESC+repeat` / `PAGEDOWN`）——「恢复默认」不再丢配置；reset 冒烟 rev 前后不变（语义无损）✅
- ⚠ **用户浏览器需刷新 `/keymap` 页面**（旧页面无该选项；且防旧页面回写）

## v2.7 变更（2026-10-10 21:0x）——配置回写加固（POST 指纹校验 → 409）

- **背景**：18:52 旧页面回写事故（v2.3 页面在 v2.4 上线后保存 → 旧逻辑覆盖 #158 连发配置）的彻底封堵。
- **机制**：`GET /api/keymap` 返回 `rev`（当前配置**语义级** sha256 前 12 位——与文件格式无关；内容变则 rev 必变、不变则稳定）；
  页面保存时回传加载时的 rev；服务端比对——**不符（含缺失）→ 409 拒绝**（提示"请刷新页面后重试"），**不写盘**；
  保存成功响应返回新 rev（前端即更新，连续保存不误报）。
- **影响**：部署后**旧页面（v2.7 前打开的）再保存会被安全拦截** ✅（替代原来"靠提醒刷新"的软约束）；
  bot/终端写入需先 GET 取 rev 再 POST（`curl` 惯例）；`/api/keymap/reset` 不变（语义独立，无覆盖风险）。
- 测试：离线 **63/63**（+9 rev 用例）+ 前端 JS **21/21**（+3：save 带 rev / 409 toast 提示刷新 / 警示符）；
  实机 HTTP 冒烟三态：GET rev ✅ / 无 rev POST→409 ✅ / 带 rev POST→200 且配置无损 ✅。
- 部署：T1 双端 md5 一致（`c25d4dcf…`）；备份 `t1_webui.py.v26.bak-20261010-2100`（v2.6 前档）、`t1_webui.py.v27.bak-20261010-2109`。

## v2.6 变更（2026-10-10 20:3x）——新增动作「★ 点击（激活当前焦点元素）」（CLICK）

- **用户需求原话**：「我把音量减号键定义成 TAB 键，通过这个 TAB 键可以切换到 WorkBuddy 的任务列表，
  但是切到焦点之后我摁回车键（也就是 OK 键），没法触发焦点，也就是说执行不了点击的命令。这个怎么解决？」
- **根因**（实证）：WorkBuddy（Electron）里 TAB 可达的焦点元素（任务条目 / 消息元素）**不响应合成回车**
  （组件未实现键盘激活；对照=模型选择器上 ENTER 有效）——但这类元素几乎都支持 AX 层 `AXPress`
  （与真实鼠标点击**完全等效**，任务条目往返双验证 ✅）。
- **新增动作 `CLICK`**（mac / win 动作清单；ATV 份拒绝）：「★ 点击（激活当前焦点元素 · 任务/列表项）」
  ——按键触发 → Mac 端点击**当前键盘焦点元素**（AXPress 四段策略 / 坐标兜底）。
- **实现**：Mac `key_bridge` **v1.9** `do_click()`（仅 DOWN / 0.6s 防抖 / 线程内不阻塞 UDP）
  → Hammerspoon `remotehub_focus.lua` v1.1 `clickFocused()`（四段策略，详见 `hammerspoon-focus.md` / `mac-key-bridge.md`）。
  T1 `voice_fwd` 通用透传无需改动；长按机制（v2.3）直接复用——`long=CLICK` 经 tick 触发转发。
- **生产配置**：mac 份 **#28 OK 长按 = CLICK**（短按回车不变；经 API 写入 + GET 复核 + 文件对账；`keymap.default.json` 已同步——「恢复默认 = 生产推荐」）。
  **使用法**：TAB（音量-）切到任务/列表项焦点 → **长按 OK（0.6s）** → 点击打开。
- 测试：离线 **54/54**（v2.5 的 50 项 + 4 项 CLICK 用例：mac 接受 / choices 含项 / atv 拒绝 / win 接受）
- 部署：T1 双端 md5 一致（`8680d323…`）、本地+远端 HTTP 200；备份 `keymap.json.bak-before-ok-click-203226`；
  ⚠ **用户浏览器需刷新 `/keymap` 页面**（旧页面无该选项；且防旧页面回写）

## v2.5 变更（2026-10-10 19:2x）——新增动作「★ 跳转输入框」（FOCUS_INPUT）

- **用户需求原话**：「有时候切换到窗口它无法获得焦点怎么办？没法输入到搜索框里头。有什么按键可以跳到输入框吗？」
- **新增动作 `FOCUS_INPUT`**（mac / win 动作清单；ATV 份拒绝——语义仅 Mac 端实现）：
  「★ 跳转输入框（聚焦输入框 · 修复失焦）」——按键触发 → Mac 端修复前台窗口焦点 + 聚焦窗口内首个可编辑元素
  （聊天输入框 / 搜索框 / 编辑器）。**同时配套「切换后自动焦点修复」**：APP 类切换动作成功后 +0.45s 自动修窗。
- **实现**：Mac `key_bridge` **v1.8** → Hammerspoon AX 层（新子系统，专档 `hammerspoon-focus.md`）。
  T1 `voice_fwd` 通用透传无需改动。
- **生产配置**：mac 份 **#41 直播键 = FOCUS_INPUT**（经 API 写入 + GET 复核；`keymap.default.json` 同步——「恢复默认 = 生产推荐」）；
  用户可随时在网页把任意 mac/win 键改绑该动作
- 测试：离线 **50/50**（v2.4 的 46 项 + 4 项 FOCUS_INPUT 用例：mac 接受 / choices 含项 / atv 拒绝 / win 接受）
  + 前端 JS **18/18**（+2：#41 单击=跳转输入框 selected / 下拉含该选项）
- 部署：T1 双端 md5 一致、banner `t1_webui v2.5 启动`；⚠ **用户浏览器需刷新 `/keymap` 页面**（旧页面无该选项；且防旧页面回写）

## v2.4 变更（2026-10-10 18:4x）——「按住连发」UI 化（长按列可自助选连发）

- **问题**（用户反馈：「有的键可以设长按，有的不可以」「把返回键改成 BACKSPACE 后，只能设成单长按，一选就不好用」）：
  ①「连发」能力此前只能经 API 写入（=写死在个别键上），网页无自助入口；
  ② 已开连发的键，「长按」列被禁用（=用户看到的"有的能设有的不能"）；
  ③「长按」列选 BACKSPACE 的语义是「按住 0.6s 后触发一次」——不是"按住连续删"，故"一选就不好用"。
- **改造**：**长按列新增首选项「⟳ 按住连发（连续重复）」**——
  - 选它 = repeat=true（按住时单击动作连续重复，0.12s 节流）→ 如 BACKSPACE =「单按删一个 / 按住连续删」
  - 与「长按动作」（0.6s 触发一次）在同一列**二选一**；所有非锁定键的长按列不再禁用
  - 保存时 repeat 由长按列派生（前端转译）；服务端接受哨兵 `__REPEAT__`（等价 repeat=true，并清 long/double 互斥项；哨兵不落盘）
- **生产配置**：#158 返回键 = `BACKSPACE + 按住连发`（= 用户想要的"单按删一个 / 按住连续删"；经 API 写入并 GET 复核）
- 测试：离线 **46/46**（原 37 项回归 + 9 项哨兵用例）+ 前端 JS 逻辑 **16/16**（新增 Node harness `webui_js_test.mjs`：DOM stub 验证 渲染 sentinel selected·非禁用·save 派生往返）
- 备份：`t1_webui.py.v23.bak-20261010-1845`（v2.3 前档）/ `keymap.json.bak-20261010-1845-preRepeatOpt`
- **18:52 旧页面回写事故与恢复**：用户 18:39 打开的 v2.3 旧页面在 v2.4 上线后保存 → 旧逻辑回写覆盖
  #158 连发配置（`repeat` 被旧值继承回 false）→ **已重写恢复**；#127=ESC（用户主动改）保留。
  教训：**部署新 UI 后须提醒用户先刷新页面**；加固待做 = POST 指纹校验（页面加载值与当前不一致 → 409 提示刷新）

## v2.3 变更（2026-10-10 17:3x-17:4x）——「长按解禁 + 自定义应用 + 应用选择器」

- **长按下拉解禁**（用户反馈「长按还是没有选择」）：mac/win 份 long 字段从「强制置空」改为**可选**
  （与 ATV 同款 0.6s 阈值语义；long 与 repeat 互斥、校验端自动清 repeat；**双击仍不支持**）
- **新增两项动作入口**（用户反馈「没有把打开某个应用做进去」）：
  ① 预设 `★ 应用选择器（APP:PICK）`（长按主页键用）
  ② `打开应用…（自定义输入）`——选它即弹输入框，输入应用名（如 `Steam`）→ 存为 `APP:<名>`；含空格拒绝（破坏 UDP 协议）
- **主页键（#102）生产绑定：短按 `APP:CYCLE`（轮询不变） / 长按 `APP:PICK`（唤出应用选择器）**
  （17:42:35 经网页 API 写入；备份 `keymap.json.bak-20261010-1743-prePick`；默认档 `keymap.default.json` 同步）
- 配套组件：T1 `voice_fwd` **v2.3**（长按 long 支持）+ Mac `key_bridge` **v1.7**（PICK 触发 + 选择器路由）
  + `AppPicker.app`（浮动选择面板：左右选 + OK 打开 + Esc/10s 取消、不抢焦点；说明见 `mac-key-bridge.md`）
- 测试：离线 **37/37**（v2.2 的 30 项 + 7 项新用例：长按保留/接受 APP:PICK/choices 含新项/自定义占位拒止/长按清 repeat 等）

## v2.2 变更（2026-10-10 16:5x 应用轮询 CYCLE）

- mac/win 下拉新增 `APP:CYCLE`（**全部轮询**：连按主页键沿快照环状推进遍历所有打开的应用）
- 实现 = Mac `app_switch` v1.1 `cycle`（冻结快照 + 前台校验续期；快照=窗口前后序 ≈ 最近使用序，
  取不到回退名称序；用户手动换应用/超 30 分钟自动重建）+ `key_bridge` v1.6 放行 CYCLE
- 绑定记录：**主页键（#102）从 `APP:TOGGLE` 改绑 `APP:CYCLE`**（16:56 经网页 API 写入；
  全字段 diff 恰 1 处 / atv·win 零改动）
- 测试：离线 **30/30**（v2.1 的 28 项 + 新增 2 项 CYCLE 用例：接受 APP:CYCLE / 下拉含 CYCLE）

## v2.1 变更（2026-10-10 15:3x 应用动作）

- mac/win 动作清单新增 6 项（下拉可选）：`APP:TOGGLE`（最近两应用间跳 ≈⌘Tab）/ `APP:NEXT`（循环下一个）/
  `APP:微信` / `APP:飞书` / `APP:Obsidian` / `APP:Safari`（打开/切换到该应用）
- 服务端校验：mac/win 份放行 `APP:` 前缀（非空、无空格；空格会破坏 UDP 协议解析故拒止）；ATV 份不适用（拒绝）
- 执行端 = Mac `key_bridge` v1.5 → `app_switch` 工具（NSWorkspace 激活, 非键盘注入, 无需 TCC）
- 绑定记录：**主页键（#102）→ `APP:TOGGLE`**（15:35 经网页 API 写入；全字段 diff 恰 1 处；待真机验收）
- 测试：离线 **28/28**（v2.0 的 22 项 + 新增 6 项 APP: 用例）

## v2.0 变更（2026-10-10 用户指示"keymapping 需要有三份"）

- `keymap.json` 升级 v2：`{version:2, hold_threshold, double_window, targets:{atv,mac,win}}`
  - **目标决定用哪一份**：`voice_target`（主页三按钮）选中哪个目标，全遥控器按键（含语音键）按该目标语义生效
  - atv 份 = pyatv 动作（小写/特例）；mac/win 份 = 键盘动作（大写 ENTER/ESC/UP/DOWN/LEFT/RIGHT/SPACE/TAB/BACKSPACE）
  - mac/win 份语义：单击+按住连发（长按/双击当时暂不支持——**长按已由 v2.3 解禁**，双击仍不支持）；repeat 键（方向）由 T1 侧
    按 0.12s 节流补发 DOWN 驱动"按住连续移动"（macOS 对合成键不做系统级自动 repeat）
  - 兼容 v1 旧结构（无 targets 时自动视为 atv 单份）
- 按键分流（T1 双服务各管一段，互不干扰）：
  - `relay_min.py` v0.10：**仅 target=atv 生效**；target=mac/win 时全部按键让位（含语音键）
  - `voice_fwd.py` **v2.1**：**仅 target=mac/win 生效**；非语音键 → `KEY <动作> DOWN/UP` → Mac `:8791 key_bridge`；**repeat 键自建连发**（DOWN 满 0.5s 后按 0.12s 主动补发 DOWN——遥控器无 EV_REP，长按不产生重复事件）
  - 配对纪律（v1.1 语音规则推广到按键）：UP/连发永远发回 DOWN 时的目标与动作 —— 按住中切换目标不断键

## 架构

- `t1-webui.service`（T1 第 7 个常驻服务）：纯标准库 HTTP（`/usr/bin/python3`），只读写两个状态文件
- 状态交换 = 文件（web 崩了不影响遥控/语音；反之亦然）：
  - `voice_target`（atv/mac/win）→ 读端：`relay_min.py` v0.10 + `voice_fwd.py` v2.0
  - `keymap.json` → 读端：relay + voice_fwd，**按键事件时 mtime 检测热重载**（三级保护：keymap.json → keymap.default.json → 代码内置兜底）
- 双击模型（仅 ATV 份）：仅当键配置了"双击"才启用单击延迟判定（默认全关 = 零延迟）；
  长按优先于双击；repeat 键为按住连发，不允许长按/双击

## API（v2.0）

- `GET /api/state` → `{voice_target}`
- `GET /api/keymap` → `{cfg(v2), choices:{atv,mac,win}, order, repeat_opt}`（v2.4：repeat_opt = 长按列「⟳ 按住连发」选项数据源）
- `GET /api/remote` → `{available, connected, percent, note?}`（v2.17：遥控器电量；busctl 读 BlueZ Battery1 缓存，未连接/未上报 → `available=false` 降级）
- `POST /api/voice_target` `{"target":"atv|mac|win"}`
- `POST /api/keymap` `{"target","keys":{...}}` → 只替换该目标份（其余目标保留当前值）；字段值优先序：本次提交 > 当前配置 > 默认
- `POST /api/keymap/reset` `{"target"}` → 恢复该目标默认；不带 target = 全部恢复
- 服务端校验：分目标动作白名单 / 13 键锁定 / locked 键保护 / repeat 互斥清理 / mac·win 双击置空；v2.4 起 long 接受哨兵 `__REPEAT__`（转 repeat=true）；v2.5 起 mac/win 白名单含 `FOCUS_INPUT`（ATV 拒绝）

## 文件清单（T1 `/root/remote-hub/`）

> 注：本节为 10-10 前后 v2.x 交付时快照（版本号未随每次迭代维护）；**现网版本以上文各变更节为准**。

| 文件 | 说明 |
|---|---|
| `t1_webui.py` v2.5 | web 服务（三 tab + v2 API + APP: 应用动作/轮询/选择器 + 长按解禁 + 自定义应用 + 按住连发可选 + **FOCUS_INPUT 跳转输入框**） |
| `t1-webui.service` | unit（enabled 自启） |
| `relay_min.py` v0.10 | 三份 keymap 消费（target=atv）+ 目标门控 |
| `voice_fwd.py` v2.3 | mac/win 键转发（语音 + 普通键双通道 + 自建连发 + 长按 long） |
| `keymap.default.json` v2 | 三份默认键位 |
| `keymap.json` v2 | 运行时配置（webui 维护；双服务热重载） |
| `voice_target` | 运行时状态 |
| `relay_logic_test.py` / `key_fwd_logic_test.py` | 离线测试（14+14 项） |
| 备份 | `relay_min.py.v09.bak-20261010-022300` / `voice_fwd.py.v11.bak-*` / `t1_webui.py.v10.bak-*` / `t1_webui.py.v20.bak-20261010-1535`（v2.1 前档） / `t1_webui.py.v21.bak-20261010-1656`（v2.2 前档） / `voice_fwd.py.v20.bak-20261010-1712`（v2.1 前档） / `keymap.json.v1.bak-*` / `keymap.json.user-copy-20261010-0213` / `keymap.json.bak-20261010-1535-preApp` / `keymap.json.bak-20261010-1650-preCycle` / `keymap.json.bak-20261010-1712-preBkspRepeat` / `voice_fwd.py.v21.bak-20261010-1755`（v2.3 前档） / `t1_webui.py.v22.bak-20261010-1803`（v2.3 前档） / `keymap.default.json.bak-20261010-1803` / `keymap.json.bak-20261010-1743-prePick` / `key_fwd_logic_test.py.v21.bak-20261010-1755` / `t1_webui.py.v23.bak-20261010-1845`（v2.4 前档） / `keymap.json.bak-20261010-1845-preRepeatOpt` / `t1_webui.py.v24.bak-20261010-192319`（v2.5 前档，双端） / `keymap.default.json.v24.bak-20261010-192319` |

## ATV 份迁移逐键对比（用户要求"别把 ATV 配置改错"，程序化全字段比对）

| 键 | 迁移前(v1) | 迁移后(v2 atv 份) | 一致 |
|---|---|---|---|
| 电源 #116 | `__POWER__` / - / 单发 | `__POWER__` / - / 单发 | ✅ |
| 语音 #63 | 锁定 / - / 单发 | 锁定 / - / 单发 | ✅ |
| 主页 #102 | `home` / `home_hold` / 单发 | `home` / `home_hold` / 单发 | ✅ |
| 返回 #158 | `menu` / - / 单发 | `menu` / - / 单发 | ✅ |
| 上 #103 | `up` / - / 连发 | `up` / - / 连发 | ✅ |
| 下 #108 | `down` / - / 连发 | `down` / - / 连发 | ✅ |
| 左 #105 | `left` / - / 连发 | `left` / - / 连发 | ✅ |
| 右 #106 | `right` / - / 连发 | `right` / - / 连发 | ✅ |
| OK #28 | `select` / - / 单发 | `select` / - / 单发 | ✅ |
| 音量+ #115 | `volume_up` / - / 连发 | `volume_up` / - / 连发 | ✅ |
| 音量- #114 | `volume_down` / - / 连发 | `volume_down` / - / 连发 | ✅ |
| 直播 #41 | `__LAUNCH__:com.zentraedi.zspaceTV` / - / 单发 | 同左 | ✅ |
| 菜单 #127 | `__PLAY_PAUSE__` / - / 单发 | 同左 | ✅ |

**结论：13 键 × 全字段（含 label/note/locked/double/repeat）程序化比对 13/13 一致。**（对比脚本：迁移时在 T1 现场以 json 序列化 sort_keys 全等 assert；本地留底 `keymap.json.t1-live-bak-20261010-022300` / `keymap.json.v1.bak-local`）

## 回滚

```bash
# 回滚到 v1 时代（单份配置）
ssh t1root 'cd /root/remote-hub && \
  cp keymap.json.v1.bak-20261010-022300 keymap.json && \
  cp relay_min.py.v09.bak-20261010-022300 relay_min.py && \
  cp voice_fwd.py.v11.bak-20261010-022300 voice_fwd.py && \
  cp t1_webui.py.v10.bak-20261010-022300 t1_webui.py && \
  systemctl restart t1-relay t1-voice-fwd t1-webui'
# Mac 侧配套回滚（如已部署 key_bridge）：停用新服务
launchctl bootout gui/501/com.remotehub.key-bridge 2>/dev/null; true
```

## 验证记录

**v1.0（01:57–02:00）**：离线状态机 10/10 全绿；三服务 active；Mac→T1:8765 跨机 GET/POST 全通。

**v2.0（02:19–02:25）**：
- webui 离线全量测试 **22/22 全绿**（v1 归一化 / 三 tab 读写 / 分目标保存 / 校验拒绝非法动作×2 / locked 保护 / repeat 互斥 / 分目标 reset / 全量 reset / 阈值钳制 / 目标切换）
- T1 现场：relay 逻辑测试 **14/14**、key_fwd 逻辑测试 **14/14**（含"现网 mac OK=ENTER"集成断言）
- ATV 份迁移全字段比对 **13/13 一致**
- 三服务以新版本重启：relay v0.10 / voice_fwd v2.0 / t1_webui v2.0 就绪日志正常
- T1→Mac:8791 网络连通（ping/pong）；key_bridge v1.0 running

**v2.0 真机验收（10-10 13:24 完成 ✅）**：用户实测「遥控器 → Mac 键盘注入」全链通过（OK=回车 / 返回=Esc / 方向键；用户：「可以了」）。
配套终局升级：Mac 注入链 key_bridge **v1.4**（serve 常驻主路径 + 15s 熔断 submit 兜底——治 launchctl 每事件 submit 的丢事件问题；
CGPost.app 经用户手动加入辅助功能授权）。详见 `mac-key-bridge.md`。

**v2.4（10-10 18:4x）**：离线 46/46（+9 哨兵用例）+ 前端 JS 16/16（Node harness）；T1 部署双端 md5 一致、服务 v2.4 就绪（banner 核实）；#158 返回键配成 `BACKSPACE + 按住连发` 并 GET 复核；
真机验证（按住返回键连续删 / 网页长按列选「按住连发」自助配置）待用户。

**v2.5（10-10 19:2x）**：离线 **50/50**（+4 FOCUS_INPUT 用例）+ 前端 JS **18/18**（+2）；T1 部署双端 md5 一致、
banner `t1_webui v2.5 启动`；mac 份 #41 配 FOCUS_INPUT 并 GET 复核；Mac 侧 key_bridge v1.8 重启 + UDP 冒烟全通
（`[focus] 跳输入框 OK | OK WorkBuddy role=AXTextArea fx=0.50 fy=0.85 src=cache ...`）。真机验收待用户。

## 真机验收结论（10-10 13:24）

- **核心链路 ✅ 通过**：遥控器 OK→回车 / 返回→Esc / 方向键 → Mac 侧日志实证（ENTER down/up 序列进 serve 注入链）
- 主页三按钮切换 ✅（用户已实际操作：目标切至 Mac）
- `/keymap` 热重载、切回〔ATV〕恢复控 TV：机制已离线验证，留待日常使用自然确认（观察点：relay/voice_fwd 日志出现 `配置已热重载`）

## 已知边界

- 局域网内无鉴权（勿暴露公网）
- 配了双击的键（仅 ATV 份可配）单击有 0.3s 延迟
- 63 语音键锁定不可配（防呆）
- mac/win 份长按自 v2.3 支持（双击仍不支持）；v2.4 起「长按」列 = 按住行为（「⟳ 按住连发」或某个动作，二选一互斥）；音量键在 Mac 份暂无键盘注入方案（需要媒体键系统事件注入，后续按需扩展）
- Windows 目标已全链部署（10-11 起）：按键 / 语音 / 音频链均实机验收，键位与 Mac 100% 对齐；见 `windows/README.md`
- mac 键注入需 Mac 侧**两个服务**在跑：`key_bridge`（:8791 收键）+ `cgpost-serve`（CGEventPost 注入器常驻；失联时自动熔断外走 submit 兜底）；见 `mac-key-bridge.md`
- **FOCUS_INPUT（跳输入框）**：mac / win 两端均已实现（win 自 `win_actions` v1.2 扩展动作起；10-11 键位对齐含 #41）；微信等内容层无 AX 的应用
  自 10-14 起改为**底部中央兜底点击**（Mac lua v1.5 引入 → **v1.6 修正**：前台提升防遮挡 + 落点距窗底 105px；win_actions v1.15 仍为 `(0.5,0.92)`，是否对称调整待复测；报 `NOEDIT+CLICK`；非常规布局仍可能点空）；
  **鼠标模式内短按 #41 也照常跳输入框**（voice_fwd v2.8 起放行转发；此前被模式层吸收）。细节与局限见 `hammerspoon-focus.md`
