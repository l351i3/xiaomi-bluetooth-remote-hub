# CHANGELOG —— 项目全史（2026-10-07 ～ 2026-10-12）

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

## 附录 A · 版本速查表（初版 → 现网）

| 端 | 件 | 版本路径 | 现网 |
|---|---|---|---|
| T1 | voice_fwd | v1.0 → v2.0 → v2.1（自建连发）→ v2.3（长按）→ v2.4（文案同步） | **v2.4** |
| T1 | relay_min | v0.2 → v0.3 → v0.4 → v0.5 → v0.6 → v0.7 → v0.8 → v0.9（配置外置）→ v0.10 | **v0.10** |
| T1 | t1_webui | v1 → v2.0 → v2.1（应用动作）→ … → v2.11（长按关闭）→ v2.12（文案同步） | **v2.12** |
| T1 | atvv_service | v1.0 → v1.1（双播） | **v1.1** |
| Mac | key_bridge | v1.0 → … → v1.10（翻页）→ v1.11（URL/RUN）→ v1.12（关闭） | **v1.12** |
| Mac | voice_bridge | v0.2 → … → v0.7 → v0.9 | **v0.9** |
| Mac | atvv_receiver | v1.0 → v1.1 → v1.2（AGC 24） | **v1.2** |
| Mac | app_switch | v1.0 → v1.1（前台修复）→ v1.2（close） | **v1.2** |
| Mac | AppPicker | v1.0 → v1.1 → v1.2（网格）→ v1.3（长名） | **v1.3** |
| Mac | hs_health | v1.0 | **v1.0** |
| Win | win_receiver | v1.0 → v1.1 → v1.2 → v1.3 → v1.4 → v1.5 → v1.6 | **v1.6** |
| Win | win_actions | v1.0 → … → v1.7 → v1.8 → v1.9 → v1.10 | **v1.10** |
| Win | win_audio_switch | v1.0 → v1.1 → v1.2 | **v1.2** |
| Win | win_audio_receiver | v1.0 | **v1.0** |
| 系统 | btflow | scene23（终版） | **scene23** |
| 系统 | 内核补丁 | `0001-…drop-the-link-before-power-.patch`（EXP-19 验收） | **已装** |

## 附录 B · 测试资产演进

| 日期 | 里程碑 |
|---|---|
| 10-09 | relay_logic(14) / key_fwd_logic(45) 建立 |
| 10-10 | webui_v2(84→89) / webui_js(39→42) / apppicker_grid(33) / apppicker_name(16) / close_app(18) / 四套 488 |
| 10-11 | Windows 五套（offline 22 / audio 26 / actions 329 / audio_switch 74 / smoke 28）→ 合计 736 |
| 10-12 | actions 329 含源码约定守护；双解释器 3.9+3.13 全绿 |
