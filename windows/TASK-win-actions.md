# TASK-win-actions — Windows 遥控扩展动作上线（win_receiver v1.2）

> 施工方：Windows 上的 WorkBuddy（或用户手动）。
> 背景：T1 遥控器的三类动作此前在 Windows 端缺失——**CLICK**（点击焦点元素）、
> **FOCUS_INPUT**（跳输入框）、**APP:\***（应用切换/选择器/启动）。v1.2 补齐，
> 此后 Windows 与 Mac 的遥控行为完全对齐。
> 前置：win_receiver **v1.1 正在运行**（若否，先按 `TASK-windows-deploy.md` 首次部署）。

---

## 步骤 1：一键更新

在 Windows 的 PowerShell 里执行：

```powershell
irm http://T1_IP:8000/update-win-receiver.ps1 | iex
```

脚本流程（6 步）：定位实例 → 装 uiautomation 依赖（清华源）→ 下载两个文件 →
备份旧文件（`.bak-<时间戳>`）→ 替换并重启（隐藏窗口）→ PING 自检 + selftest。

**可能出现的情况：**
- `uiautomation OK` / `uiautomation missing -> installing ...`：都正常；
  若最终 `WARN: uiautomation install failed` —— 不阻塞（APP:* 不受影响），
  请在报告里注明。
- PING 部分应输出 `PONG`。
- 末尾 `--- selftest ---` 段落：这是关键信息，**原样贴回**。

---

## 步骤 2：读 selftest 输出

selftest 会打印（并同时写入实例目录 `selftest.log` 的 UTF-8 完整版）：

```
win_actions v1.0 selftest
platform: win32 | dpi: per-monitor-v2 | uia: ready
top-level windows (filtered): N | apps: M
  xxx.exe           | 窗口标题...
focused element: type=50000 name=... rect=(...)
```

**报告时请贴回此段**（ASCII 安全版即可；中文标题会显示为 `?`，正常）。

---

## 步骤 3：功能验收（三条 UDP 直发命令）

> 此阶段**不需要** T1 遥控器（键位表稍后再配），直接用本地 UDP 触发：
> 所有命令都用 **python** 执行（不要用 pythonw）。

### 3.1 APP:CYCLE（应用轮询）

先随手打开 2-3 个应用窗口（浏览器 / 记事本 / WorkBuddy / 资源管理器），
然后执行（连续跑 2-3 次，每次间隔 1 秒以上）：

```powershell
python -c "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'KEY APP:CYCLE DOWN',('127.0.0.1',8791)); time.sleep(0.3); s.sendto(b'KEY APP:CYCLE UP',('127.0.0.1',8791))"
```

预期：前台窗口在打开的多个应用间轮换（每次切到「下一个」）。
连续发多次应继续轮换，而不是来回跳。

### 3.2 APP:PICK（应用选择器）

```powershell
python -c "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'KEY APP:PICK DOWN',('127.0.0.1',8791)); time.sleep(0.3); s.sendto(b'KEY APP:PICK UP',('127.0.0.1',8791))"
```

预期：屏幕弹出一个「切换应用」列表窗口（列出所有可见应用）。
用键盘 ↑↓ 选择，回车激活目标应用，Esc 或退格取消。

### 3.3 CLICK（点击焦点元素）

测试场景（任选其一，推荐 A）：

**A. 浏览器链接：**
1. 打开浏览器（Edge/Chrome），访问 https://www.baidu.com
2. 连按 Tab 键数次，直到页面内某个链接/按钮出现**虚线焦点框**（通常 2-5 次内）
3. 执行：

```powershell
python -c "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'KEY CLICK DOWN',('127.0.0.1',8791)); time.sleep(0.3); s.sendto(b'KEY CLICK UP',('127.0.0.1',8791))"
```

预期：该链接/按钮被「点击」（页面跳转或按钮触发）。

**B. 任务栏按钮（备选）：**
1. 按 `Win+B`（焦点进入任务栏），用方向键移到某个任务栏图标
2. 发上面的 CLICK 命令
3. 预期：对应应用被唤起/前景化

### 3.4 FOCUS_INPUT（跳输入框）

**推荐用 WorkBuddy 自己的窗口测试：**
1. 打开 WorkBuddy（Windows 上本会话的宿主）
2. 用鼠标点击「消息列表区/历史区」（让输入焦点离开底部输入框）
3. 执行：

```powershell
python -c "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'KEY FOCUS_INPUT DOWN',('127.0.0.1',8791)); time.sleep(0.3); s.sendto(b'KEY FOCUS_INPUT UP',('127.0.0.1',8791))"
```

4. 预期：输入光标跳到输入框（直接打字应出现在输入框里）

备选场景：浏览器页面里点空白处 → 发命令 → 光标应跳到页面第一个输入框。

### 3.5 读日志（重要证据）

```powershell
Get-Content "$env:USERPROFILE\remotehub-win\receiver.log" -Tail 25
```

（若实例不在默认目录，用 `[1/6]` 步骤打印的 `dir`。）
每次触发应有对应行，例如：

```
EXT CLICK -> CLICK press self type=50000 name=...   （或 press child / press upN / click@x,y）
EXT FOCUS_INPUT -> FOCUS_INPUT OK src=grid type=... [winfix=raise]
EXT APP:CYCLE -> cycle[z序] -> chrome.exe ok (重建 idx=1/3)
EXT APP:PICK -> picker opened (↑↓ 选择 / OK 打开 / 返回 取消)
```

---

## 步骤 4：报告格式

完成后把以下内容贴回：

```
1) 更新脚本全程输出（含 selftest 段）
2) 3.1 APP:CYCLE: [预期轮换 / 异常描述]
3) 3.2 APP:PICK: [弹窗正常 / 异常描述]
4) 3.3 CLICK: [链接被点击 / 无反应, 附 log 行]
5) 3.4 FOCUS_INPUT: [光标跳转 / 无反应, 附 log 行]
6) receiver.log 最后 25 行
```

---

## 回滚

```powershell
# 1. 找到实例目录（receiver.log 所在处），停止进程
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'win_receiver\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 2. 恢复备份（时间戳取自更新输出）
# dir = 实例目录
Move-Item -Force "$dir\win_receiver.py.bak-<TS>" "$dir\win_receiver.py"
Move-Item -Force "$dir\win_actions.py.bak-<TS>"  "$dir\win_actions.py"
# 3. 重新启动（与更新脚本相同方式）
```

---

## 附录：遥控器键位绑定（更新验收后，由用户决定）

打开 http://T1_IP:8765/keymap → 切到 **Windows** 标签页，可把任意按键的
单击/长按绑定为：`CLICK` / `FOCUS_INPUT` / `APP:CYCLE` / `APP:TOGGLE` / `APP:NEXT`
/ `APP:PICK` / `APP:<exe 名或窗口标题关键词>`。保存即热生效（无需重启任何服务）。

Mac 份现行键位（对齐参考）：
| 键 | 单击 | 长按 |
|---|---|---|
| OK (#28) | ENTER | **CLICK** |
| 直播 (#41) | **FOCUS_INPUT** | — |
| 主页 (#102) | **APP:CYCLE** | **APP:PICK** |
| 电源 (#116) | **APP:workbuddy** | — |
