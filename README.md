# xiaomi-bluetooth-remote-hub

> 把一只**小米蓝牙遥控器（RC003）**变成跨三端的中枢输入设备：
> **Apple TV 全键遥控 · macOS / Windows「无线麦克风 + 无线键盘 + 宏动作」**。
> 遥控器 → 斐讯 T1（PHICOMM-T1）盒子中继 → 目标端（三选一，随时切换）。

```
小米遥控器（RC003）
   │  BLE（HID/HOG 按键 + ATVV 语音流）
   ▼
斐讯 T1 盒子（枢纽：转发 / 中继 / 网页遥控台 :8765）
   ├── UDP 8788（语音）· 8789（音频回传）· 8791（按键） ──► macOS 主机（键盘+麦克风注入）
   ├──────────────────────────────────────────────────────► Windows 主机（同上，键位与 macOS 完全一致）
   └── pyatv（Companion + AirPlay）──────────────────────► Apple TV 4K（原生遥控 + 语音键一键开 YouTube）
```

## 亮点

- **语音即无线麦克风**：按住遥控器语音键说话，音频经 T1 实时转发到目标端的虚拟声卡，由**本机输入法**直接上屏（不做本机识别，复用你已有的语音输入法）；
- **按键即键盘**：麦克风 / 回车 / 退格 / 方向 / 翻页……全部可配，网页台三 tab 热配置，三端键位可完全对齐；
- **宏动作**：应用选择器（图标网格）、切换 / 关闭应用、跳输入框、点击焦点元素、打开网页、执行命令；
- **网页遥控台**：`http://<T1_IP>:8765/`——切目标、改键位、看状态，一个页面全搞定。

## 仓库导航

| 文档 | 内容 |
|---|---|
| [docs/02-USER-GUIDE.md](docs/02-USER-GUIDE.md) | 使用指南（3 分钟上手） |
| [docs/03-DEV-GUIDE.md](docs/03-DEV-GUIDE.md) | 架构 / 协议 / 开发 / 部署 |
| [docs/04-CHANGELOG.md](docs/04-CHANGELOG.md) | 完整变更史（2026-10-07 起，叙事式） |
| [mac-key-bridge.md](mac-key-bridge.md) | macOS 注入端设计（CGPost / 熔断 / 动作语法） |
| [t1-webui.md](t1-webui.md) | 网页遥控台设计（三 tab / 指纹校验 / 动作下拉） |
| [hammerspoon-focus.md](hammerspoon-focus.md) | 焦点子系统（跳输入框 / 点击焦点元素） |
| [voice-diagnosis-2026-10-10.md](voice-diagnosis-2026-10-10.md) | 语音链路一次完整故障诊断复盘 |
| [rc003-keymap.md](rc003-keymap.md) | RC003 键值全表（13 键采集） |
| [relay-daemon-design.md](relay-daemon-design.md) | 中继 daemon 设计草案 |

## 代码地图

| 端 | 主要文件 |
|---|---|
| T1（枢纽） | `voice_fwd.py` `relay_min.py` `t1_webui.py` `atvv_service.py` `t1_evwatch.py`；`t1-systemd/` |
| macOS（注入端） | `key_bridge.py` `voice_bridge.py` `atvv_receiver.py` `app_switch.swift` `AppPicker.swift` `hammerspoon/` `mac-launchd/` |
| Windows（接收端） | `windows/`（`win_receiver.py` `win_actions.py` `win_audio_switch.py` `win_audio_receiver.py`） |
| 诊断工具 | `t1_sniff.py` `parse_t1_frames.py` `atvv_decode.py` `speech_forensics.py` `bh_stream_rec.py` 等 |
| 测试 | `*_test.py` / `*_test.mjs` / `windows/*_offline_test.py` |
| Agent skill | `skills/xiaomi-bt-remote-switch/`（一句口语切换遥控目标） |

## 快速开始（使用侧）

1. **遥控器与 T1 配对**：长按【直播键】3~5 秒至指示灯快闪；
2. 打开网页遥控台 `http://<T1_IP>:8765/`，选目标（ATV / macOS / Windows）；
3. **按住语音键说话 → 松开 → 文字上屏**；按键即键盘（详见使用文档）。

## 部署（三端）

| 端 | 内容 | 要点 |
|---|---|---|
| T1 | `t1-systemd/` 三个 unit + 脚本 | 服务自启；网页台 :8765 |
| macOS | `mac-launchd/` plist ×5 + 脚本 | 注入件受 TCC 约束，**换机需重新授权**（见下） |
| Windows | `windows/` + `setup-windows.ps1` | 计划任务自启；UWP 应用经 Shell 通路取图标 |

## 占位符约定

文档与脚本中的地址一律为占位符，部署时全文替换为你的环境值：

| 占位符 | 含义 |
|---|---|
| `T1_IP` | T1 盒子的局域网地址 |
| `MACOS_IP` / `WINDOWS_IP` | 两台目标主机 |
| `GW_IP` / `LAN_IP` | 网关 / 其他内网主机 |
| `username` | 用户名占位 |

两台目标主机在文档中统一用平台通名 **macOS / Windows** 指代（不暴露真实主机名）。

## 技术栈

Python 3（生产件零第三方依赖为主）· Swift（macOS 注入 / 选择器）· Hammerspoon（焦点子系统）·
pyatv（Apple TV）· UDP 自定义总线 · systemd / launchd / Windows 计划任务。

## 姊妹项目

- **[phicomm-t1-system-fix](https://github.com/l351i3/phicomm-t1-system-fix)** —— T1 的系统修复线（蓝牙固件加载 + 关机链路修复 + 救援盘）。

## 说明

- 本项目为个人自用系统的开源存档：含真机部署路径与内网环境假设（见各文档），移植需按环境调整；
- macOS 注入件（`CGPost.app` / `iohid_post`）受 TCC 授权机制约束（授权绑定路径 + cdhash）——**换机器需重新授权**，源码在 `cgpost.c` / `iohid_post.c`；
- 历史过程物（备份链 / 运行日志 / 回传归档）不入库，保留于维护者本地。

## 许可与免责

- 本项目为个人项目，现以 **MIT 许可证**发布（见 [`LICENSE`](LICENSE)）——可自由使用、修改、分发，保留版权声明即可。
- 代码按「现状」提供，不附带任何担保。
