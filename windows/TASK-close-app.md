# TASK-close-app.md — win_actions v1.10 施工单（长按电源键「关闭当前应用」+ v1.8/v1.9 累积外观修复）

> **状态：✅ 已上线并实测通过**（2026-10-12 14:17:53 用户侧自助拉取；14:22 用户实测：
> 「Mac和Windows都测试了，基本没发现什么问题」）。本单转为**留档**：§1 施工 / §2 验收 / §3 回滚。

> **目标**：Windows 接收端 `win_actions.py` 升级到 **v1.10**。自 v1.7 起累积交付：
> - **v1.8** 选择器配色对齐 Mac AppPicker（浅灰磨砂 + 系统蓝 + 近黑文字）；
> - **v1.9** 选中格图标透明融合（双底色变体——修复「图标外围一圈灰底」）；
> - **v1.10** ★ 本轮主体：**长按电源键关闭当前前台应用**（Mac 同日已上线，双端对等）。
>
> `win_receiver.py` v1.6 / `win_audio_switch.py` v1.2 **不变**，无需动。
> 全程本机操作，无网络外发（仅按现有分发链从 T1:8000 拉文件）。
> 执行方：Windows 侧 WorkBuddy。

---

## §0 30 秒读懂（v1.10 怎么工作）

- **功能**：遥控器**长按电源键（#116）≥0.6s** → 关闭**当前前台应用**。
  生产绑定 = keymap v2 `#116.long = "APP:CLOSE"`（T1 已下发；单击仍为「打开 workbuddy」，
  长按由 voice_fwd v2.3 状态机独立触发、与单击严格互斥——**不会双击误触**）。
- **语义 = 优雅关闭**：对前台顶层窗口发 `WM_CLOSE`（`SendMessageTimeoutW`,
  `SMTO_ABORTIFHUNG`, 1.5s）——应用走自身退出流程；**未保存内容会弹保存确认（不丢数据）**；
  **不用 TerminateProcess**。
- **UWP 应用**（计算器/设置等，窗口宿主 = ApplicationFrameHost）：先取**真身子窗口**再发。
- **系统 shell 窗口**（桌面/任务栏）拒绝关闭（对齐 Mac 端 Finder 保护）。
- **成功判定**：窗口销毁 或 前台已切换（轮询 ≤2s）；超时 = `pending`（可能弹保存确认）。
- **防抖 2.0s**（APP:CLOSE 专属）：关闭后前台必变——防重复包连关第二个应用。
- **多窗口应用**（如 Chrome 多窗口）只关前台该窗口（连续长按可依次关）——有意取舍，
  不误关同一应用的其余窗口（与 Mac 整应用退出的差异说明见上游 changelog）。
- ⚠️ **GUID 修复已在 <u>上游</u>**（v1.9 起含 `bcc18b79…` 正确 IID + 你的 20261012-username
  标记；测试断言同步更正）——**本包全量覆盖不会再丢**。

---

## §1 施工

### 1A. 推荐路径（双击 `update-win-receiver.bat`）

双击即自动：定位目录 → 下载 3 件 → 备份 → 替换 → 清缓存 → 重启计划任务 → PING 自检 + selftest。

### 1B. 手工等效（若 `irm|iex` 被策略拦截）

1. **下载**（浏览器或 PowerShell `Invoke-WebRequest`）：
   - `http://T1_IP:8000/win_actions.py` → **v1.10** `sha256 = ba5857f6aff1adcd905e2167a045823b7a193eb0fbdf9129af1577573f86fa4d`（115402 B）
   - `http://T1_IP:8000/actions_offline_test.py` → `a4a1cf380a9cf3d51ea0f1eda68eb0951a37ce574164a7fe85f6e13b1d653fd5`（42468 B，329 PASS 版）
   - `win_receiver.py` v1.6 / `win_audio_switch.py` v1.2 **无需重新下载**（未变）。
2. **逐行审查**（对照本单 §0；文件头 changelog v1.10 段）。
3. **哈希核对**（`Get-FileHash -Algorithm SHA256`）。
4. **备份**：`win_actions.py.bak-<TS>`。
5. **停旧**（计划任务 `remotehub-win-receiver` 或结束 `pythonw.exe`）→ **替换** →
   清 `__pycache__` → **重启计划任务**。
6. **自检**：`python win_receiver.py --selftest`（`win_actions v1.10`）。
7. **离线回归**：`python actions_offline_test.py` → 期望 **329 PASS / 0 FAIL**。

---

## §2 验收单（用户操作，遥控器实机）

| # | 操作 | 期望 | 日志行（receiver.log） |
|---|---|---|---|
| 2a | 打开一个应用（记事本/计算器/浏览器）→ **长按电源键 ≥0.6s** | 该应用关闭 | `EXT APP:CLOSE -> close[…] -> … ok (…)` |
| 2b | **单击**电源键（<0.6s） | 只打开/激活 workbuddy，**不关任何东西** | `KEY APP:workbuddy queued (ext)`（无 CLOSE 行） |
| 2c | 连续快速长按两次（间隔 <2s） | 只关一个应用（第二次被防抖） | `KEY APP:CLOSE debounced (2.00s window)` |
| 2d | 前台=桌面（无应用窗口）时长按 | 无动作/无副作用 | `close: 拒绝关闭系统窗口（Progman）` |
| 2e | 应用有未保存内容（记事本敲字不保存）→ 长按 | 弹「保存确认」对话框（**数据不丢**） | `close[…] pending: …（可能弹保存确认…）` |
| 2f | **回归**：长按主页 → 选择器 | 浅灰配色（v1.8）+ 选中格图标**无灰圈**（v1.9） | 无异常 |
| 2g | **回归**：单击电源键 | workbuddy 正常打开（既有行为不回归） | `KEY APP:workbuddy …` |

> 验收通过后回传：`report-v1.10.md`（模板随惯例）+ 如有 `win_actions.py.patched` 一并回传 `T1:8001`。

---

## §3 回滚

停接收端 → 恢复 `win_actions.py.bak-<TS>` → 计划任务重启。（键位无需回滚：`APP:CLOSE`
在旧版会被当普通应用名处理成「not-running」，不会误关任何东西——但建议同步回滚验收。）

## §4 附：同步信息

- Mac 侧对等实现：`app_switch` v1.2 `close`（NSRunningApplication.terminate 优雅退出，
  Finder 保护）+ `key_bridge` v1.12（路由 + CLOSE_DEBOUNCE=2.0）；已于 10-12 14:0x
  生产路径实测（TextEdit 关闭 ✅）。
- T1 侧：keymap v2 三份（现网/default/本地）均已含 `#116.long=APP:CLOSE`（sha256
  `33da9a4b…`）；网页台 v2.11（下拉含「★ 关闭当前应用（长按电源键）」）。
- 上游三件测试基线：actions **329** / receiver **28** / webui **89** / JS **42**。
