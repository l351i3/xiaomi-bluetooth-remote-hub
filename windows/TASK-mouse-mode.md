# TASK-mouse-mode.md — win_receiver v1.7 + win_actions v1.11 施工单（鼠标模式：遥控器 dpad 模拟鼠标）

> **状态：✅ 已上线 + 首测修复轮完成（三版接力：v1.7+v1.11 首次远程升级 13:29 → v1.8+v1.12
> 修复轮① 14:08 → v1.9+v1.13 元凶修复 14:23；全部经 RUN 通道「零到场」执行，升前/升后取证
> 自动回传 `forensics-2026-10-13/`；v1.13 探针实机 `EXC → ok(1)`、HUD `(tk)` 实证）
> → 待 §2 遥控器实测复验收（五问逐项；修复详情见 §6）。**
> 执行方：Windows 侧 WorkBuddy（人工兜底路径见 §1B）。若有偏差，以「不改端口/协议 + 用户会话运行」两条硬约束自行适配并注明。

> **目标**：Windows 接收端升级到 **win_receiver v1.7 + win_actions v1.11**。
> 本轮主体 —— ★ **鼠标模式**（用户需求：遥控器 dpad 直接推光标，替代 Tab/焦点切换的繁琐操作）：
> - **长按直播键（#41）≥0.6s** 开/关鼠标模式（T1 本地消化，不占按键通道）；
> - **模式内**：方向键 = 光标滑行（按住渐加速）· **OK 短按 = 左键 / 长按 = 右键** ·
>   音量 ± = 滚动 · **返回键 = 退出** · 其余键忽略；
> - 双子机制保安全：T1 每 **0.4s** 保活重发 DOWN；接收端 **1.2s** 无刷新自动刹车+移除方向（防丢包卡死）。
>
> `win_audio_switch.py` v1.2 **不变**，无需动。全程本机操作，无网络外发（仅按现有分发链从 T1:8000 拉文件）。

---

## §0 30 秒读懂（鼠标模式怎么工作）

- **入口**：长按遥控器直播键（#41）≥0.6s → **进入/退出**鼠标模式。进入/退出完全在 T1 上完成
  （voice_fwd v2.5 模式层），**Windows 端不需要也不会有任何"模式"状态**——它只收 `MOUSE:*` 动作流。
- **滑行引擎**（win_actions.MouseGlide，与 Mac lua 版逐条对齐）：
  - 按住方向键 → 光标以 **700 px/s²** 线性加速（**轻点 = 精准微调**：速度从 0 起步）；
  - 速度上限 **1600 px/s**；推进 tick **1/60s**（60Hz 常驻线程，懒启动）；
  - 多方向叠加**不归一化**（斜向 ≈ √2 倍速）；对向相消；贴屏幕边缘自动夹取。
- **OK 键**：短按（<0.6s）松手 = **左键单击**；长按 ≥0.6s = **右键**（长按判定在 T1 完成，只发新动作）；仅 DOWN 触发。
- **音量键**：按住 = 连续滚动（1 notch/60Hz ≈ 10 notch/s；WHEEL_DELTA=120）；松开即停。
- **返回键**：退出鼠标模式（T1 侧消化）；退出后的按键恢复普通键盘行为。
- **看门狗安全带**：按住期间 T1 每 0.4s 重发同一 DOWN（保活）；接收端 1.2s 无刷新 ⇒ 自动移除该方向并刹车。
  —— 即使 UDP 丢失 UP 包或 T1 断线，光标也**不会失控**。重复 DOWN 是幂等保活，**不做防抖**（UP 不可去重）。
- **路由**：`MOUSE:*` 走 **专用前置分支**（handle_mouse → win_actions.mouse_control）——
  MOVE/SCROLL 是 DOWN+UP 双向 hold 语义，**不能**走扩展动作的 down-only 管道。
- ⚠️ **键位无需配置**：T1 侧 keymap 已配好（win tab `#41.long = "MOUSE:TOGGLE"`，网页台已含该项）。
  本单**不涉及任何键位改动**。

---

## §1 施工

### 1A. 推荐路径（双击 `update-win-receiver.bat`）

双击即自动：定位目录 → 下载 3 件 → 备份 → 替换 → 清缓存 → 重启计划任务 → PING 自检 + selftest。
（脚本头/流程文案已更新为 v1.7 + v1.11。）

### 1B. 手工等效（若 `irm|iex` 被策略拦截）

1. **下载**（浏览器或 PowerShell `Invoke-WebRequest`）：
   - `http://T1_IP:8000/win_receiver.py` → **v1.7** `sha256 = 186e059fec2ee4845438937ee9a1bb7f063a372ef65e7f655c5b2f85f58b4503`（22069 B）
   - `http://T1_IP:8000/win_actions.py` → **v1.11** `sha256 = f588e61a15660b533cc9659f7f777cf0d912152ff20c837b7a28c5a4eabf6f02`（125429 B）
   - `http://T1_IP:8000/actions_offline_test.py` → `sha256 = 937102c8ee8e23d39204f29351cf22df5c764e6e2cfbf5cf219f7668b991b1ad`（47783 B，367 PASS 版）
   - `win_audio_switch.py` v1.2 **无需重新下载**（未变）。
2. **逐行审查**（对照本单 §0；两文件头 changelog 的 v1.7 / v1.11 段）。
3. **哈希核对**（`Get-FileHash -Algorithm SHA256`）。
4. **备份**：`win_receiver.py.bak-<TS>` / `win_actions.py.bak-<TS>`。
5. **停旧**（计划任务 `remotehub-win-receiver` 或结束 `pythonw.exe`）→ **替换** →
   清 `__pycache__` → **重启计划任务**。
6. **自检**：`python win_receiver.py --selftest` —— 期望首行 `=== win_receiver v1.7 selftest ===`，
   且含 `win_actions v1.11 selftest`。
7. **离线回归**：
   - `python actions_offline_test.py` → 期望 **367 PASS / 0 FAIL**；
   - `python receiver_smoke_test.py` → 期望 **28 PASS**。

---

## §2 验收单（用户操作，遥控器实机）

> 前置：遥控器目标切到 Windows（长按/T1 网页台均可）。保持接收端运行。

| # | 操作 | 期望 | 日志行（receiver.log） |
|---|---|---|---|
| 2a | **长按直播键（#41）≥0.6s**，然后**按住方向键** | 进入鼠标模式；光标开始滑动（轻点=微移，按住=渐快） | `MOUSE MOUSE:MOVE:<方向> DOWN -> move <方向> on`（保活每 0.4s 重复） |
| 2b | 松开方向键 | 光标**立即停住**，不飘 | `MOUSE MOUSE:MOVE:<方向> UP -> move <方向> off` |
| 2c | **OK 短按**（光标停在某图标/按钮上） | 左键单击（选中/打开） | `MOUSE MOUSE:LCLICK DOWN -> lclick ok` |
| 2d | **OK 长按 ≥0.6s** | 右键单击（弹出右键菜单） | `MOUSE MOUSE:RCLICK DOWN -> rclick ok` |
| 2e | **音量 +** 按住（在长页面上） | 向上连续滚动；松开即停 | `MOUSE MOUSE:SCROLL:UP DOWN -> scroll UP on` → `... UP -> scroll UP off` |
| 2f | **音量 -** 按住 | 向下连续滚动 | `MOUSE MOUSE:SCROLL:DOWN ...` |
| 2g | **返回键（#158）** | **退出**鼠标模式 | （无 MOUSE 行——T1 本地消化） |
| 2h | 退出后按方向键 | 恢复**普通键盘方向键**（焦点在应用内生效） | `KEY UP DOWN -> vk=0x26 ...`（普通键盘行） |
| 2i | 模式内按 菜单/主页 键 | **无动作**（被模式层忽略） | 无对应行 |
| 2j | **再次长按直播键** | 重新进入鼠标模式（开/关循环） | 同 2a |
| 2k | **回归**：单击电源键 / 长按电源键 / 长按主页键 | workbuddy 打开 / 关闭前台应用 / 打开选择器（均不回归） | `KEY APP:workbuddy ...` / `EXT APP:CLOSE ...` / `EXT APP:PICK ...` |
| 2l | **回归**：语音键按住说一句、松开 | 语音输入正常 | `VOICE down/up` |
| 2m | **看门狗**：按住方向后直接**关掉遥控器**（或走远断连） | 光标 ~1.2s 后**自动停**（不失控） | `MOUSE glide stale ...`（自动移除） |

> 2a–2g 为核心交付验收；2k–2l 为既有功能回归（必须全过）；2m 为安全机制验证（建议做）。
> ⚠ **v2.6 修订（10-13 修复轮）**：**2i 已过时**——模式内 **主页（102）/ 电源（116）已放行**，行为与模式外一致
> （短电源=workbuddy / 长电源=关闭应用 / 短主页=轮询 / 长主页=选择器；见 §6-3）；仅 **菜单** 键在模式内暂停。
> 另：模式切换与模式内单按 #41 现在都有 HUD 提示（`MOUSE:MODE:ON|OFF`）。
> 验收通过后回传：`report-mouse-mode.md`（§5 模板）+ 如有 `win_actions.py.patched` / `win_receiver.py.patched` 一并回传。

---

## §3 回滚

停接收端 → 恢复 `win_receiver.py.bak-<TS>` + `win_actions.py.bak-<TS>` → 计划任务重启。
- 键位无需回滚：T1 侧长按 #41 发的 `MOUSE:TOGGLE` 在旧版接收端会被判为 unknown action **静默丢弃**
  （无任何副作用）；方向/OK/音量键在旧版也会走 unknown 分支。
- 若选择「双端同时回滚」：T1 侧把 keymap `#41.long` 改回 `null` 即可（网页台 :8765 一键改）。

---

## §4 附：同步信息

- **T1 侧（已上线）**：`voice_fwd` **v2.5**（MouseMode 状态机 + 0.4s 保活 + OK 长按判定）+ `keymap`
  现网三份 `#41.long = "MOUSE:TOGGLE"`（rev `13a15509efba`）+ 网页台 **v2.13**（下拉含「★ 鼠标模式开/关」）。
- **Mac 侧（已上线）**：`key_bridge` **v1.13**（MOUSE 串行 worker）+ `remotehub_focus.lua` **v1.2**（含
  `_G.REMOTEHUB_MOUSE` 全局单例）。端到端实测 8 PASS（右移 126px / 松开即停 / 看门狗自停 / 滚动 + 左右键实击）。
- **三端参数逐条一致**：`ACCEL=700 px/s²` / `MAX=1600 px/s` / `TICK=1/60` / `STALE=1.2s` / `KEEPALIVE=0.4s`。
- 上游测试基线：actions **367** / receiver smoke **28** / key_fwd **79** / webui **89** / relay **14**。

---

## §5 报告格式（回传 T1 :8001）

```
# RemoteHub Windows 鼠标模式验收报告（v1.7 + v1.11）
- 完成时间：
- 升级方式：1A bat / 1B 手工
- 哈希核对：win_receiver.py ✓/✗  win_actions.py ✓/✗
- selftest：win_receiver v1.7 首行 ✓/✗  win_actions v1.11 ✓/✗
- 离线回归：actions_offline_test 结果（__ PASS / __ FAIL）；receiver_smoke 结果（__ PASS）
- 验收单：2a–2j 逐条结果（✔/✘ + 现象）；2k–2l 回归结果；2m 看门狗结果
- 日志摘录：receiver.log 相关行 10–20 行
- 其它偏差/异常：
```

回传命令（PowerShell）：

```powershell
Invoke-WebRequest -Uri "http://T1_IP:8001/upload/report-mouse-mode.md" -Method POST -InFile <报告路径> -UseBasicParsing
```

---

## §6 首测修复轮（2026-10-13 下午）—— 用户五问 → 全部修复并实机验证

**用户首测五问**（原话：Mac 表现相对正常，Windows 问题更多）：

| # | 问题 | 根因 | 修复 | 实机验证 |
|---|---|---|---|---|
| 1 | Mac **TV 键单按无法聚焦**了 | 模式内单按 #41 被设计性吸收且零提示（误判「键坏了」） | T1 voice_fwd v2.6：单按发 `MOUSE:MODE:ON` → HUD 提醒「模式仍开着」 | Mac 全链 `OK hud on/off` |
| 2 | 模式切换**应该提示**一下（否则不知生效没有） | T1 v2.5 只在本地消化开关，目标端收不到任何信号 | `MOUSE:MODE:ON\|OFF` 双端 HUD（Mac lua v1.3 / Win Tk 浮层 + 音） | `mode hud on/off (tk)`；Mac `OK hud on/off` |
| 3 | 模式内按**开机键没反应**，没法跳走打开应用 | `MouseMode.handle()` 对非映射键静默忽略 | T1 voice_fwd v2.6 放行（`MOUSE_PASSTHROUGH_CODES={116,102}`，含长按语义；本端无需改动） | key_fwd 104 PASS（§16 放行断言） |
| 4 | Windows 鼠标**特别快**，无法小距离移动 | 离散按压流 + 旧版唯一速度清零点在 `step()` → 速度跨按压累积 | `MouseGlide.stop()/_sweep()` 事件驱动清零（v1.12） | §19a 对照 11.67 vs 23.33 px/step |
| 5 | Windows **OK 键完全无反应**（短/长按） | ★ **跨模块 SendInput 类型冲突**（两模块各定义 INPUT 类 + `SendInput.argtypes` 互相覆盖 → win_actions 侧全部 SendInput 调用 TypeError 被 `except` 吞） | win_actions v1.13 结构上移通用层 + win_receiver v1.9 **复用同一类对象** + 4 处 except 落盘 + REPORT `input_class_module` 指纹 | **探针 `EXC TypeError`（14:15）→ `ok(1)`（14:23）** |

**升级与取证链**（全程零用户操作）：
1. Mac/T1 → RUN 通道 → `Downloads\update-win-receiver.bat` → ps1：[2/7] 升级前取证上传 →
   [3/7] 环境检查 → [4/7] T1:8000 拉新件 → [5/7] 备份停旧 → [6/7] 替换重启 → [7/7] selftest +
   升级后取证上传。
2. 取证直达 T1:8001/inbox（`windows-fingerprint-{pre,post}.txt` / `windows-pre-win_*.py` 源码存档 /
   `windows-selftest.log` / `windows-mouse-report.json`）；证据存 `windows/forensics-2026-10-13/`。
3. **v1.13 版 `MOUSE:REPORT` 探针** = 零位移 `MOUSEEVENTF_MOVE`（无害）+ `GetLastError`——
   「发送即取证」的常驻能力，本单的关键破案工具。

**当前版本**：win_receiver **v1.9** / win_actions **v1.13**（2026-10-13 14:23:30 装机，sha256 见 post 指纹）。
**回滚**：照 §3（每次升级自动创建 `.bak-<TS>` 备份链）。
