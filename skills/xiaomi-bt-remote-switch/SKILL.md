---
name: xiaomi-bt-remote-switch
description: "小米蓝牙遥控器切换：一句话把 T1（斐讯盒子）上小米蓝牙遥控器的行为目标切到 ATV/Apple TV/电视（atv）、macOS/Mac/电脑（mac）或 Windows/Windows/笔记本（win）。Use when 用户说「切换到电视/切到 Apple TV/换成 ATV」「切到 macos/mac/电脑」「切到 windows/windows/笔记本」「把遥控器切到××」「切换遥控器目标」「切换 T1 控制台」，或问「遥控器现在是什么模式/当前目标」。"
---

# 小米蓝牙遥控器切换

把斐讯 T1 盒子上**小米蓝牙遥控器**的行为目标（= 遥控器按键/语音送往哪台设备）一句话切好。
底层走 T1 网页控制台 API（`http://T1_IP:8765`，局域网、无鉴权）。

## 一句话用法

```bash
python3 scripts/switch.py atv     # → ATV / 电视 / Apple TV
python3 scripts/switch.py mac     # → macOS / 电脑
python3 scripts/switch.py win     # → Windows / Windows 笔记本
python3 scripts/switch.py status  # 查看当前目标
```

（在**本 skill 所在目录**下执行；也可用绝对路径 `<skill目录>/scripts/switch.py`。脚本本身也认识口语词，直接传「电视」「电脑」「笔记本」等也行。）

- 成功输出：`OK target=<atv|mac|win>`
- 失败输出：`FAIL …`（含原因）——**如实转告用户，不要假装成功**

## 口语 → 目标 映射（按用户约定）

| 目标 | 用户说法 |
| ---- | -------- |
| `atv` | ATV、Apple TV、电视、TV |
| `mac` | Mac、macOS、macos、电脑——**「电脑」按约定 = macOS**（不是 Windows） |
| `win` | Windows、Windows、win、笔记本 |

## 工作流

1. 从用户的话里识别目标（上表）→ 跑 `python3 scripts/switch.py <目标>`
2. 成功 → 用一句话确认，并带上该模式的行为（下表）
3. 用户只问「现在什么模式」→ 跑 `status` 后按名称报回（ATV / macOS / Windows）
4. 目标含糊（一句话同时含多台设备）→ 先问清再切

## 各模式行为（确认话术素材）

| 目标 | 名称 | 行为 |
| ---- | ---- | ---- |
| atv | ATV | 语音键 = 一键开 YouTube；按键 = 控制 Apple TV |
| mac | macOS | 语音键 = 按住说话输入；OK=回车 · 返回=Esc · 方向=方向键；主页键长按 = 应用选择器 |
| win | Windows | 与 Mac 完全同语义（转发链路已上线 ✅）：语音键 = 按住说话输入；OK=回车 · 返回=Esc · 方向=方向键；主页键长按 = 应用选择器 |

> 通用行为：**电源键连击切换设备**（1 击=ATV / 2 击=Mac / 3 击=Win）；**长按直播键** = 鼠标模式开关（mac / win 目标下）。

## 排错

- `FAIL 无法连接 T1`：确认 T1 在线（T1_IP）；重试一次；仍失败如实报告
- 服务端 400「target 必须是 atv/mac/win」= 参数错，检查映射表
- 幂等：切到与当前相同的目标没有任何副作用

## 维护说明

- 安装：把 `xiaomi-bt-remote-switch/` 目录放入你的 agent skills 目录（如 `~/.agents/skills/`）即可；
  改动请改源（`remote-hub/skills/xiaomi-bt-remote-switch/`）后同步两处，避免漂移。
- 依赖：仅 python3 标准库；`T1_WEBUI=host:port` 环境变量可覆盖服务地址
  （默认 T1_IP:8765，备选 127.0.0.1:8765——在 T1 本机执行时用）。
