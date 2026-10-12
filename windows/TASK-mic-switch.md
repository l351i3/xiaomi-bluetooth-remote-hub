# TASK-mic-switch.md — Windows 麦克风按需自动切换（方案 V）施工单

> 前置背景：T1 项目「三端方案」语音链。Windows 侧接收端本次从 **v1.2 升到 v1.3**。
> v1.3 新增 `win_audio_switch.py`：遥控语音键**按下** → 系统「默认录音设备」切到
> **CABLE Output**（虚拟录音端）；**松开后 ~2s 自动切回**原设备。
> 配合微信输入法麦克风=「默认设备」使用：平时录真麦不受影响，遥控会话自动让位。
> （麦克风下拉里「默认设备」选项已由用户确认存在。）
>
> 由 T1（T1_IP）侧下发；执行方：Windows 侧 WorkBuddy。**全程只在本机操作，无网络外发。**

---

## §0 原理与时序

```
遥控语音键按下
  → T1 voice_fwd → UDP :8788 "VOICE down"
  → v1.3 接收端：① 先把系统默认录音设备切到 CABLE Output（~100-300ms）
                 ② 再注入 Ctrl+Win（微信输入法开始录音, 读「默认设备」= CABLE）
  → 声音走：T1 遥控 MIC → T1 atvv_service → (UDP:8789) → CABLE Input → === 虚拟线 === → CABLE Output → 输入法
遥控语音键松开
  → "VOICE up" → 注入释放 Ctrl+Win（输入法提交文字）
  → 延迟 2s（输入法收尾缓冲）→ 自动把默认录音设备切回原设备
连按（2s 内又按下）→ 自动取消待切回，保持 CABLE；过晚再按则重新走上面全流程
```

要点：
- **fail-open**：设备切换失败（如虚拟设备缺失）只记日志，**不影响**按键注入链路；
- **崩溃自愈**：若进程在「已切到 CABLE」状态下退出，下次启动自动切回原设备（state/audio_switch.json）；
- 切换只影响「跟随系统默认设备」的应用；显式绑定 CABLE 的应用（如把输入法写死 CABLE 时）不受影响。

---

## §1 更新到 v1.3

### 1A. 一键更新（若 `irm | iex` 未被本机策略拦截）

```powershell
irm http://T1_IP:8000/update-win-receiver.ps1 | iex
```

脚本 6 步：定位实例 → 检查 python/uiautomation → 下载 3 文件 → 备份(.bak-TS)+停旧进程 →
替换+清 `__pycache__`+隐藏重启 → PING 自检 + selftest。

### 1B. 等效步骤（**推荐**——上次 `irm | iex` 因 `Invoke-Expression` 黑名单被拦，这次可直接走此路）

```powershell
# -- 0) 先看现状：找运行中的实例
$p = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
     Where-Object { $_.CommandLine -match 'win_receiver\.py' } | Select-Object -First 1
$p.ProcessId; $p.CommandLine
$dir = Split-Path ($p.CommandLine -replace '.*?"([A-Za-z]:\\[^"]*?win_receiver\.py)".*','$1')
Write-Host "dir=$dir"   # 若解析失败, 手动填写 win_receiver.py 所在目录

# -- 1) 下载 3 个文件（到临时名, 不动现网）
Invoke-WebRequest "http://T1_IP:8000/win_receiver.py"     -OutFile "$dir\win_receiver.new"     -UseBasicParsing
Invoke-WebRequest "http://T1_IP:8000/win_actions.py"      -OutFile "$dir\win_actions.new"      -UseBasicParsing
Invoke-WebRequest "http://T1_IP:8000/win_audio_switch.py" -OutFile "$dir\win_audio_switch.new" -UseBasicParsing

# -- 2) 核对 sha256（与本单尾部 §5 清单核对; 不一致即停止并上报）
Get-FileHash "$dir\win_receiver.new","$dir\win_actions.new","$dir\win_audio_switch.new" -Algorithm SHA256

# -- 3) 审查新文件（win_audio_switch.new 为本轮新增, 重点审: 无网络外发 / 无提权 / 只调音频 COM 与注册表读）
# -- 4) 备份 + 停旧进程
$TS = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item "$dir\win_receiver.py" "$dir\win_receiver.py.bak-$TS" -Force
if (Test-Path "$dir\win_actions.py")      { Copy-Item "$dir\win_actions.py"      "$dir\win_actions.py.bak-$TS"      -Force }
if (Test-Path "$dir\win_audio_switch.py") { Copy-Item "$dir\win_audio_switch.py" "$dir\win_audio_switch.py.bak-$TS" -Force }
Stop-Process -Id $p.ProcessId -Force; Start-Sleep -Milliseconds 800

# -- 5) 替换 + 清缓存 + 隐藏重启
Move-Item -Force "$dir\win_receiver.new"     "$dir\win_receiver.py"
Move-Item -Force "$dir\win_actions.new"      "$dir\win_actions.py"
Move-Item -Force "$dir\win_audio_switch.new" "$dir\win_audio_switch.py"
Remove-Item -Force -Recurse "$dir\__pycache__" -ErrorAction SilentlyContinue
Start-Process -FilePath $p.ExecutablePath -ArgumentList "`"$dir\win_receiver.py`"" -WorkingDirectory $dir -WindowStyle Hidden
Start-Sleep -Seconds 2

# -- 6) 自检
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3);s.sendto(b'PING',('127.0.0.1',8788));print(s.recvfrom(64))"
python "$dir\win_receiver.py" --selftest
```

> ⚠️ 注意：`win_actions.py` 服务器版已合入上次的「最小化→还原」兜底补丁（本单 §5 有校验值），
> 重跑更新**不会**再丢补丁。

---

## §2 selftest 解读（v1.3 新增音频段）

`--selftest` 输出开头新增：

```
win_audio_switch: v1.1
capture devices (3):
  麦克风阵列 (...)                                     [DEFAULT]
  CABLE Output (VB-Audio Virtual Cable)                [VIRTUAL]
  立体声混音 (...)
virtual match 'cable output': CABLE Output (VB-Audio Virtual Cable)
```

- `[VIRTUAL]` = 匹配到的虚拟录音设备（若为空 → 检查 VB-Cable 是否装好）；
- `[DEFAULT]` = 当前系统默认录音设备（**打印的是感知原始值, 请人工确认是否符合预期**）。

---

## §3 验收（UDP 直发, 逐条做 + 记录原始输出）

**3.0 确认 v1.3 在跑**：读日志尾部应含 `=== remotehub-win receiver v1.3 starting ===`
与 `win_audio_switch v1.1 loaded (N capture devices)`；顺带确认音频链进程未受影响。

```powershell
Get-Content "$dir\receiver.log" -Tail 30
```

**3.1 记录切换前默认设备**（status 快照 A）：

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "import win_audio_switch as w; print(w.status())"
# 若 cwd 不在脚本目录, 先 cd $dir
```

**3.2 模拟按下（VOICE down）→ 期望默认切到 CABLE**：

```powershell
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE down',('127.0.0.1',8788))"
Start-Sleep -Milliseconds 800
python -c "import win_audio_switch as w; print(w.status())"        # 快照 B: [DEFAULT] 应在 CABLE Output 行
Get-Content "$dir\receiver.log" -Tail 6                            # 应见: mic switch -> ok=True [switched -> CABLE Output ...] (NNms)
```

**3.3 模拟松开（VOICE up）→ 期望 ~2s 后自动切回**：

```powershell
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE up',('127.0.0.1',8788))"
Start-Sleep -Seconds 3
python -c "import win_audio_switch as w; print(w.status())"        # 快照 C: [DEFAULT] 应回到 3.1 的原设备
Get-Content "$dir\receiver.log" -Tail 8                            # 应见: VOICE stop / mic restore scheduled / delayed restore -> ok=True [restored]
```

**3.4 连按保护**：down → up → **1 秒内再** down → 等 3s → 期望默认仍停在 CABLE（未被切回）：

```powershell
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE down',('127.0.0.1',8788))"
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE up',('127.0.0.1',8788))"
Start-Sleep -Milliseconds 900
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE down',('127.0.0.1',8788))"
Start-Sleep -Seconds 3
python -c "import win_audio_switch as w; print(w.status())"        # 快照 D: [DEFAULT] 仍应 = CABLE Output
python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'VOICE up',('127.0.0.1',8788))"   # 收尾
Start-Sleep -Seconds 3
python -c "import win_audio_switch as w; print(w.status())"        # 快照 E: 已切回原设备
```

**3.5 真人实测（与用户配合；放在 §4 改完输入法设置之后）**：
- 遥控器按住语音键说话（例：今天天气怎么样）→ 松开 → 文字应上屏；
- 本机麦克风直接按 Ctrl+Win 说话 → 文字也应上屏（验证平时不被干扰）。

---

## §4 用户侧设置（一次性）

微信输入法 → 设置 → 语音（麦克风下拉）→ 把麦克风从「CABLE Output」改为「**默认设备**」。

> 顺序要求：**先完成 §1 更新 + §3.1-3.4 技术验收，再改此设置**。改完后 3.5 实测。
> （改设置前：输入法写死 CABLE == 遥控可用、本机麦克风语音不可用；
>  改设置后：系统默认设备由 v1.3 按需切换 → 两者都可用。）

---

## §5 校验清单（sha256, 与 T1 :8000 分发件双端核对一致）

| 文件 | sha256 |
|---|---|
| win_receiver.py (v1.3) | `38cbef6dad12e4b07d377a2c8e322f3c59a5fcdf836c9a776b6368dad4b03bcd` |
| win_actions.py (v1.0+补丁合并版) | `2c537a2015adb8fe7c8d086dd74ebbd7ef1243aeae856f1ec5d4755b6db202e5` |
| win_audio_switch.py (v1.1) | `87fa9fe306ca307ac2865c5d36f97b49bec91e1c7cf7d673b220ab9c9cf1caed` |
| update-win-receiver.ps1 (v1.3) | `3990e881bc2f8b0ea3659b85f969cdacb07aebd389275412571d576ef88671b1` |

## §6 回滚

```powershell
# 找进程 → 停 → 换回 .bak-$TS 三个文件（原样恢复旧版）→ 重启
# 单点回退（不改代码）：微信输入法麦克风改回「CABLE Output」即回到改动前行为
```

## §7 报告格式（回传）

按上次 `report-*.md` 格式：执行方式与偏差 → 全程输出 → selftest 段 → §3 各快照（A-E +
日志行）→ 问题与结论 → 运行态（PID、监听端口、音频链完好性）→ 回传 T1 :8001
（`Invoke-WebRequest -Uri "http://T1_IP:8001/upload/report-mic-switch.md" -Method POST -InFile <路径> -UseBasicParsing`）。
