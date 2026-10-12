# 小米蓝牙语音遥控器 2 Pro（RC003）键值表

- **采集日期**: 2026-10-08
- **采集环境**: T1 盒子（Armbian noble, 内核 6.12.65-ophub, BlueZ 5.66, hid-generic over uhid）
- **设备**: 小米蓝牙语音遥控器, MAC `C0:5D:39:XX:XX:XX`, VID:PID `2717:32B8`
- **输入节点**: `/dev/input/event2` ("小米蓝牙语音遥控器", ID_BUS=bluetooth)
- **采集方式**: `evtest --grab /dev/input/event2`
- **配对方式**: 长按【直播键】3~5 秒直至指示灯快闪（⚠️ 不是 Home+菜单）
- **配对方案**: Python dbus agent（RegisterAgent + RequestDefaultAgent + 全回调自动确认），见 `bt_agent_pair.py`

## 键值表

| 遥控器按键 | evdev code | KEY 名 | 长按自动重复 |
|---|---|---|---|
| 语音键（麦克风） | 63 | KEY_F5 | 有 |
| 主页键 | 102 | KEY_HOME | - |
| 返回键 | 158 | KEY_BACK | 有 |
| 方向上 | 103 | KEY_UP | - |
| 方向下 | 108 | KEY_DOWN | - |
| 方向左 | 105 | KEY_LEFT | - |
| 方向右 | 106 | KEY_RIGHT | - |
| OK（确定） | 28 | KEY_ENTER | - |
| 音量+ | 115 | KEY_VOLUMEUP | 有（~40ms/次） |
| 音量- | 114 | KEY_VOLUMEDOWN | - |
| 电源键 | 116 | KEY_POWER | -（轻按） |
| 直播键 | 41 | KEY_GRAVE | 有 |
| 菜单键 | 127 | KEY_COMPOSE | ✅ 已实测（2026-10-08 16:52，T1 回连验证） |

**共 13 键**（与 MiRemoteBridge 项目对 RC003 "all 13 keys" 的描述一致）。

## 关键工程注记

1. **电源键风险（⚠️ 2026-10-08 实锤事故）**：`KEY_POWER` 在 T1 上会被 systemd-logind 默认拦截
   （`HandlePowerKey=poweroff`）。**实锤**：12:31:47 抢连实验期间按下电源键，logind 直接记录
   `Power key pressed short → Powering off` → T1 数秒内关机（一度被误判为「死机/关机链路异常」）。
   如要透传给上层应用（如中继 daemon），**必须**：在 logind 配置中将 `HandlePowerKey=ignore`，
   或由 daemon 用 evdev `EVIOCGRAB` 独占设备后自行处理。**这是 T1 daemon 的硬需求（P0）。**
2. **语音键 = KEY_F5**：HID 层表现为 F5；语音音频流（ATVV）是独立的 GATT 链路，
   需主机侧使能（后续 Mac/Windows 端语音链路任务处理）。
3. MSC_SCAN 原始 HID usage 可见于事件流（例：直播键 usage 0x00070035）。
4. 内核自动重复速率：约 40ms/次（value=2 序列）。

## 交叉验证与资料来源（2026-10-08）

本表已与多个独立来源交叉验证（本机 evtest 实测 + 开源项目实测）：

| 来源 | 内容 | 与实采对照 |
|---|---|---|
| 本机 evtest 实测（本文件） | 12 键 | 基准 |
| [sayall-omarchy issue #1](https://github.com/fan-tastic-z/sayall-omarchy/issues/1) | RC003 (2717:32B8, fw 00A4) evdev 实测：Home=102, Menu=127, TV=41, OK=28, Back=158 | ✅ 完全一致；并补充 **菜单键=KEY_COMPOSE(127)** |
| [MiRemoteBridge](https://www.productcool.com/product/miremotebridge) / [BleRemoteBrideg](https://github.com/QYHHHH/BleRemoteBrideg) | RC003 "all 13 keys" 支持的 ESP32-C3 桥项目 | ✅ 键数吻合（13 键） |

**rc003 全键 = 13 键**：电源、语音、主页、返回、直播、菜单、方向上/下/左/右、OK、音量±。

### 配对方式备注（两说并存）
- **本机实测（用户操作）**：长按【直播键】3~5 秒 → 广播 → 配对成功 ✅
- 部分文档（mi-ao 的 PAIRING.md、sspai 文章）称【菜单键 + HOME 键】同时长按——可能因固件版本而异，以实测为准。

### 相关资料速查（三端方案参考）
- **fanxeon/mi-ao（米遥）**：macOS 全方案（ATVV 语音链路 + 转写 + Codex 输入），含配对/权限/排障完整文档
- **SayAll**：macOS 方案（含 MiRemoteV2ch 虚拟音频驱动，sayall-omarchy 为其 Linux 版）
- **zhaozhuque/MIC-RC003-Windows**：Windows 适配方案
- 上述项目说明 RC003 语音链路（ATVV）在 Mac/Win 均有成熟先例

## 配对修复记录（2026-10-08）

**症状**: bluetoothctl 配对一直失败（三种方式均失败）。
**根因**: bluetoothctl 的 agent 注册不可靠（`Failed to register agent object` / 静默失效），
导致 bluetoothd 在 LESC 确认环节找不到默认 agent（`src/device.c: new_auth(): No agent available`），
自动 Negative Reply → SMP Pairing Failed (Numeric comparison failed)。
**修复**: 改用 Python dbus 直接 RegisterAgent + RequestDefaultAgent（`/org/bluez` 路径的
`org.bluez.AgentManager1`），全部回调自动确认。配对一次通过。
（对应源码: bluez 5.66 `src/device.c device_confirm_passkey`: confirm_hint=1 + bonding!=NULL 本应 auto-accept，唯一前提是存在默认 agent。）
