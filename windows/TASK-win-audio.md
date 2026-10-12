# 任务：Windows「语音音频链」部署（Windows）—— 遥控器麦克风 → 虚拟声卡

> 本说明由 macOS 上的 WorkBuddy 会话编写（此前 `TASK-windows-deploy.md` 的续集）。
> 你是运行在 Windows 上的 WorkBuddy——请在本机完成**部署 + 自测**，并按 §5 输出报告。
> 前置任务（win_receiver 按键链路）已完工；本任务只做**语音音频**这一条链。

---

## 0. 背景（一句话）

T1（T1_IP）是蓝牙遥控器中继：遥控器麦克风的音频现在以 **UDP 双播**（Mac + 本机 WINDOWS_IP:8789）发出（T1 侧 `atvv_service v1.1` 已完成部署）。
本机需要：装一个**虚拟声卡**（VB-Cable）→ 跑一个**接收端**把音频写进虚拟声卡 → 微信输入法从虚拟声卡读麦克风。

```
遥控器 MIC → BLE → T1 → UDP:8789 → win_audio_receiver.py → "CABLE Input" ┐
                                                        （VB-Cable 虚拟线）│
微信输入法 ←── 麦克风选择 "CABLE Output" ←───────────────────────────────┘
```

体验目标：与 Mac 端一致——**按住遥控器语音键说话 → 松开 → 文字上屏**。

---

## 1. 交付物（从 T1 下载 / 一键脚本自动处理）

| 文件 | 地址 | 用途 |
|---|---|---|
| `update-win-audio.ps1` | `http://T1_IP:8000/update-win-audio.ps1` | 一键部署/更新脚本（下载主程序→装依赖→启动→自检） |
| `win_audio_receiver.py` | `http://T1_IP:8000/win_audio_receiver.py` | 接收端主程序（脚本会自动下载，无需手动） |

---

## 2. 步骤

### 2.1 安装虚拟声卡 VB-Audio Virtual Cable（人工，一次性）

1. 打开 https://vb-audio.com/Cable/ → 下载 `VBCABLE_Driver_Pack*.zip` → 解压。
2. 右键 `VBCABLE_Setup_x64.exe` → **以管理员身份运行** → 点 "Install Driver"。
3. **若安装器要求重启：先重启**（驱动加载），回来继续。
4. 重启后在 Windows「声音设置」确认新设备出现：
   - 播放（输出）设备：`CABLE Input (VB-Audio Virtual Cable)`
   - 录音（输入）设备：`CABLE Output (VB-Audio Virtual Cable)`

> 若没有出现 → 重新以管理员运行安装器，再重启一次。

### 2.2 一键部署（PowerShell，无需管理员）

```powershell
irm http://T1_IP:8000/update-win-audio.ps1 | iex
```

脚本自动：检查 python → 安装 pip 依赖（numpy + sounddevice，走清华源）→ 下载 `win_audio_receiver.py` → 启动（隐藏窗口）→ PING 自检 `:8789`。
预期末尾出现 `('PONG', ...)` 与 `DONE.`。
若 PING 超时：按脚本提示（多半是 VB-Cable 未装或未重启），处理后**再跑一遍**（脚本幂等）。

### 2.3 防火墙（管理员，一次性）

```powershell
# 管理员 PowerShell
New-NetFirewallRule -Name 'remotehub-win-audio' -DisplayName 'RemoteHub Windows audio (UDP 8789)' -Enabled True -Direction Inbound -Protocol UDP -LocalPort 8789 -Action Allow
```

> 拿不到管理员权限：首次运行接收端时 Windows 弹「防火墙已阻止部分功能」——勾选允许（专用网络）。

### 2.4 微信输入法：麦克风设备指向虚拟声卡

优先在**微信输入法设置**里找「麦克风 / 录音设备」选项，选 **`CABLE Output (VB-Audio Virtual Cable)`**。
若输入法没有该选项（跟随系统默认），则二选一并在报告中注明：
- 系统设置 → 声音 → 输入 → 默认设备改为 `CABLE Output`（注意：其他需要真实麦克风的应用会受影响）；或
- 报告「无应用级设置」，由用户决定。

### 2.5 验收测试（需要用户配合按遥控器）

1. **先切换遥控器目标到 Windows**：浏览器打开 `http://T1_IP:8765/` → 点 **Windows** 按钮。
   （语音触发="按住 Ctrl+Win" 只会在目标=Windows 时注入到本机；这一步不能省。）
2. 请用户**按住遥控器语音键 2~3 秒说一句话，松开**。
3. 预期：微信输入法出字（与 Mac 上体验一致）。
4. 同时检查日志 `audio_receiver.log` 应出现 `session start` / `session end ... frames=N`（N>0）。

### 2.6 开机自启（可选，建议；与 win_receiver 同款计划任务）

确认 2.2 的实例在跑（或先停掉），然后：

```powershell
$dir = "$env:USERPROFILE\remotehub-win"
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { $pyw = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe" }  # 按实际改
$act = New-ScheduledTaskAction -Execute $pyw -Argument "$dir\win_audio_receiver.py" -WorkingDirectory $dir
$trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'remotehub-win-audio' -Action $act -Trigger $trg -Settings $set -Description 'RemoteHub Windows audio receiver' -Force
Start-ScheduledTask -TaskName 'remotehub-win-audio'
Get-ScheduledTask -TaskName 'remotehub-win-audio' | Get-ScheduledTaskInfo
```

> 注意：先停掉手动实例再注册启动（同一端口 8789 只能一个实例；双实例时第二个会 bind 失败退出，属正常保护）。

---

## 3. 诊断速查

| 目的 | 命令（在 `$dir` 下） |
|---|---|
| 列音频设备（找 CABLE Input 的编号/名称） | `python win_audio_receiver.py --list` |
| 链路诊断（不依赖声卡） | 先停正常实例 → `python win_audio_receiver.py --dry-run` → 按遥控器语音键 → 日志出现 `session ... frames=N` = T1→本机链路通 → Ctrl+C 后重启正常实例 |
| 本机 PING | `python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3);s.sendto(b'PING',('127.0.0.1',8789));print(s.recvfrom(64))"` |
| 看日志 | `Get-Content $dir\audio_receiver.log -Tail 20` |
| 重启接收端 | 停进程后 `pythonw win_audio_receiver.py`（或计划任务 `Start-ScheduledTask -TaskName 'remotehub-win-audio'`） |

常见故障：
- 日志 `output device not found: 'cable input'` → VB-Cable 没装/没重启，或设备名不同（用 `--list` 看实际名，`--device "..."` 指定）。
- 日志 `FATAL bind udp :8789 failed` → 已有实例在跑（正常保护）。
- 有帧（session frames>0）但输入法不出字 → 麦克风设备没选 CABLE Output（§2.4）；或没把目标切到 Windows（§2.5 第 1 步）。

---

## 4. 验收标准（全过才算完成）

- [ ] VB-Cable 安装完成，设备列表可见 `CABLE Input` / `CABLE Output`（`--list` 输出为证）
- [ ] `update-win-audio.ps1` 运行成功，`:8789` PING 返回 PONG
- [ ] 防火墙放行 UDP 8789（或弹窗允许）
- [ ] `audio_receiver.log` 在用户按语音键后出现 `session start` + `session end ... frames=N`（N>0）
- [ ] **用户实测：按住遥控器语音键说话 → 松开 → 微信输入法出字**（最终验收）
- [ ] 报告 §5 所需信息齐全

---

## 5. 报告格式（完成后输出，粘给用户）

```
# Windows 语音音频链 部署报告
- 完成时间：
- 机器：主机名 / Windows 版本 / 用户名
- VB-Cable：已装（安装后是否重启）/ 未装
- --list 输出（贴 CABLE 相关行 + 设备索引）：
- update 脚本结果：deps / 下载 / 启动 / PING 输出（贴原文）
- 防火墙：规则已建 / 弹窗允许 / 未做
- 微信输入法麦克风设置：应用级选了 CABLE Output / 改系统默认 / 无此设置
- 日志尾部（按语音键测试后 audio_receiver.log 最后 15 行）：
- 实测结果：出字 / 不出字（现象描述）/ 无法测试（原因）
- 其它偏差/异常：
```

---

## 6. 硬约束

1. **不要改** UDP 端口（8789）与包格式（`[1B type][payload]`，0x01/0x02/0x03 + PING/PONG）——T1 侧已按此实现（`atvv_service v1.1` 双播 Mac + Windows）。
2. 接收端必须在**用户登录会话**内运行（`pythonw.exe`；**不要**注册成 Windows 服务——那会收不到桌面音频会话）。
3. 依赖安装仅 numpy + sounddevice（pip）；除 VB-Cable 外不需要其它驱动。
4. 只监听局域网 UDP + 本机回 PONG，不做任何外发。
5. 若文档与实际情况冲突：以「不改端口/协议 + 用户会话运行」两条为准，自行适配并在报告中注明偏差。
6. 本任务**不动**已有 win_receiver（8788/8791 按键/语音触发链）——两条链互不相干，可同时运行。
