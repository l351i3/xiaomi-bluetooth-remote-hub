# 任务：Windows「遥控接收端」部署（Windows）

> 本说明由同一账号下 macOS 上的 WorkBuddy 会话编写。
> 你是运行在 Windows 上的 WorkBuddy——请在本机完成下面的**部署 + 自测**，并按要求输出报告。

---

## 0. 背景（一句话）

家中有一台斐讯盒子 **T1（T1_IP）** 做蓝牙遥控器中继。当遥控器目标切到 Windows 时，
T1 会把两类 UDP 包发到**本机 WINDOWS_IP**：

| 端口 | 消息 | 含义 |
|---|---|---|
| `:8788` | `VOICE down` / `VOICE up` | 按住 / 松开遥控器的语音键 |
| `:8791` | `KEY <动作> DOWN` / `KEY <动作> UP` | 普通按键（回车/返回/方向/翻页等） |

本任务 = 在本机部署一个 Python 小程序（接收端），把这些包转成：
- **语音**：按住 **Ctrl + Win**（触发微信输入法语音输入）
- **按键**：注入对应的键盘事件

---

## 1. 交付物（从 T1 下载）

先把两个文件下载到 `%USERPROFILE%\remotehub-win\`（下称 `$DIR`）：

| 文件 | 地址 | 用途 |
|---|---|---|
| `win_receiver.py` | `http://T1_IP:8000/win_receiver.py` | 接收端主程序 |
| `selftest_send.py` | `http://T1_IP:8000/selftest_send.py` | 本机自测（模拟 T1 发包） |

下载命令示例（PowerShell）：

```powershell
$dir = "$env:USERPROFILE\remotehub-win"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Invoke-WebRequest -Uri 'http://T1_IP:8000/win_receiver.py'  -OutFile "$dir\win_receiver.py"
Invoke-WebRequest -Uri 'http://T1_IP:8000/selftest_send.py' -OutFile "$dir\selftest_send.py"
```

> 这是局域网内网地址（T1），浏览器直接打开 `http://T1_IP:8000/` 也能看到文件列表。

---

## 2. 步骤

### 2.1 确认 Python 3
```powershell
python --version
```
没有就装（任选其一）：
- `winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements`
- 或从 python.org 下载安装包手动安装（勾选 Add to PATH）

要求 Python 3.8+；只用标准库，无需 pip 安装任何依赖。

### 2.2 下载交付物
见上文 §1。

### 2.3 防火墙（需要管理员）
允许 UDP 8788 / 8791 入站（其它设备才能发进来）：

```powershell
# 管理员 PowerShell
New-NetFirewallRule -Name 'remotehub-win' -DisplayName 'RemoteHub Windows (UDP 8788/8791)' -Enabled True -Direction Inbound -Protocol UDP -LocalPort 8788,8791 -Action Allow
```

> 若拿不到管理员权限：跳过本步，先做 2.4 手动运行接收端，
> Windows 会弹「防火墙已阻止部分功能」——勾选允许访问（家庭/专用网络即可）。

### 2.4 手动跑一次（前台）
```powershell
python "$env:USERPROFILE\remotehub-win\win_receiver.py"
```
预期输出两行：
```
... listening udp :8788 (handle_voice)
... listening udp :8791 (handle_key)
```
若出现 `FATAL bind udp ... another instance running?` = 已经有一个实例在跑（属正常保护）。

### 2.5 自测
**另开一个终端**（接收端保持运行）：
```powershell
python "$env:USERPROFILE\remotehub-win\selftest_send.py"
```
预期：
- selftest 打印 9 个测试包 + `PONG: PONG | from 127.0.0.1`
- 接收端控制台与 `$DIR\receiver.log` 新增 10 条 `RX ...` 记录（9 个测试包 + 1 个 PING）
- （可选眼见）先在记事本/浏览器放好焦点，能看到 PageDown 滚动、回车换行等效果

### 2.6 注册开机自启（当前用户，无需管理员）
先 **Ctrl+C 停掉** 2.4 的手动实例（避免端口冲突），然后：

```powershell
$dir = "$env:USERPROFILE\remotehub-win"
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { $pyw = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe" }  # winget 安装的常见路径，按实际改
$act = New-ScheduledTaskAction -Execute $pyw -Argument "$dir\win_receiver.py" -WorkingDirectory $dir
$trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'remotehub-win-receiver' -Action $act -Trigger $trg -Settings $set -Description 'RemoteHub Windows receiver' -Force
Start-ScheduledTask -TaskName 'remotehub-win-receiver'
Get-ScheduledTask -TaskName 'remotehub-win-receiver' | Get-ScheduledTaskInfo
```

启动后确认 `$DIR\receiver.log` 尾部出现新的 `=== remotehub-win receiver starting ===`（即任务实例接管成功）。

### 2.7 写报告
把 §3 的内容写成 `$DIR\report.md`，并贴给用户。

---

## 3. 报告格式（完成后输出）

```
# RemoteHub Windows 部署报告
- 完成时间：
- 机器：主机名 / Windows 版本（如 Windows 11 23H2）/ 用户名
- Python：版本 + 安装方式（原有 / winget / 其它）
- 防火墙：规则 'remotehub-win' 已建 / 或"弹窗手动允许"
- 接收端手动自测：selftest 输出 + receiver.log 最后 12 行
- PING/PONG：结果
- 计划任务：任务名 remotehub-win-receiver 的状态（State / LastRunTime）
- 微信输入法：本机是否安装？其语音快捷键实际值（设置里看，期望"按住 Ctrl+Win"）
- 其它偏差/异常：
```

---

## 4. 验收标准（全过才算完成）

- [ ] selftest 后 `receiver.log` 有 10 条 RX（9 测试包 + 1 PING）
- [ ] PING 收到 PONG
- [ ] 计划任务 `remotehub-win-receiver` 已注册并运行（Ready/Running）
- [ ] 防火墙放行 UDP 8788/8791（规则或手动允许）
- [ ] 微信输入法语音快捷键已核实（或已注明实际值）

---

## 5. 注意（硬约束）

1. **不要改** UDP 端口（8788/8791）与消息格式（`VOICE down`、`KEY <动作> DOWN/UP`）——T1 侧已按此实现。
2. 键盘注入必须在**用户登录会话**内运行（用 `pythonw.exe` 跑即可；**不要**注册成 Windows 服务）。
3. 若微信输入法语音键不是 Ctrl+Win：在报告里注明实际值，或改 `win_receiver.py` 顶部 `VOICE_MODS` 一行（注释有说明）。
4. 接收端只监听局域网 UDP，不做任何外发；不需要联网下载依赖。
5. 双实例会"绑定失败退出"，属正常保护（log 里有 FATAL）。
6. 若文档与实际情况冲突：以「不改端口/协议 + 用户会话运行」两条为准，自行适配并在报告中注明偏差。
