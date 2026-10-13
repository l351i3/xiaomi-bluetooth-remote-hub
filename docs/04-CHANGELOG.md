# CHANGELOG —— 项目全史（2026-10-07 ～ 2026-10-14）

> 组织方式：**按日正序**（叙事式 changelog——本项目是「从爬坑到建成」的完整故事）。
> 版本号以各件现网版为准；历史版本照引。速查表见文末附录。
> 数据源：四天工作日志（.workbuddy/memory/）+ 各文件 changelog + MEMORY.md。

---

## 前史 · 2026-10-07 及以前（背景）

- ZCode（另一 AI）在斐讯 T1（PHICOMM-T1）上做小米遥控器实验：**eMMC 6.12.65 内核被 5.15 覆盖且未备份**（只备了 uEnv）。
- 5.x 两装两败：能启动，但一按遥控器键 → BT/HOG 内核卡死 → 硬件看门狗复位循环 → **关机链路异常波及全家网络**（用户记忆中的"两次"）；蓝牙始终未通。
- 用户下令「停止所有工作，恢复 T1 最初状态」→ ZCode 还原到一半，会话中断 → 本项目从此接力。

---

## 2026-10-08（D1）：还原 · 蓝牙修复 · 关机链路异常修复开局

### 1. 系统还原收尾（接力 ZCode）✅
- eMMC /boot 清理（删 5.15 内核、4 个实验 dtb）；purge bluez、修复 device-tree-compiler 误卸；U 盘 uEnv/dtb 还原。
- 01:27 拔 U 盘重启闭环：eMMC 6.12.65 引导、9 服务全 active、蓝牙回"最初无栈"状态。

### 2. ★ 蓝牙根因攻坚 → 全链路打通（全天核心）
- 逐层排除：dtb（与"实测可用"版逐字节同）→ pinctrl/时钟 → `-84` 噪声 → 固件/硬件。kprobe 判决："UART 通、芯片不答"；最终定位 **芯片处于 BootROM 态，需要用户态注入固件**（主线 hci_bcm 假设不成立）。
- 途中两次「裸 tty 高频实验打死 T1」事故 → 定下硬约束：**禁止高频开关 tty**。
- **里程碑（07:37–08:50）**：`btflow`（逐字节固件下载，500µs/字节）下载 280 块 CC=279/ER=0 → 原位挂 HCI（ldisc）→ **hci0 UP RUNNING（真 MAC 80:C5:F2:XX:XX:XX）**、扫描到 14 个 BLE 设备 errors:0。
- 开机自动化：`t1bt-btinit.sh` + `t1bt-bluetooth.service`（8 次重试 / 30s 巡检自愈）；重启验收 + kill 自愈实测全过。

### 3. 交付：蓝牙版 Armbian 镜像 ✅
- 官方镜像注入 btflow 全套 → `Armbian_26.11.0_..._bluetooth.img.gz`（1.05G，SHA256 `e0d5320d…`）——「刷完即用」。

### 4. RC003 遥控器配对 + 13 键实测 ✅
- 配对姿势权威 = **长按【直播键】3~5 秒**（非网传 Home+菜单）；Python dbus 直控（`bt_agent_pair.py`，RegisterAgent + RequestDefaultAgent）一次通过。
- 13 键全量采集（`rc003-keymap.md`）；下午认证失败（密钥不匹配 0x05）→ remove 重配 → 全键事件流验证 100% 一致。

### 5. 事故与关机异常案成立
- 抢连拉锯（12:28–12:45）：Mac×T1 抢遥控器 → T1 失联。终局取证：**遥控器电源键被 T1 logind 拦截关机**（`HandlePowerKey=poweroff` 实锤）→ 加 `ignore` 防护。
- 用户纠偏："T1 已前后 3 次搞死网络，绝不是偶然"→ **关机异常案独立成案**（10-07 两现场 + 10-08 一次，三档案齐）。

### 6. ★ 关机链路异常修复实验链（受控实验 ×5）
- 实验 1/2：常规关机会触发异常（延迟 12~15s）；**只拔网线 = 立刻恢复**；插回不复现（一次性事件）。
- 实验 4A/4B：`eth0 down → poweroff` **干净**（根治候选实证）；实验 5A/5B：quiet-down 牺牲"插线唤醒"（用户拍板：只要根治）。
- 钩子落地：`t1-quietdown.service`（每次关机先放网卡）→ 验收 0 异常。
- **重大副作用发现**：插线唤醒（拔线关机→插线自动开机）——后被钩子牺牲。

### 7. 异常机理收口取证 ✅
- 完成跨设备双端取证（逐秒连通性探针 + 上游设备侧日志），异常机理全链条闭环；
  技术细节留维护者内部报告，暂不公开。

### 8. watchdog 修复 + 安全体检 ✅
- 真因：T1 硬件 watchdog 一直在喂狗但**从未配置任何检测项**（"永远活着、永远不判故障"）→ 配 `t1_health`（进程存活 + D 进程数判据）+ 故障注入验收（~100s 自动重启）。
- 安全体检（用户问"会不会有毒"）：12 类检查全可溯源，**无任何恶意程序**。

### 9. ★ Armbian T1 网卡补丁开工（dwmac-meson8b · 链路异常终极根治）
- 用户授权自改内核；源码级验尸：`dwmac-meson8b` **无 .shutdown 回调**（连上游 master 也没有）→ 关机时内核从不管网卡 = 异常机理闭环。
- **网卡补丁**：`.shutdown = rtnl_lock + dev_close + msleep(5000)`；**checkpatch 0 errors/0 warnings**（"ready for submission"）；`0001-net-stmmac-dwmac-meson8b-drop-the-link-before-power-.patch`（39 行，commit `be53dcb`）。
- T1 上整内核编译启动（`make -j6 LOCALVERSION=-ophub Image`，21:59）。

---

## 2026-10-09（D2）：内核补丁验收 · ATV 中继上线 · 语音链奠基

### 1. ★ Armbian T1 网卡补丁（dwmac-meson8b）验收 ✅ + 钩子退役
- **网卡补丁 EXP-19 实测通过**：netconsole 实时捕获补丁打印（`meson8b-dwmac … shutdown: bringing the link down before power-off`），带线关机全程零异常 → **纯内核方案成立** → `t1-quietdown` 钩子退役（保留脚本归档）。
- N1 盒子排除实验：真·软关机 → 全网零卡顿 → **N1 非触发源**实测收口。
- **★ 上游设备缺陷报告完成**：提交格式（10 节）定稿——环境拓扑 / 复现时间线 / 关键判据 / 修复建议 / 边界声明；按负责任披露流程处理中，**未对外发送**。

### 2. 蓝牙链恢复 + 三服务开机自启拍板 ✅
- 新内核首跑：btflow try1 成功 → hci0 UP → 按键回连 + 事件流全通。
- 拍板 enable：`bluetooth + t1bt-bluetooth + t1-evwatch` 三件套（重启实测零人工全自动）。

### 3. ★ ATV 中继上线（M2–M4，relay_min v0.2 → v0.7）
- **M2**：ATV4K 配对（Companion + AirPlay 双协议，凭据落盘 600）。
- **M3**：最小中继 daemon 通电（方向+OK+返回，38/38 零失败）→ **RC003→T1→ATV 全链首次贯通** 🎉。
- **M4 迭代**（用户实测驱动的 6 轮）：
  - v0.2 全键映射 + 断连重挂；v0.3 菜单=返回/长按=切换器 + 直播=开极空间（MRP 隧道探明）；
  - v0.4 主页长按=控制中心、返回=播放暂停；**v0.5 修复 play_pause"假成功"**（pyatv 媒体通道状态依赖 → 改 HID 直发 `(12,0xCD)`）；
  - v0.6 键位微调（控制中心回主页长按）；v0.7 语音键=一键开 YouTube（bundle 实机核实）。
  - 定案：主页=单击主屏/双击切换器/长按控制中心；电源唤醒电视不亮=电视侧 CEC 局限（收口）。

### 4. ★ 语音链全链打通（当日最大成果）
- 侦察：RC003 含 **ATVV 语音服务**（ab5e0001）→ GATT 预探通过（HID 连接与 GATT client 共存）。
- 三端方案拍板：音频 → **电脑虚拟麦克风 → 本机输入法（不做 Whisper）**；切换=网页；配置=网页。
- Mac 合成：CGEvent 判死 → **IOHIDPostEvent 打通** ✅（`iohid_post`）→ 22:04 用户确认"出文字了"。
- T1 接线 + ATVV 抓流成功（`atvv_probe` v0.1→v0.2）→ 解码管线 → **22:45 端到端闭环**：遥控器当无线麦克风 → 文字上屏 🎉。
- 服务化：T1 六服务自启验收；Mac LaunchAgent ×2（`voice_bridge` v0.2/v0.5）。
- **TCC 危机**（23:02）：注入事件被静默丢弃 → 架构定稿「**CGPost.app + kickstart 直跑注入**」。
- v0.5/v0.6 智能长短按（按住说话/短按切换模式）。

---

## 2026-10-10（D3）：三端框架成型

### 1. 语音链 v1.1 修复 + 双 E2E 实证
- 00:12–00:30 根因定位（FS 闭环丢事件）→ `voice_bridge` v1.1 → 双端到端实证。

### 2. 注入链终局 + 组合键调查
- `CGPost.app serve 常驻`（+15s 熔断→submit 兜底）终局定稿；iohid_post 事故修复。
- 组合键注入调查：五路线实测**全否决**（用户态不可行，证据归档）。

### 3. 功能扩张（用户需求驱动）
- 「切换应用」功能（app_switch v1.0）；语音键故障修复；`atvv_receiver` v1.2（AGC→24 小声增强）。
- 主页键「全应用轮询」CYCLE；长按连发修复（自建 tick）；**三项需求落地**：网页长按解禁 + 「打开应用…」自定义 + 主页长按应用选择器（AppPicker v1.0）。
- skill「小米蓝牙遥控器切换」开发 + 双装 ✅；用户全量验收「测试通过」。
- 「按住连发」UI 化；旧页面回写事故 → 恢复（后升级为 rev 指纹）。

### 4. ★ 焦点子系统 + 健康守卫
- `remotehub_focus.lua`：`focusInput()` 五阶段 + `clickFocused()` 四段（Hammerspoon 执行）。
- `hs_health.py` v1.0：12 项检查 + 自动修复 + 通知（用户拍板"保持自动更新 + 自检"）。
- **CLICK 动作交付**（点击焦点元素——Electron/Chromium 不响应合成回车问题的正解）。

---

## 2026-10-11（D4）：Windows 接入（三端成型）

### 1. 加固与收尾（凌晨）
- `t1_webui` v2.7：**rev 指纹**（旧页面回写 → 409 拒写）；v2.8 翻页动作（PAGEUP/PAGEDOWN）；Tailscale watchdog 恢复。

### 2. ★ Windows 全接入
- 接线（17:35）：PING 双通 + `voice_fwd.WIN_IP` 生效。
- `win_receiver` v1.0 → v1.1（延迟修复：异步日志）→ v1.2（扩展动作 Mac 对等）→ v1.3（麦克风切换）→ v1.5（大小写保真）→ v1.6（防抖首击修复）。
- **延迟真相**：BLE HOG 断连循环（延迟谜题实锤）。
- Mac 语音故障全链修复（Notify 幽灵订阅 → 重启 bluetoothd → DEV_MATCH 加 "MI RC"）。
- 音频链：`atvv_service` v1.1（双播 Mac+Windows）+ `win_audio_receiver` v1.0（VB-Cable）→ 用户确认"语音可以工作"。

### 3. ★ 键位对齐 + 补丁回收机制
- win 键位 100% 对齐 mac（全量 diff=0）；`keymap.default.json` 同步 = 现网；用户立规「对齐 mac，不得逐项询问」。
- Windows 扩展动作 v1.2（CLICK/FOCUS_INPUT/APP:* 移植）→ **实机验收 4/4**。
- **补丁回收闭环**：Windows 回传 patched → 合入上游 → 重分发（教训固化：**patched 必回收 + 连测试件对账**）。
- 麦克风按需切换（方案 V）：`win_audio_switch` v1.2（先切后注入；松开 2s 恢复）。

### 4. ★ URL/RUN + 选择器 v2 系列
- `key_bridge` v1.11 + `t1_webui` v2.10：**URL:<网址> / RUN:<命令>** 全链。
- `APP:PICK` 选择器 v2（常驻 Tk 线程根治崩溃 + 图标网格 + 高 DPI）→ v2.1（修剪/名称/宿主进程）→ v2.2（光学归一 + 单元格固定尺寸根因修复）→ v2.3（长名滚动 + 防抖，win_receiver v1.6）。
- 「理想收敛轮」：Windows 逐行核对上游补丁齐全、哈希一致。

---

## 2026-10-12（D5）：选择器打磨 · 长按关闭 · 收官

### 1. picker v2.4 → v2.6
- v2.4：**网格方向导航**（↑↓=垂直）+ **UWP 真实图标 Shell 通路**（GUID 修复 `bcc18b79`；`bcc38b79` 错一位 → 曾 100% 静默失败）。
- v2.5：灰调配色（对齐 Mac）；v2.6：选中格图标透明融合 + 一键更新包（.bat）+ `AppPicker` v1.3（长名滚动）+ key_bridge VERSION 修复。
- 附带：清理 T1 磁盘冗余（549M→108K，磁盘占用降至 21%）。

### 2. ★ 长按电源键「关闭当前应用」全链交付
- Mac：`app_switch` v1.2（close，NSRunningApplication.terminate 优雅退出）+ `key_bridge` v1.12（APP:CLOSE，2s 强防抖）。
- Win：`win_actions` v1.10（WM_CLOSE + close_poll 轮询 + UWP 真身窗口）；离线回归 329 全过。
- T1：keymap #116 long=APP:CLOSE + `t1_webui` v2.11（下拉 + 特判文案）。
- 用户双端实测：「基本没发现什么问题」✅。

### 3. 收官
- T1:8000/8001 分发服务关停；项目整理（本文档集）启动。

### 4. ★ GitHub 三库发布（21:2x–21:4x）✅
- 用户拍板三库方案落地：① `phicomm-t1-system-fix`（公开）② 上游设备缺陷报告（**私有**，库名不公开）③ `xiaomi-bluetooth-remote-hub`（公开）。
- 导出流水线 `publish_export.py`（暂存 → 镜像 → 脱敏 → 中立化 → 披露收敛 → 验证 → 门禁）：三树验证 0 问题；公开树自动安装 `.githooks` 门禁；反向哨兵 fail-closed。
- 门禁实测拦截通过（泄漏样件 commit 被拒，exit 1）；三库首提，push 后线上核对（文件清单逐一比对一致）。
- 另：发布树 `.gitignore` 由流水线生成；`sync-publish.sh` 一条龙更新脚本入列（维护约定见《05》§七）；win 链路「已上线」文案全链路同步（`t1_webui` v2.12 / `voice_fwd` v2.4）。

### 5. ★ 发布内容隐私复核（22:0x–22:3x）✅
- 触发：用户问询「上传到 GitHub 的内容是否存在个人数据」→ 对三棵发布树全量复核 + 机制加固。
- **复核结论**：私钥 / 个人邮箱 / 手机号 / WiFi 口令 全部 0 命中；发现并即修 6 类漏网：
  ① 私有库：日志 `mac:` 前缀形态的 MAC 整段漏网（原脱敏正则前边界排除冒号；413 处）→ 补规则后统一打码 453 处（含后缀形态），另 7 组 EUI-64 形态 434 处；
  ② 私有库：SSID 实名（2 个：`SSID` / `SSID_5G`；出现于无线配置转储 / mesh 探测记录 / HTML 页头）→ 泛化打码 70 处；
  ③ 私有库：用户名大小写变体 `username-iPhone` → 打码 46 处；
  ④ `phicomm-t1-system-fix`：救援 U 盘验证快照内 tailscale 网段地址未脱敏（2 处）→ 占位化；
  ⑤ 本库：Windows 部署公钥（`setup-windows.ps1`，用途=写远程主机 `authorized_keys`，非私钥）→ 占位化；
  ⑥ 《06》口径文档自身两处网段 CIDR 表述被新规则误伤（自指）→ 改 `100.64/10` 简写规避。
- **机制加固（双层）**：export 层统一形态检查（公开 / 私有树同跑）+ 发布树门禁新增形态扫描（MAC 三形态 / tailscale 网段 / SSID / SSH 公钥）——「禁词哈希表」管具体词、「形态检查」管模式；门禁工具自身不入扫描面（自指豁免）。
- **门禁红灯实测**：注入待脱敏形态（MAC / tailscale / SSID）的样件 → commit 被拦（exit 1）✓；三种 MAC 形态逐一验证命中标签。
- 三库修复重推；口径文档同步随行（本档 + 《03》 + 《05》 + 《06》）。
- **▶ 历史重写（当晚）**：修复只清洗「最新版本」——已推送的旧提交历史仍可被逐条翻阅（含上述标识）；故三库历史已重写为隐私复核后的**单次发布提交**并强推，此前任何阶段性提交哈希不再有效（本档已同步移除哈希引用）。

---

## 2026-10-13（D6）：鼠标模式全链交付 · 用户首测修复轮 · presence 心跳核心 · GitHub 维护推进

### 1. GitHub 三库维护（凌晨）
- 三库协议统一 **MIT**（`LICENSE` 由发布模板注入；README 许可段同步补齐）；BatteryBar 项目隐私审查通过（本来即 MIT）。
- 历史审计工具入列（`docs/tools/history-audit.py`，规则与脱敏/导出同源）——三树基线 321 对象 0 命中。
- **旧对象清除申请已提交（工单 #4849797）**：历史重写后旧对象按 SHA 仍五通道可达，16 个旧 SHA 基线已复测；等待 Support 首复（1–3 工作日）。
- 旧发布目录 `~/remote-hub-publish/` 核查为导出产物（零引用、可全量重建）→ 移入废纸篓存档。

### 2. presence 心跳注册制 —— 核心模块完成（接线中）
- `presence.py`（T1 守护）: UDP:8790 注册表（role→ip:port:last_seen）+ 6s TTL 判离线 +
  `mac>win>atv` 优先级自动切换 + 状态原子落盘（30s 节流）+ ACK 应答。
- `presence_beat.py`（客户端库）: 启动即拍 / ACK 复位 / 无 ACK 退避 2→4→8→15s / 可停可启。
- 测试：离线注入时钟 **62 PASS** + 真实 socket 冒烟全过。目标 = 去硬编码 IP、按在线状态自动选目标。

### 3. ★ 遥控器鼠标模式 —— 三端实现全链交付（用户需求「方向键模拟鼠标」）
- **背景**：用户提出「Tab 切窗口/焦点太麻烦——按一个键模拟鼠标，上下左右移动 + OK 点击」。
- **键位设计**：**长按 #41 直播键 开/关模式**；模式内 **方向=滑行移光标 / OK 短=左键·长=右键 /
  音量±=滚动 / 返回=退出**（其余键忽略）。滑行引擎参数两端逐条对齐：加速 700px/s² /
  上限 1600px/s / 1.2s 无刷新看门狗自停（保活断流即刹车）/ 斜向 √2 速不归一化。
- **T1 `voice_fwd` v2.5**：模式层状态机（本地消化 MOUSE:TOGGLE/OFF，不转发）；方向/音量
  按住 0.4s 保活补发；DOWN 时目标快照、UP 回原目标（配对纪律）。keymap 两份 #41
  long=`MOUSE:TOGGLE`（mac/win 对齐，atv 不变）。
- **Mac `key_bridge` v1.13**：MOUSE:* 分支 → 串行 worker → Hammerspoon
  `remotehub_focus.lua` v1.2 鼠标执行器（状态挂 _G 单例跨 hs 调用存活）。
- **Win `win_receiver` v1.7 + `win_actions` v1.11**：MOUSE:* 专用路由（DOWN+UP 双向 hold
  语义，不走扩展 down-only 管道）+ MouseGlide 滑行积分器（纯逻辑可测）+ SendInput
  当前位置点击/滚轮（WHEEL_DELTA=120）。**代码+离线测试全部完成，待 Windows 上线部署**。
- **T1 `t1_webui` v2.13**：`MOUSE:TOGGLE` 白名单放行 + 下拉选项。
- **测试**：key_fwd 45→**79**（+34 鼠标模式断言）/ actions 329→**367**（+38 滑行引擎）/
  webui_v2 89 / **Mac 端到端 8 PASS**（真实光标右移 126px、松开即停、看门狗自停、点击/滚动实测）。
- **部署**：T1（voice_fwd v2.5 + webui v2.13 + keymap）与 Mac（key_bridge v1.13）已于 13:18 上线；
  Windows 于 13:29 经 RUN 通道「零到场」远程升级（v1.7 + v1.11）。→ 用户随即实测（见 §4）。

### 4. ★ 用户首测五问 —— 实测修复轮（下午，全链闭环）

**背景**：Windows 上线后用户立即实测，报回五个问题；当日全部定位、修复、实机验证。

**问题 → 根因 → 修复**：

1. **「模式切换没有任何提示，按了不知道生效没有」**（核心体验）→ T1 v2.5 只在本地消化开关，
   目标端收不到任何信号。修：`voice_fwd v2.6` 新增 `send_mode_hint` —— 开关模式 / 模式内
   单按 #41 时向目标发 `MOUSE:MODE:ON|OFF`。接收端双 HUD：**Mac**（lua v1.3 `mouseHud`：
   hs.alert 大浮层 1.1s + Glass/Pop 声音）/ **Win**（win_actions v1.12 复用 picker Tk 线程弹
   「鼠标模式/键盘模式」浮层 + MessageBeep；Tk 不可用静默降级）。
2. **「Mac TV 键单按无法聚焦了」** → 实为模式内单按 #41 被设计性吸收且零提示（用户以为键坏了）。
   修：同 ①——单按现在弹「🖱 鼠标模式」，提醒「模式仍开着」。
3. **「模式内按开机键没反应，没法跳走打开应用」** → `MouseMode.handle()` 对非映射键静默忽略。
   修：`MOUSE_PASSTHROUGH_CODES = {116, 102}` 放行至正常键路径（电源：短 APP:workbuddy /
   长 APP:CLOSE；主页：短 APP:CYCLE / 长 APP:PICK），长按语义与模式外一致。
4. **「Windows 鼠标特别快，无法小距离移动」** → 遥控器方向键是离散「按下→松开」流；win 侧
   `MouseGlide` 唯一速度清零点在 `step()`，up 间隙内 60Hz worker 因 `busy()=False` 提前
   continue → 速度跨按压累积（按住 1s ≈ 1050px/s，几次顶满 1600）。修：`stop()/_sweep()`
   事件驱动清零（对齐 Mac lua `stopTimer` 语义）；§19a 离散按压流对照（11.67 vs 旧 23.33）。
5. **★「Windows OK 键完全没反应（短、长按都不行）」** → **元凶级：跨模块 SendInput 类型冲突**。
   `ctypes.windll.user32` 是**进程级共享对象**；`win_receiver` 与 `win_actions` **各自定义
   INPUT 结构类**并各自设置 `SendInput.argtypes`（后加载的 receiver 覆盖）→ win_actions 侧
   全部 SendInput 调用（鼠标点击 / 滚轮 / Alt tap）以跨类指针被 ctypes 拒绝，抛
   `TypeError: expected LP_INPUT instance instead of pointer to INPUT` 被 `except: return
   False` 吞掉 → **静默全灭**。键盘（receiver 自己的类，与 argtypes 同型）正常 —— 即
   「鼠标能滑行（SetCursorPos 不走 SendInput）、键盘可用，唯独点击毫无反应」之谜。
   **取证**：v1.12 内置 `MOUSE:REPORT` 探针（零位移 MOUSEEVENTF_MOVE，无害）经 RUN 通道
   回传 `state/mouse-report.json` **一击命中**（`"EXC argument 2: TypeError..."`）。
   **修复**（win_actions v1.13 + win_receiver v1.9）：结构定义上移通用层 + win_receiver
   **复用同一类对象**（全进程单类）；4 处静默 `except` 补 `_logv` 落盘（教训固化：同类问题
   今后直达 receiver.log）；REPORT 增 `input_class_module` 指纹。
   **实机验证：探针 `EXC` → `ok(1)`**（同一零位移探针，修复前后对照）。
   **连带纠正**：`force_foreground` 注释「实测 Alt 敲击无效」实为同 bug——Alt tap 从未成功
   执行过；修复后恢复可用（前台锁定多一条解锁手段）。

**验证与部署（全部实机）**：
- Windows 经 RUN 通道共三轮升级（v1.7+v1.11 初装 → v1.8+v1.12 修复轮① → v1.9+v1.13 元凶修复）；
  每轮 [2/7] 升级前取证 + [7/7] 升级后取证自动回传 T1（证据存 `windows/forensics-2026-10-13/`）。
- v1.13 报告实机两证：`sendinput_probe: "ok(1)"` + `input_class_module: "win_actions"`；
  Windows HUD 实机：`mode hud on/off (tk)` + `tk_thread: alive`。
- Mac 全链冒烟（自 T1 发字节级仿真报文）：`-> [mouse] MOUSE:MODE:ON DOWN OK | OK hud on`。
- 测试：key_fwd 79→**104**（+25 v2.6 断言）/ actions 367→**425**（+§20 类统一运行时断言
  `win_receiver.INPUT is win_actions.INPUT` 等 27 条）/ receiver 22 —— 全绿。
- 部署：T1 voice_fwd **v2.6**（14:25:33 重启，banner 确认）/ Mac key_bridge **v1.14** +
  lua **v1.3**（14:25:17）/ Windows **v1.9 + v1.13**（14:23:30，指纹核对）。
  → **用户复测通过（15:1x）：Windows 鼠标速度正常 / OK 长按右键 / 主页 / 返回全部 OK。**

### 5. ★ 电源键连击切换设备（用户需求「1 击 ATV / 2 击 Mac / 3 击 Windows」；15:1x 立项）

- **背景**：五问复测通过后用户提新需求——「每次在几个设备之间切换用网页还是有些麻烦」→ 电源键连击直切。
  用户拍板：电源键短按原绑定「打开 WorkBuddy」**不再保留**（长按=关闭当前应用不变）。
- **键位**：**1 击=ATV / 2 击=macOS / 3 击=Windows**（立即切换 + 目标端提示浮层）。
  网关式启用 = keymap `#116.single == "TARGET:SWITCH"`（改回任意动作即退回普通键语义，零代码改动）；
  两份 keymap（现网/default）已写入注记。
- **T1 `voice_fwd` v2.7 + `relay_min` v0.11**：**双侧各挂连击计数器**（voice_fwd 管 mac/win 态、
  relay 管 atv 态——ATV 状态也能切走）；窗 0.5s / 第 3 击立即提交 / 长按 ≥0.6s 中止计数走
  `APP:CLOSE` 不误发 / 提交后 0.5s 吞键期（防手抖）；atv 侧 1 击=电视电源（原行为）、无长按语义；
  切到 atv 强制退出鼠标模式 + HUD 发「旧目标端」（mac/win 必见提示）。
- **Mac `key_bridge` v1.15 + lua v1.4**：`TARGET:SWITCH:*`（仅 DOWN）→ `switchHud()`「🎯 已切到 X」
  浮层（复用鼠标串行 worker；lua 副本已部署实证 `OK hud switch:win`）；
  **Win `win_receiver` v1.10 + `win_actions` v1.14**：同 MOUSE:* 路由 + Tk 浮层
  （`_hud_open_text` 抽取共用模式 HUD 体系）。
- **T1 `t1_webui` v2.14**：三 tab 下拉新增「★ 电源（连击切设备）」项（atv 份+mac/win 份）。
- **测试**：key_fwd 104→**149**（+45 连击断言）/ relay_logic 14→**29**（+15，atv 侧）/
  webui_v2 89→**100**（+11）/ actions 425→**448**（+§21 23 条）/ mouse_channel **24 PASS**
  （含 v1.15 映射 + lua `switchHud` 实机段）——全绿。
- **部署**：Mac 15:26 上线（key_bridge v1.15 重启 + lua v1.4 拷贝）；T1 / Windows 部署完成
  （15:40-15:42 升级取证 + 烟测）→ **15:4x 用户复测通过：「可以切换了」。**

### 6. ★ ATV 语音键解锁（用户反馈「ATV 配置页语音键不可设、描述不对」；16:1x 立项）

- **背景**：用户复测电源连击通过后反馈——atv 配置页 #63 语音键显示为「锁定」不可编辑，
  且 note 把它描述成「语音链专用」；实际上语音键在 ATV 上应可自由设置
  （10-09「语音键=开 YouTube」是**需求默认值**，锁死不必要）。
- **T1 `relay_min` v0.12**：语音键 63 由硬编码 YouTube 改为**配置驱动**——删除特判分支，
  走通用 keymap 分派（默认 `single=__LAUNCH__:com.google.ios.youtube` 保持原行为一键开
  YouTube；网页改绑任意 ATV 动作即生效；清空=关闭该键）；target≠atv 仍忽略（交 voice_fwd
  转发语音输入）。内置兜底补 63 条目。
- **T1 `t1_webui` v2.15**：atv 份 #63 去 locked + single 默认置 `__LAUNCH__:com.google.ios.youtube`
  + note 重写（「默认『打开 YouTube』；可自由改绑其它 ATV 动作。Mac·Windows 目标下语音键
  仍为按住说话（语音输入），不受此处影响」）；mac/win 份 #63 保持锁定（按住说话, 语音链专用）。
- **测试**：relay_logic 29→**31**（+2：改绑跟随 / 清空无动作）/ webui_v2 100→**101**
  （+1 净增：atv 63 解锁可改 + mac 63 锁定保护）——本地与 T1 现场全绿。
- **部署**：T1 16:25 上线（relay v0.12 + webui v2.15 重启；keymap.json / default 三配置同步）。

---

### 7. ★ FOCUS_INPUT 聚焦不灵修复（用户反馈「无论 Mac/Win，鼠标模式下按焦点聚焦键不灵、不好使，键盘模式也不好用」；10-14 凌晨立项）

- **双根因**（证据链）：
  ① **鼠标模式内 #41 被 T1 主动吸收**（v2.6 设计——弹「模式仍开着」提示代替执行）→ 用户视角
     =「按了没反应」；T1 日志实证 15:54-15:59 用户连按 #41 五次全被吞、只剩提示；
  ② **微信类「无 AX（Mac）/无 UIA 内容层（Win）」应用聚焦不了**——两端五段策略（缓存/网格/树）
     对其全空转；Mac key_bridge 日志 9 条 `NOEDIT 微信 win=850x917`（用户实测场景）；
     Mac WorkBuddy 13:41 也三连败（缓存点场景性失效）。
- **修复三件**：
  - **T1 `voice_fwd` v2.8**：鼠标模式内短按 #41 **放行**（FOCUS_INPUT 直发实时目标，与键盘模式
    行为完全一致）；长按仍 = MOUSE:TOGGLE 关模式；修正旧版「模式内固定 mac 键表」为实时 target。
  - **Mac `remotehub_focus.lua` v1.5**：五段全败时 **NOEDIT 兜底「底部中央点击」(0.5, 0.92)**
    （聊天/评论类输入区几何假设），点击后恢复鼠标位置；返回 `NOEDIT+CLICK@x,y`。
  - **Win `win_actions` v1.15**：同款兜底点击（`_click_preserve_cursor` 保光标位置；策略函数加
    `click_at` 注入参数——既有 NOEDIT 断言向后兼容、测试可打桩）；结果串追加 `app=<exe_key>`
    可观测性字段（排障直达）。
- **★ 深挖轮（10-14 03:3x–04:0x，承用户复查「还是不行」）——三号根因「窗口遮挡」+ 坐标修正**：
  - **发现**（证据链全通但用户仍不灵 → 现场诊断）：T1 转发 ✓ / Mac 执行 ✓ / `NOEDIT+CLICK`
    已发出 ✓，但 hit-test 扫描 + 全屏截图 + Quartz z 序揭示实况——**WorkBuddy 的 AX 树仅 9
    节点（输入框不暴露, 属 Chromium 惰性树）**；且 **z 序 = 抖音直播窗压在 WorkBuddy 之上**
    （activate 提升可解; 用户多窗口工作环境常态）→ 合成点击与键盘事件全被顶层窗口截胡；
    v1.5 的 0.92 比例坐标实测落在输入框下方按钮行（0.87 才是文字行）。
  - **Mac `remotehub_focus.lua` v1.5 → v1.6**：① 新增 `ensureFrontApp()`——`app:activate()`
    + z 序校验（≤3 次 ×150ms, 在 unmin 修复之后），确保目标窗口真在最顶（否则点击落空 /
    键盘进不去）；提升失败时跳过点击（防误点遮挡弹窗按钮）；② 兜底坐标 `0.92 比例` →
    **距窗底固定 105px**（WorkBuddy 输入框文字行实测值; 固定像素距底对窗口高度变化更稳）；
    返回串加 `front=ok|fail` 诊断字段。**实证**：`activate + click(956,767)` → 注入字符
    落入输入框 ✓（03:3x 双盲验证：字符 x 出现→删除）。
  - **Win 侧待定**：`fix_foreground_window`（unmin + force_foreground）已有等价前台提升
    机制——待用户复测反馈后再定是否需对称调整兜底坐标。
- **测试**：key_fwd 149→**154**（16e 模式内 #41 放行 5 断言）；actions 448→**459**
  （F2/F3/F4 兜底点击行为 + 22 区源码约定守护）——本地与 T1 现场全绿。
- **部署**：T1 voice_fwd v2.8（03:14 重启，banner + event2 挂载确认）/ Mac lua v1.5
  （03:15 拷贝，sha256 一致 + 加载验证）→ **v1.6（03:4x 追加：sha256 `737b7cf4…` 双端一致 +
  双副本加载验证）** / Windows win_actions v1.15（03:16 升级，post 指纹 sha256
  逐字节一致；03:18 现场实测日志 `NOEDIT+CLICK@1920,1987 ... [winfix=raise app=lockapp.exe]`
  ——兜底点击与 app 字段双验证；实测时机器锁屏，属环境如实）。
- **复测指引（用户）**：① 键盘模式按 #41（Mac 微信/WorkBuddy）→ 目标应用被提到最前 + 光标
  进输入框；② 鼠标模式内短按 #41 → 同款；长按 #41 仍开/关模式；③ Win 侧同款试一次。

---

## 2026-10-14（D7）：presence 心跳注册制全链接线（去硬编码 IP · 体面断开/优雅连上）· 控制台设备状态条

> 承接 D6 §2「核心模块完成（接线中）」——本日完成三端全部接线与部署，并新增控制台可视化。
> （10-14 凌晨的 FOCUS_INPUT 深挖轮见 D6 §7。）

### 1. ★ presence 心跳注册制 —— 三端接线完成（T1 → Mac → Win）

- **动机复述**（D6 §2）：一套机制吃两个需求——① **体面断开/优雅连上**（设备离网 = 暂停投递
  + 明确日志，消灭「假已发送」；回网自动续）② **投递地址去硬编码**（心跳学习 IP，DHCP
  变更自动跟上；静态常量降级为 fallback）。
- **T1 侧三服务接线**（投递闸门 = 离线跳过 + 心跳 IP 优先 + 边沿日志）：
  - `voice_fwd` v2.8→**v2.9**：新增 `_send_to()` 闸门（离线跳过 / `ip_of()` 优先 /
    无地址 60s 节流丢弃）；`MAC_IP`/`WIN_IP` 降级为 fallback（注释标注）；
  - `atvv_service` v1.1→**v1.2**：`DESTS` 静态表 → `_dests()` 动态解析（按 role 逐路判）；
  - `relay_min` v0.12→**v0.13**：`_send_target_hint()` 地址动态化 + ATV 心跳上报
    （`presence_beat.start("atv", [("relay", 0)])`）；
  - **`t1-presence.service` 新建并部署**（UDP:8790 守护，systemd enabled 自启，
    日志 `/var/log.hdd/presence.log`；T1 自启服务 7→8）。
- **Mac 侧**：**`presence_beater` v2.1 新建**（`bash + /usr/bin/nc` 形态，LaunchAgent 常驻）——
  每 2s 一轮三 svc 并发心跳（`voice:8788 / key:8791 / audio:8789`）+ 每 60s ACK 深探。
- **Win 侧**：`win_receiver` v1.10→**v1.11**（`presence_beat.start("win", [voice/key/audio])`
  单代理；`presence_beat.py` 随 `update-win-receiver.ps1` 配套分发）——经 RUN 通道
  「零到场」升级（04:42 触发，ps1 全流程 + pre/post 指纹回传核对逐字节一致）。
- **架构要点**：**单代理形态**（每设备一个心跳源代报全部 svc——Mac beater / Win receiver /
  T1 relay）；设备级闸门粒度（svc 明细为观测字段）；`presence.json` **30s 写盘快照**
  （读端 90s 过期 → unknown 降级 = 维持旧行为照旧投递，永不阻塞）。
- **全链验收**：三设备 online 齐活（mac=.19 / win=.18 / atv=.16 均心跳学习 IP）；
  04:42 起零离线事件；自动切换链路此前已实证（mac 离线 → 切 atv → 恢复自动切回）。

### 2. ★★ macOS 27 本地网络隐私 —— launchd 上下文解释器出站被拦（本日最大发现）

- **症状**：presence 心跳在 Mac 发不出——`OSError(65, 'No route to host')` / UDP 静默丢，
  而 `route get` / `ping` 全正常（错误信息指向错误的层，排查三次误判后才锁定）。
- **实测判决**（决定性证据）：launchd 上下文（LaunchAgent + `launchctl submit`）中
  **所有解释器出站被拦**（workbuddy python〔ad-hoc 签名〕与系统 `/usr/bin/python3` 全灭，
  UDP/TCP 全试）；而 **系统网络工具 `/usr/bin/nc`、`/usr/bin/curl` 放行**（nc UDP 双向
  含 ACK 回程实测通；curl HTTP 200）。依据 Apple **TN3179**（Local Network Privacy：
  系统签名二进制获自动放行；外部同类案例 Grafana Alloy / ESPHome 佐证）。
- **对策**：beater 改「bash 循环 + `/usr/bin/nc`」形态（v1.0 python → v2.0 首版 →
  **v2.1** 发送后台并发 + 2s 节拍 + 60s ACK 深探）——协议与 T1 侧**零改动**。
- **副产教训**：macOS `nc` 的 `-w` **只接受整数**（小数 = 参数错误 exit 1 且静默不发包，
  「秒退」伪装成发送成功——曾据此误判）；UDP 发送正确姿势 = 后台扇出 + 主循环固定节拍。

### 3. 控制台设备状态条（t1_webui v2.15→v2.16）

- 主页新增「设备在线状态」条：ATV / macOS / Windows 三状态点（绿=在线 / 灰=离线+最后
  在线秒数 / 黄=未知），3s 轮询 `GET /api/presence`（只读 `state/presence.json`）。
- 降级安全：presence 未运行 / 快照缺失 / 过期 → `available=false` 前端显示「未知」，
  不阻塞页面其余功能（页面其余行为零改动）。

### 4. 测试与部署

- 测试：key_fwd 154→**165**（+11：v2.9 闸门——离线跳过/恢复/漂移 IP/降级照旧/无地址丢弃）；
  webui_v2 101→**111**（+10：/api/presence 组装 + 缺失/过期降级 + 主页元素）；
  presence 62 / relay 31 / mouse_channel 24 / actions 459 —— 全绿（本地 + T1 现场）。
- 部署：T1 五件（voice_fwd v2.9 / atvv v1.2 / relay v0.13 / t1_webui v2.16 +
  t1-presence.service）双端 sha256 全等；Mac beater v2.1 + LaunchAgent（plist 指向 bash）；
  Win v1.11 经 RUN 通道升级（第 5 次「零到场」实践全成，8000 日志 + inbox 回传双证）。
- 用户可感知：网页台主页看三设备状态点（拔网/关机设备约 6s 转灰；恢复自动转绿）。


---

## 附录 A · 版本速查表（初版 → 现网）

| 端 | 件 | 版本路径 | 现网 |
|---|---|---|---|
| T1 | voice_fwd | v1.0 → v2.0 → v2.1（自建连发）→ v2.3（长按）→ v2.4（文案同步）→ v2.5（鼠标模式）→ v2.6（模式提示 HUD + 放行键）→ v2.7（电源连击切换）→ v2.8（模式内 #41 放行）→ v2.9（presence 心跳闸门） | **v2.9** |
| T1 | relay_min | v0.2 → v0.3 → v0.4 → v0.5 → v0.6 → v0.7 → v0.8 → v0.9（配置外置）→ v0.10 → v0.11（电源连击 atv 侧）→ v0.12（语音键配置驱动）→ v0.13（presence 闸门 + atv 心跳） | **v0.13** |
| T1 | t1_webui | v1 → v2.0 → v2.1（应用动作）→ … → v2.11（长按关闭）→ v2.12（文案同步）→ v2.13（鼠标模式）→ v2.14（电源连击选项）→ v2.15（语音键解锁）→ v2.16（设备状态条） | **v2.16** |
| T1 | atvv_service | v1.0 → v1.1（双播）→ v1.2（presence 闸门） | **v1.2** |
| T1 | presence | v0.1 → v1.0（心跳注册制守护，10-13 新增；10-14 全链接线） | **v1.0** |
| Mac | key_bridge | v1.0 → … → v1.11（URL/RUN）→ v1.12（关闭）→ v1.13（鼠标模式）→ v1.14（模式 HUD 后端）→ v1.15（设备切换 HUD） | **v1.15** |
| Mac | voice_bridge | v0.2 → … → v0.7 → v0.9 | **v0.9** |
| Mac | atvv_receiver | v1.0 → v1.1 → v1.2（AGC 24） | **v1.2** |
| Mac | app_switch | v1.0 → v1.1（前台修复）→ v1.2（close） | **v1.2** |
| Mac | AppPicker | v1.0 → v1.1 → v1.2（网格）→ v1.3（长名） | **v1.3** |
| Mac | hs_health | v1.0 | **v1.0** |
| Mac | remotehub_focus.lua | v1.0 → v1.1（clickFocused）→ v1.2（鼠标执行器）→ v1.3（模式 HUD）→ v1.4（设备切换浮层）→ v1.5（NOEDIT 兜底点击）→ v1.6（前台提升 + 距底 105px 坐标） | **v1.6** |
| Mac | presence_beater | v1.0（python 参考版）→ v2.0 → v2.1（bash + nc 形态；macOS 27 本地网络隐私对策） | **v2.1** |
| Win | win_receiver | v1.0 → … → v1.6 → v1.7（鼠标模式）→ v1.8（HUD/取证配套）→ v1.9（★ SendInput 类统一修复）→ v1.10（设备切换路由）→ v1.11（presence 心跳） | **v1.11** |
| Win | win_actions | v1.0 → … → v1.10 → v1.11（滑行引擎）→ v1.12（速度清零/ HUD / 取证）→ v1.13（★ SendInput 类统一修复）→ v1.14（设备切换 HUD）→ v1.15（FOCUS_INPUT 兜底点击 + app 观测字段） | **v1.15** |
| Win | win_audio_switch | v1.0 → v1.1 → v1.2 | **v1.2** |
| Win | win_audio_receiver | v1.0 | **v1.0** |
| 系统 | btflow | scene23（终版） | **scene23** |
| 系统 | 内核补丁 | `0001-…drop-the-link-before-power-.patch`（EXP-19 验收） | **已装** |

> （presence 心跳注册制已于 10-14 全链接线完成；本表 10-14 复核。）

## 附录 B · 测试资产演进

| 日期 | 里程碑 |
|---|---|
| 10-09 | relay_logic(14) / key_fwd_logic(45) 建立 |
| 10-10 | webui_v2(84→89) / webui_js(39→42) / apppicker_grid(33) / apppicker_name(16) / close_app(18) / 四套 488 |
| 10-11 | Windows 五套（offline 22 / audio 26 / actions 329 / audio_switch 74 / smoke 28）→ 合计 736 |
| 10-12 | actions 329 含源码约定守护；双解释器 3.9+3.13 全绿 |
| 10-13 | presence(62) 新增；key_fwd 45→79→104→**149**（鼠标模式 + v2.6 修复轮 + v2.7 连击）；relay 14→29→**31**（v0.11 atv 侧连击 + v0.12 语音键配置驱动）；actions 329→367→425→**448**（滑行引擎 + v1.13 类统一 + v1.14 设备切换）；webui_v2 89→100→**101**（v2.14 连击选项 + v2.15 语音键解锁）；Mac 鼠标端到端 **24 PASS**（含 switchHud 实机段） |
| 10-14 | key_fwd 149→**165**（v2.8 模式内 #41 放行 + v2.9 presence 闸门）；actions 448→**459**（v1.15 兜底点击 + 源码约定守护）；webui_v2 101→**111**（v2.16 设备状态条）；presence 62 接线回归全绿——本地与 T1 现场全绿 |
