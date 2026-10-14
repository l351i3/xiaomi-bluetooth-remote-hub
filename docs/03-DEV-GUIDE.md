# 开发文档 —— 架构 · 协议 · 模块 · 流程

> 现网版本：T1 `voice_fwd` v2.9 / `relay_min` v0.13 / `t1_webui` v2.17 / `atvv_service` v1.2 / `presence` v1.0 ｜ Mac `key_bridge` v1.15 / `voice_bridge` v0.9 / `atvv_receiver` v1.2 / `app_switch` v1.2 / `AppPicker` v1.3 / `hs_health` v1.0 / `remotehub_focus.lua` v1.6 / `presence_beater` v2.1 ｜ Win `win_receiver` v1.11 / `win_actions` v1.16 / `win_audio_switch` v1.2 / `win_audio_receiver` v1.0 / `presence_beat` v1.0
>
> （presence 心跳注册制 10-14 全链接线；遥控器电量同日并入；更新于 2026-10-14。）

---

## 一、架构总览

> **斐讯 T1（PHICOMM-T1）** 为中继枢纽（BLE 独占配对 / 协议翻译 / 音频双播）；macOS 与 Windows 为接收端。

```
                       ┌──────────────────────────────────────────────┐
                       │     小米蓝牙遥控器 RC003（BLE HID + ATVV）    │
                       │   13 键 · MIC 语音流（ImaADPCM 16k）         │
                       └───────────────┬──────────────┬───────────────┘
                                       │ BLE（T1 独占配对）
                                       ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  斐讯 T1（Armbian / hci0 = btflow 用户态固件加载链）                       │
│                                                                           │
│  /dev/input/event2 ──┬─► relay_min      v0.13 ──pyatv(Companion)──► ATV4K │
│                      │        （target=atv 时全键 + 语音开 YouTube）       │
│                      │                                                    │
│                      ├─► voice_fwd      v2.9  ─┬─ UDP :8788 "VOICE down/up"
│                      │   （键分类/连发/长按状态机）└─ UDP :8791 "KEY <A> DOWN/UP"
│                      │                              （→ mac 或 win，按 keymap）│
│  MIC(ATVV) ──────────┴─► atvv_service   v1.2  ── UDP :8789 音频流 双播 ──┐ │
│                                                                          │ │
│  t1_webui  v2.17  :8765（目标切换 + /keymap 配置 + rev 指纹）              │ │
└──────────────────────────────────────────────────────────────────────────┘ │
                                                                             │
        ┌────────────────────────────────────────────┬───────────────────────┘
        ▼                                            ▼
┌───────────────────────────────┐    ┌────────────────────────────────────────┐
│ macOS（本机）                 │    │ Windows（Win11）                       │
│                               │    │                                        │
│ key_bridge v1.15 :8791        │    │ win_receiver v1.11 :8791               │
│   └─ CGPost serve 常驻注入    │    │   ├─ win_actions v1.16（扩展动作库）   │
│   └─ app_switch v1.2 /        │    │   ├─ win_audio_switch v1.2（麦克风切换）│
│      AppPicker v1.3 /         │    │   └─ 键盘注入（SendInput）             │
│      hammerspoon 焦点子系统   │    │                                        │
│ voice_bridge v0.9 :8788       │    │ win_audio_receiver v1.0 :8789          │
│   └─ 右⌥ 注入 → Chatterfly    │    │   └─ CABLE Input → 微信输入法          │
│ atvv_receiver v1.2 :8789      │    │                                        │
│   └─ 高通+AGC → BlackHole     │    │ 计划任务自启（%USERPROFILE%\remotehub-win\）│
│ hs_health v1.0（每小时巡检）  │    │                                        │
│ launchd ×6 常驻               │    │                                        │
└───────────────────────────────┘    └────────────────────────────────────────┘
```

**数据总线 = 四条 UDP + 一条 HTTP**：

| 通道 | 端口 | 方向 | 载荷 |
|---|---|---|---|
| 语音指令 | UDP 8788 | T1 → Mac | `VOICE down` / `VOICE up` |
| 按键 | UDP 8791 | T1 → Mac / Win | `KEY <动作> DOWN` / `KEY <动作> UP` |
| 语音流 | UDP 8789 | T1 → Mac + Win（双播） | RC003 音频包（ImaADPCM 解码前） |
| 网页台/API | TCP 8765 | 浏览器 → T1 | 目标切换 + keymap 读写 |
| 在线心跳 | UDP 8790 | Mac / Win / ATV → T1 | `PRESENCE <role> <svc> <port>` → `PRESENCE-ACK` |

---

## 二、协议参考

### 2.1 按键协议（T1 → 接收端，UDP :8791）

```
KEY <ACTION> DOWN      ← 动作触发（单击/长按/连发的每一次都以此形式发出）
KEY <ACTION> UP        ← 配对释放（长按触发后松开）或普通键抬起
```

- **配对纪律**：`voice_fwd` 保证 DOWN/UP 成对；接收端对 UP 的处置按动作类型（多数动作仅 DOWN 触发、UP 忽略；`MOUSE:MOVE/SCROLL` 例外——UP 是 hold 语义的刹车）；
- **动作取值**：基础键 `ENTER/ESC/TAB/SPACE/BACKSPACE/UP/DOWN/LEFT/RIGHT/PAGEUP/PAGEDOWN`；扩展动作 `CLICK / FOCUS_INPUT / APP:* / APP:CLOSE / URL:<网址> / RUN:<命令>`；鼠标动作 `MOUSE:MOVE:UP|DOWN|LEFT|RIGHT` / `MOUSE:SCROLL:UP|DOWN` / `MOUSE:LCLICK` / `MOUSE:RCLICK` / `MOUSE:MODE:ON|OFF`（v2.5/v2.6；由 T1 模式层产生——`MOUSE:TOGGLE`/`MOUSE:OFF` 是本地动作不转发；`MODE:*` = 模式切换时的接收端 HUD 提示；v2.8 起模式内单按 #41 改为放行聚焦、不再发提示）；设备切换 `TARGET:SWITCH:ATV|MAC|WIN`（v2.7/v1.14——电源键连击产生，仅 DOWN，接收端弹「🎯 已切到 X」HUD；切到 atv 时提示发往旧目标端）。

### 2.2 语音指令（T1 → Mac，UDP :8788）

```
VOICE down   ← 按住语音键
VOICE up     ← 松开（提交）
```

### 2.3 语音流（T1 → Mac+Win，UDP :8789）

- RC003 的 ATVV 流；接收端做 **ImaADPCM 解码 → 16k→设备采样率 → 80Hz 高通 → AGC** → 写虚拟声卡；
- AGC 上限 24（小声识别增强，实测调优值）。

### 2.4 keymap v2（`keymap.json`，三端共享）

```json
{
  "version": 2,
  "hold_threshold": 0.6,      // 长按判定阈值（秒）
  "double_window": 0.3,       // 双击窗口（预留，当前未启用）
  "targets": {
    "atv": { "keys": { "28": { "label":"OK", "single":"select", "long":null,
                               "repeat":false, "locked":false, "note":"…" } } },
    "mac": { "keys": { … } },
    "win": { "keys": { … } }
  }
}
```

- 键 = 遥控器 evdev code（`28`=OK、`102`=主页、`158`=返回、`103/108/105/106`=方向、`114/115`=音量、`116`=电源、`41`=直播、`127`=菜单、`63`=语音**锁定**）；
- 每键四字段：`single` / `double`（当前全部 null）/ `long` / `repeat`；`long` 还接受哨兵 `"__REPEAT__"`（UI 的「⟳ 按住连发」）；`locked=true` 的键 UI 禁改（语音键）；
- 校验端（t1_webui）强制 `double=null`、long 与 repeat 互斥。

### 2.5 网页 API（t1_webui :8765）

| 方法/路径 | 说明 |
|---|---|
| `GET /api/keymap` | 返回 `{cfg, rev, choices, order, repeat_opt}`（rev = 配置指纹前 12 位） |
| `POST /api/keymap` | 写配置；`rev` 不符/缺失 → **409 拒写**（防旧页面回写） |
| `POST /api/keymap/reset` | 用 `keymap.default.json` 恢复默认 |
| `GET /api/remote` | 遥控器电量（v2.17）：`{available, connected, percent}`（busctl 只读 BlueZ 缓存；未连接/未上报 → 降级 `available=false`） |

---

### 2.6 presence 心跳（Mac / Win / ATV → T1，UDP :8790）

```
Mac/Win/ATV ──"PRESENCE <role> <svc> <port>"（每 2s）──► T1 presence 守护
            ◄──────────────  "PRESENCE-ACK"  ──────────────
```

- **角色**：`mac` / `win` / `atv`（固定三值；非法 role/svc 忽略且不回 ACK）；svc 明细示例：
  `voice:8788 / key:8791 / audio:8789`（Mac/Win）、`relay:0`（ATV）。
- **节奏**：启动即拍（首拍 = T1 侧 IP 学习源）→ 2s/拍；无 ACK 退避 2→4→8→15s（封顶）；
  收到 ACK 复位。**T1 侧 6s（3 拍）无心跳判离线**。
- **状态消费**：读端读 `state/presence.json`（30s 写盘快照；90s 过期 → `unknown` 降级 =
  维持旧行为）；投递闸门 = 设备离线跳过 + 心跳学习 IP 优先于静态常量（**去硬编码**）。
- **自动切换**：当前目标离线 ≥12s 且有在线设备 → 切到优先级最高者（`mac>win>atv`）并写
  `voice_target`；原目标连续在线 ≥10s → 自动切回；全离线不切（日常主用手动电源连击）。
- **单代理形态**（10-14 定）：每设备一个心跳源代报全部 svc（Mac=`presence_beater` /
  Win=`win_receiver` / T1=`relay_min` 报 atv）——设备级粒度，svc 明细为观测字段。

---

## 三、模块说明

### 3.1 T1 端

| 模块 | 关键设计 |
|---|---|
| `voice_fwd.py` v2.9 | ① 键分类：语音键→8788 / 普通键→8791；② **自建连发**：遥控器固件不发 `EV_REP`，`repeat=true` 的键在满 0.5s 后由本进程每 0.12s 补发 DOWN；③ **长按状态机**：`pending_long`/`long_fired` 严格互斥——未满 0.6s 松开→发 single（补 down+up）；满阈值→发 long；触发 long 后松开→补发 long 的 UP；④ 配对纪律；⑤ WIN_IP（WINDOWS_IP）双目标转发；⑥ **鼠标模式状态机**（v2.5/v2.6：长按 #41 开关 + `MOUSE:MODE:*` HUD 提示 + 电源/主页放行透传 + 0.4s 保活；**v2.8：模式内短按 #41 放行聚焦**——直发实时目标，不再吸收/提示）；⑦ **电源连击切换设备**（v2.7：keymap `#116.single=TARGET:SWITCH` 为启用闸门——1/2/3 击=ATV/Mac/Win，窗 0.5s、第 3 击立即提交、长按仍走 APP:CLOSE；提交后 0.5s 吞键期 + 切 atv 强退鼠标模式）；⑧ **presence 投递闸门**（v2.9：`_send_to()`——设备离线跳过 + 心跳学习 IP 优先 + 无地址 60s 节流丢弃） |
| `relay_min.py` v0.13 | RC003 → pyatv 中继（Companion 协议）；配置外置（keymap atv 份）；语音键 v0.12 起**配置驱动**（走通用分派；默认一键开 YouTube，网页可自由改绑，清空=关闭）；`play_pause` 须 HID 直发 `(12,0xCD)`（pyatv 通用路径"假成功"）；v0.11 电源连击（atv 目标下）：1 击=电视电源 / 2 击=切 mac / 3 击=切 win（切走时写 `voice_target` + 向旧目标端发 HUD）；v0.13：presence 闸门（HUD 地址动态化 + 离线跳过）+ ATV 心跳上报 |
| `t1_webui.py` v2.17 | 标准库 http.server；`/`=三按钮；`/keymap`=三 tab 配置；rev 指纹防回写；改配置即写 `keymap.json`（voice_fwd 热读，无需重启）；动作选项含 `MOUSE:TOGGLE`（鼠标模式开关，v2.13）与 `TARGET:SWITCH`（电源连击切设备，v2.14）；atv 语音键 #63 v2.15 已解锁（默认「打开 YouTube」，可改绑）；v2.16 主页设备状态条（`GET /api/presence` 只读消费 + 降级安全）；v2.17 遥控器电量（`GET /api/remote`，busctl 只读 BlueZ Battery1 缓存 + 降级安全） |
| `atvv_service.py` v1.2 | RC003 语音流 → UDP 双播（Mac + Windows）；失败隔离（一路不通不影响另一路）；与按键 target 解耦（音频恒双播）；v1.2：presence 闸门（`_dests()` 动态解析——离线跳过 + 边沿日志） |
| `presence.py` v1.0 | 设备在线注册表（UDP :8790 守护）：心跳接收 / ACK / 6s 判离线 / 优先级自动切换 / 30s 原子落盘 `state/presence.json`；读端 `StateView`（0.5s 节流 + mtime 缓存）供三服务热路径消费 |

### 3.2 Mac 端

| 模块 | 关键设计 |
|---|---|
| `key_bridge.py` v1.15 | 动作分发中枢：基础键→CGPost 注入；`APP:*`→`app_switch` 工具；`APP:PICK`→`AppPicker.app`；`FOCUS_INPUT/CLICK`→Hammerspoon（`hs -c`）；`URL:`→`open`；`RUN:`→`/bin/sh`。**注入模型 = CGPost serve 常驻**（`/tmp/cgpost.sock`，零启动开销）+ 15s 无响应熔断回退 submit 一次性 job。各动作独立防抖（见 §四）。 **鼠标模式**（v1.13/v1.14）：`MOUSE:*` 信道（MOVE/SCROLL/LCLICK/RCLICK → lua 滑行执行器）+ `MOUSE:MODE:*` → `mouseHud()` 浮层；**v1.15**：`TARGET:SWITCH:*` 设备切换 HUD（→ lua v1.6 `switchHud()`，复用鼠标串行 worker） |
| `voice_bridge.py` v0.9 | 纯长按语义；FS 闭环（丢事件自动补发）；注入=右⌥（61）→ Chatterfly 触发语音输入 |
| `atvv_receiver.py` v1.2 | 语音流落地：80Hz 高通 + AGC 上限 24 + 限幅 → BlackHole 2ch |
| `app_switch.swift` v1.2 | `cycle`（全应用轮询：冻结快照+前台校验）、`toggle`、`next`、`pick`、`close`（NSRunningApplication.terminate() 优雅退出；Finder 保护） |
| `AppPicker.swift` v1.3 | 常驻 Tk 风格 NSWindow 网格选择器：6 列 / 初始第 2 项 / 环绕 / 10s 自动取消 / 方向导航 / 长名跑马灯；socket `/tmp/apppicker.sock` 接收按键路由 |
| `hs_health.py` v1.0 | 12 项检查（App/CLI/进程/IPC/AX/Lua/初始化/冒烟/各服务）+ 自动修复 + 通知 |
| `remotehub_focus.lua` v1.6 | `focusInput()` 六段（窗口修复→**前台提升 v1.6**→缓存→坐标网格→树遍历→设焦点读回；**v1.5** 全 miss 兜底点击〔**v1.6** 改「距窗底 105px」——0.92 比例实测偏低〕+ 光标恢复，报 `NOEDIT+CLICK@x,y front=ok|fail`）；`clickFocused()` 四段（AXPress→直接子→向上≤6→坐标兜底）；v1.2 鼠标滑行执行器（60Hz 积分 + 1.2s 看门狗）；v1.3 `mouseHud()` 模式切换浮层；v1.4 `switchHud()` 设备切换浮层（「🎯 已切到 X」） |
| `presence_beater.sh` v2.1 | 设备心跳代理（Mac 整机 → T1 :8790）：bash 循环 + `/usr/bin/nc` 后台并发（2s 节拍 + 60s ACK 深探）——**macOS 27 本地网络隐私下解释器出站被拦的绕行形态**（见 §4.12）；LaunchAgent 常驻。python 版 `presence_beater.py` 仅留档 |

### 3.3 Windows 端（Windows）

| 模块 | 关键设计 |
|---|---|
| `win_receiver.py` v1.11 | UDP 接收 + 防抖 + 异步日志（队列+句柄常开，杜绝收包线程写盘）；语音键=**先切麦克风后注入**；`picker_route()` 选择器期间按键直连路由（50ms 消费，不依赖焦点）；防抖首击修复（None 哨兵）；v1.8 鼠标模式（`MOUSE:*` → `win_actions.mouse_control` + 模式 HUD）；v1.9 **复用 win_actions 的 INPUT 类**（全进程单类，修跨模块 SendInput 冲突）；v1.10 `TARGET:SWITCH:*` 同 MOUSE:* 路由（设备切换 HUD）；v1.11 presence 心跳（`presence_beat` 单代理报 voice/key/audio） |
| `win_actions.py` v1.16 | 扩展动作库（3373 行）：CLICK 四段 / FOCUS_INPUT 五阶段（均移植自 Mac 对应件；**v1.15 NOEDIT 兜底点击 + `app=` 观测字段**）/ APP:* 全家 / URL: / RUN: / `APP:CLOSE`（WM_CLOSE 优雅关闭：`SendMessageTimeoutW(SMTO_ABORTIFHUNG)` + `close_poll` 轮询 ≤2s + UWP 真身窗口定位）；选择器 v2.6（网格导航 + UWP Shell 图标 + 光学尺寸归一 + 长名滚动）；v1.11/v1.12 **MouseGlide 滑行引擎**（60Hz 积分、速度自 0 线性加速、`stop()/_sweep()` 事件驱动清零、模式 HUD）；v1.13 INPUT 类**唯一定义源**（跨模块 SendInput 冲突修复 + `MOUSE:REPORT` 探针）；v1.14 `TARGET:SWITCH:*` 设备切换 HUD（复用 v1.12 HUD 体系——`_hud_open_text` 抽取共用）；v1.16 `do_app_activate` 观测日志（`front=… -> key ok=…`／not-running 路径） |
| `win_audio_switch.py` v1.2 | 默认录音设备按需切换（三 role 同切；松开 2s 恢复；gen 双重检查；fail-open） |
| `win_audio_receiver.py` v1.0 | 语音流 → CABLE Input（设备采样率自适应） |

---

## 四、关键设计决策（为什么这样做）

### 4.1 单击/长按严格互斥（voice_fwd v2.3）
`pending_long`/`long_fired` 状态机：有 long 的键按下不即时发；满 0.6s 才发 long；未满阈值松开补发 single。**保证一次按压永远只出一个语义**（不会"又发 single 又发 long"）。双击（double）字段在当前实现中**未启用**（校验端强制置空）。

### 4.2 防抖表（接收端）

| 动作 | 防抖 | 理由 |
|---|---|---|
| 基础键 | 无（UP 配对语义） | 键盘天然重复 |
| `CLICK` / `FOCUS_INPUT` | 0.6s | 防连点误触 |
| `APP:*`（切换类） | 0.35s | 快速连按循环切换需要 |
| **`APP:CLOSE`** | **2.0s** | 关闭后前台必变，防重复包连关第二个应用 |
| `URL:` | per-url 0.6s | 同一网址短时只开一次 |
| `RUN:` | per-cmd 0.6s | 防连跑 |

### 4.3 自建连发（T1）
遥控器（bluez-hog-device）capabilities 为空、不发 `EV_REP`——内核连发路径从不存在。改为 `voice_fwd` 自己 tick 补发（与 `val=2` 路径共用节流防双发）。

### 4.4 Mac 注入模型（CGPost serve）
历史教训：每次注入 spawn 一个新进程会被 TCC 空授权丢弃（静默）。终局 = **serve 常驻进程**（CGPost.app 已获授权，路径+cdhash 冻结）长期持有；`key_bridge` 经 UNIX socket 请求注入；serve 死亡 15s 熔断自动回退「submit 一次性 job」模式。**UNIX dgram 客户端必须显式 bind**（否则收不到回包）。

### 4.5 UWP 图标与关闭（Windows）
- UWP 应用窗口宿主 = `ApplicationFrameHost` → 需 `EnumChildWindows` 取真身 PID/HWND；
- 图标取真图：`SHGetPropertyStoreForWindow(PKEY_AppUserModel_ID)` → `shell:AppsFolder` → `IShellItemImageFactory.GetImage`；**GUID 必须一字不差**：`IID_IShellItemImageFactory = {bcc18b79-ba16-442f-80c4-8a59c30c463b}`（错一位 `bcc38b79` → `E_NOINTERFACE` → 静默回退，曾 100% 失败）；COM 全手写 vtable（`Release=vt[2] / GetImage=vt[3] / GetValue=vt[5]`）；
- 关闭 = `WM_CLOSE`（优雅，等价点 X）而非 Terminate；

### 4.6 音频链增益链
RC003 流两坑：**直流偏置**（最高满幅 50%）+ 有效电平低（0.01–0.06 rms）。故接收端先高通再 AGC（上限 24）。Chatterfly 侧另有过坑：**丢弃 ≲3s 间隔的重复注入**（FS 闭环补发解决）。

### 4.7 鼠标模式（滑行引擎，双端逐条对齐）
- 分层：**状态机在 T1**（`voice_fwd.MouseMode`——模式开/关、键映射、OK 长短按、0.4s 保活；纯逻辑离线可测）；**执行在接收端**（Mac lua / Win MouseGlide）；
- 传的是**意图**不是坐标：`MOUSE:MOVE:UP DOWN`（按住语义）——接收端自己按 60Hz 积分滑行（加速 700px/s² / 上限 1600px/s，**速度自 0 线性加速**：轻点=精准微调、按住=横扫）；
- **保活 + 看门狗**（掉线安全带的双子机制）：T1 每 0.4s 重发 DOWN 刷新接收端时间戳；接收端 **1.2s 无刷新即自动移除方向并刹车**——UDP 丢包/蓝牙断连/进程崩溃任何一个环节断流，光标都会在 1.2s 内停下；
- 不做防抖：重复 DOWN = 保活（幂等）；UP = 配对刹车（不可去重）；对向方向同时按住 → 矢量相消（净位移 0）；
- 斜向 √2 速（方向矢量**不归一化**——与 lua 实装逐条对齐）；Windows 端 WHEEL_DELTA=120/notch × 10 notch/s ≈ Mac 900px/s 观感；
- **v2.6 实测反馈修复轮**（三端四件）：① 模式切换 / 模式内单按 #41 → 目标端 `MOUSE:MODE:ON|OFF` 弹 HUD（Mac `hs.alert` / Win Tk 浮层，1.1s 自动消失——治「按了不知道生效没有」）；② 模式内**电源 116 / 主页 102 放行**（`handle()` 返回 None → 转正常键路径，含长按机制，行为与模式外一致——治「没法跳走打开应用」）；③ Windows 滑行速度清零（`stop()/_sweep()` 事件驱动——修「多次按压速度跨按压累积、没法微调」）。

### 4.8 跨模块 ctypes 单类铁律（Windows SendInput，v1.13 元凶级教训）
`ctypes.windll.user32` 是**进程级共享对象**：win_receiver 与 win_actions 曾各自定义 INPUT 结构类、各自设 `SendInput.argtypes`（后加载者覆盖前者）→ 跨类指针被 ctypes 类型检查拒绝（`TypeError: expected LP_INPUT instance…`）→ 又被 `except` 吞掉 → 鼠标点击/滚轮**静默全灭**（键盘正常——调用方与最终 argtypes 恰为同型）。铁律：**全进程单一结构类**（`win_actions` 定义、`win_receiver` 复用；离线兜底分支字段逐项一致）；**禁止静默吞异常**（关键 except 一律 `_logv` 落盘）；`MOUSE:REPORT` 的 `input_class_module` 字段为常驻指纹（健康值 = `win_actions`）。

### 4.9 电源键连击切换设备（v2.7/v0.11 —— 网关式启用 + 双侧各挂计数器）

- **动机**：用户日常切设备要走网页台（开网页点按钮），嫌麻烦 → 电源键连击直切：**1 击=ATV / 2 击=Mac / 3 击=Win**。
- **★ 网关式启用**：以 keymap `#116.single == "TARGET:SWITCH"` 作为**连击层启用闸门**（每事件热读）——
  改回任意具体动作即退回普通键语义，**零代码改动**；旧短按行为随时可恢复（不用时改下拉即可）。
- **双侧各挂计数器**（为什么两份实现）：`voice_fwd` 只在 target≠atv 处理按键、`relay_min` 只在
  target=atv 处理 → 要在 ATV 状态下也能切走，两侧必须各有一套连击检测。算法（两端同规）：
  窗口 0.5s（自最后一次 DOWN 起算）· 第 3 击**按下立即提交** · 其余窗口期满且当前未按住才提交 ·
  长按 ≥0.6s 中止计数走 long 路径（=APP:CLOSE）不误发 · 提交后 **0.5s 吞键期**（防手抖多敲一记）。
- **语义不对称（有意）**：atv 目标下 1 击=`__POWER__`（电视电源开关，保持现行为）、双击/三击=切走、
  无长按语义；计数期间离开 atv → 提交丢弃（防串台）。
- **切换动作**（T1 本地）：写 `voice_target` 文件（`voice_fwd`/`relay_min` 按键时热读——零重启切换）
  + 向一端发 `KEY TARGET:SWITCH:<X> DOWN` HUD。发送规则：**切到 atv 发旧目标端**（mac/win 必见提示，
  否则 ATV 无接收端 = 零反馈）、切到 mac/win 发新目标端；切到 atv 时同时强制退出鼠标模式（ATV 无鼠标通道）。
- **HUD 多端**：Mac=lua v1.6 `switchHud()`（hs.alert 浮层）/ Win=win_actions v1.15（复用模式 HUD 的
  Tk 浮层体系，`_hud_open_text` 抽取共用）——文案统一「🎯 已切到 ATV / macOS / Windows」，1.1s 消失。

### 4.10 FOCUS_INPUT 聚焦（v2.8 / lua v1.6 / win_actions v1.15 —— 模式内放行 + 前台提升 + NOEDIT 兜底点击）

- **链路**：#41 短按 → T1 `voice_fwd` 按 keymap `#41.single=FOCUS_INPUT` 转发（仅 DOWN 有效、
  0.6s 防抖）→ Mac `key_bridge` → lua `focusInput()` / Win `win_receiver` → `win_actions.do_focus_input()`。
- **v2.8 模式内放行**：鼠标模式内短按 #41 直发实时目标（旧版「吸收 + 弹提示」被用户判定为「不灵」）；
  长按仍走 `MOUSE:TOGGLE`（kf 长按机制，与模式外一致）；喂 kf 的目标用实时 target（旧版固定 "mac"）。
- **★ v1.6 前置：窗口遮挡**（10-14 深挖，实机实证）：目标 app 窗口**未必在 z 序最顶**（现场 12 窗
  堆叠，抖音直播窗压住 WorkBuddy）→ 合成点击/键盘全被顶层窗口截胡——**这是「全策略跑通但仍不灵」的
  元凶之一，也是任何「聚焦/合成输入」类问题的普适前置项**。lua v1.6 新增 `ensureFrontApp()`：
  `activate` + z 序校验（≤3 次重试），**放在窗口修复（含 unmin）之后**（最小化窗不在 z 序里，先校验
  会误判）。
- **六段策略**（两端同构；Mac v1.6）：① 窗口聚焦修复 → ② **前台提升（v1.6, `ensureFrontApp`）** →
  ③ 缓存点（曾命中的窗口比例坐标）→ ④ 坐标网格（`GRID_X 6 列 × GRID_Y 12 行`，底部输入区优先）→
  ⑤ 树遍历（首个 Edit/ComboBox）→ ⑥ SetFocus 读回。
- **v1.5/v1.15 NOEDIT 兜底点击**：六段全败（微信等无 AX/UIA 内容层应用）→ 点击**窗口底部中央**，
  点击后恢复用户鼠标位置（Mac `hs.mouse.absolutePosition` 存还 / Win `_click_preserve_cursor`
  存还）；返回 `NOEDIT+CLICK@x,y`。Win 侧策略函数加 `click_at` 注入参数（None=旧行为，测试打桩）；
  结果串追加 `app=<exe_key>` 观测字段。
  - **★ v1.6 坐标修正**：旧 `(0.5, 0.92)` 比例坐标实测落在**输入框下方按钮行**（偏过低）→ 改为
    **距窗底固定 105px**（WorkBuddy 输入框文字行实测标定；聊天类亦大致同区间；固定像素距底对窗口
    高度变化比比例坐标稳）。
  - **★ v1.6 失败保护**：前台提升失败（`front=fail`）时**跳过点击**——疑似弹窗/异常遮挡，盲目点击
    恐误中他人按钮（如授权弹窗）；如实回报 `front=fail-skip` 供诊断。成功则为 `front=ok`。
- **已知代价**：若窗口底部没有输入框，兜底点击可能落在内容区（选中/打开链接风险低概率、低危害）；
  仅作用在用户主动按 #41 的时刻。

---

### 4.11 presence 心跳注册制（去硬编码 IP + 体面断开/优雅连上；10-14 全链接线）

- **两个需求一套机制**：① **体面断开**——设备离网时投递端「离线跳过 + 明确日志」（消灭
  「假已发送」：日志照显『已发送』实则无人收）；② **去硬编码**——投递地址用心跳学习的 IP
  （DHCP 变更自动跟上），静态常量降级为 fallback。
- **形态**：每设备**单代理**代报全部 svc；设备级闸门（`device_state(role)`），svc 明细仅观测。
- **降级纪律**：`presence.json` 缺失/损坏/过期（>90s）→ 读端按 `unknown` → **维持旧行为
  照旧投递**，永不阻塞（presence 停摆 = 退化为接线前的静态行为）。
- **快照语义**：`presence.json` 是 **30s 写盘**的状态快照（原子替换）——外部观察者读到的
  `last_seen` 含最多 ~30s 陈旧度；判断「实时性」以 presence.log 事件为准。
- **自动切换**（`mac>win>atv` 优先级 + 12s/10s 确认窗）保留为纯逻辑能力（`Presence` 类，
  注入时钟离线可测）。

### 4.12 ★ macOS 27 本地网络隐私 —— launchd 上下文解释器出站被拦（10-14 实证）

- **现象**：launchd（LaunchAgent / `launchctl submit`）上下文中，所有**解释器**（含系统
  `/usr/bin/python3`）的 LAN 出站被系统拦截——UDP 静默丢 / TCP `OSError(65 No route to
  host)`，而 `route get` / `ping` 全正常（错误信息指向错误的层）。
- **豁免名单**（实测）：系统签名网络工具 `/usr/bin/nc`（UDP 双向含回程）与 `/usr/bin/curl`
  放行——依据 Apple **TN3179**（Local Network Privacy：系统二进制获自动放行）。
- **对策**：需在 launchd 下持续发 LAN 包的场景，用「**bash 循环 + 系统网络工具**」形态
  （实作 = `presence_beater.sh`：`nc` 后台扇出 + 固定节拍 + 周期 ACK 深探）。
- **排障要点**：① 症状层与网络层分离（route/ping 正常时勿再查路由）；② 判别法 = 同一目标
  分别从「shell 会话树」与「launchd 上下文」发——前者通后者不通即命中本坑；③ macOS
  `nc -w` **只接受整数**（小数 = 参数错误 exit 1 且静默不发包）。

---

## 五、开发环境

| 端 | 环境 |
|---|---|
| T1 | Armbian（6.12.65-ophub 内核）/ `/usr/bin/python3` / pyatv 在 `/opt/pyatv` venv |
| Mac | python 3.13（`.workbuddy/binaries/.../3.13.12`）+ venv（`envs/default`）；`swiftc` 编译 Swift 件（`-O -swift-version 5`，输出名别叫 `AppPicker`）；Hammerspoon；node（JS 测试用 22.x） |
| Win | Python 3.13（`pythonw` 跑接收端）；uiautomation 须在 worker 线程首初始化 |
| 版本控制 | 本机 git（Apple Git 2.54）——发布树均为普通 git 仓库（公开树附 `.githooks` 泄漏门禁）。**发布镜像三库已上线**：公开库 `l351i3/phicomm-t1-system-fix` 与 `l351i3/xiaomi-bluetooth-remote-hub`；另有私有库 1 个（上游设备缺陷报告，未公开）；源树 → 导出流水线 → 发布树单向流（见《05》） |

**约定**：所有 py 生产件**零第三方依赖**（T1/Mac/部分 Win 件纯标准库；Win 扩展动作用 uiautomation/pywin32 在目标机装好）。

---

## 六、测试体系（14 套）

```bash
# Mac/T1 侧（在 remote-hub/ 下）
python3 relay_logic_test.py            # 31（v0.11 连击 + v0.12 语音键配置驱动）
python3 key_fwd_logic_test.py          # 165（鼠标模式 + v2.7 连击 + v2.8 模式内 #41 放行 + v2.9 presence 闸门）
python3 webui_v2_test.py               # 121（v2.15 语音键解锁 + v2.16 设备状态条 + v2.17 遥控器电量）
/Users/username/.workbuddy/binaries/node/versions/22.22.2-6/bin/node webui_js_test.mjs   # 42
python3 apppicker_grid_test.py         # 33
python3 apppicker_name_test.py         # 16
python3 close_app_test.py              # 18
python3 presence_test.py               # 62 （v1.0 心跳注册制, 注入时钟）
python3 mouse_channel_test.py          # 24（实机, 需 Hammerspoon —— 鼠标执行器 + 模式 HUD + v1.4 switchHud）

# Win 侧（在 windows/ 下；本机双解释器 3.9 + 3.13 均须全过）
python3 offline_test.py                # 22
python3 audio_offline_test.py          # 26
python3 actions_offline_test.py        # 459  ★ 含"源码约定守护"（如断言禁用 TerminateProcess）+ 滑行引擎 + §20 类统一 + 聚焦兜底 F2-F4
python3 audio_switch_offline_test.py   # 74
python3 receiver_smoke_test.py         # 28
```

**测试哲学**：
- 纯逻辑注入打桩（时钟/网络/IO 全部可注入）→ 无网无设备即可全跑；
- **源码约定守护**：把"架构决策"写成断言（如 GUID 正确性、互斥语义、禁用 API 清单），防回归时被悄悄改坏；
- 双解释器跑（3.9 + 3.13）：兼容性双保险。

---

## 七、部署与升级流程

### 7.1 三端部署拓扑
| 端 | 部署路径 | 自启机制 |
|---|---|---|
| T1 | `/root/remote-hub/` + `/etc/systemd/system/` | systemd（8 服务 enabled） |
| Mac | 工作区 `remote-hub/`（launchd WorkingDirectory 指向） | launchd ×6（5 个 KeepAlive） |
| Win | `%USERPROFILE%\remotehub-win\` | 计划任务 |

### 7.2 标准升级流程（施工单模式）
1. 本地改代码 → 编辑脚本定式（备份 `.bak-<时间>-preV*` + 逐处 `count==1` 断言 + `py_compile -W error::SyntaxWarning` + sha256）；
2. 跑离线测试全绿；
3. 分发：scp/T1:8000 → 目标端；**三重核对**（scp 后双端 sha256 一致 + HTTP 取回验证）；
4. 目标端执行施工单（`TASK-*.md`：施工步骤 + 验收清单 + 回滚指引）；
5. 回传验收报告 + 任何 `*.patched` **必回收合入上游**（防下轮全量分发覆盖）。

### 7.3 分发服务
- `8000`：T1 静态分发（根 `/root/remote-hub/windows/`，绑 T1_IP）；非常驻，用时重启；
- `8001`：`upload_recv.py` 回传接收（存 `/root/remote-hub/inbox/`）。
- **恢复命令**（T1，nohup 即起即用；T1 重启后需重跑）：
  ```sh
  cd /root/remote-hub/windows && nohup python3 -u -m http.server 8000 --bind T1_IP >> /tmp/dist-8000.log 2>&1 < /dev/null &
  cd /root/remote-hub && nohup python3 -u upload_recv.py >> /tmp/upload-8001.log 2>&1 < /dev/null &
  ```
- **远程触发升级通道**（2026-10-13 实证）：Windows 的 `win_receiver` 常驻时，可从任意端向其
  `:8791` 发 `KEY RUN:<相对路径>.bat DOWN`（如 `Downloads\update-win-receiver.bat`，**值不含空格**）
  ——执行 `cmd (cwd=~)`，配合 8000 访问日志（`/tmp/dist-8000.log` 见目标机 GET 记录）+ PONG 连续探测
  （重启窗口即升级证据），实现「零到场」远程升级触发与观测（2026-10-13 鼠标模式部署首次使用）。
- **状态取证通道**（同轮实证）：`KEY MOUSE:REPORT DOWN` → 目标机生成 `state/mouse-report.json`
  （SendInput 探针 / 输入类归属 / DPI / UIA / 前台窗口等）；随后 RUN 重跑 update 脚本（幂等，`[7/7]` 步）
  → 报告经 8001 自动回传 T1 `inbox/`。

---

## 八、协作纪律（血泪版）

1. **开工先同步 inbox**：上轮 Windows 的回传（报告 + patched + 截图）先取回处理；
2. **`*.patched` 必回收**：曾因未回收，下一轮全量分发把目标端补丁覆盖丢失（返工）——回收还必须**连测试件对账**（有一次 GUID 补丁只在测试件里，测试件没同步导致差点再踩）；
3. **编辑脚本定式**（见 7.2）——所有改动留痕可追；
4. **改动键位 ≠ 重启**：keymap 热重载；但**部署新 webui 后必须提醒用户刷新页面**（防旧页面回写，rev 指纹兜底 409）；
5. **用户约定**：键位「对齐 mac」为既定方针（win 份与 mac 份 diff 必须 = 0）——待补项直接照 mac 执行，不要逐项询问。

---

## 九、已知限制与坑清单

| 坑 | 说明 |
|---|---|
| BSD grep | `grep 'A\|B'` 静默返回空——**用 `grep -E 'A|B'` 或内置工具** |
| WorkBuddy 沙箱 | `sudo` 硬拦（用 `osascript … with administrator privileges`）；`launchctl bootstrap` 失败（走 SSH 本机会话）；跨进程退出请求会被沙箱拦截（自测≠产品问题，走真实链路验证） |
| launchd 版本坑 | `launchctl submit` 从此环境"静默不生效"；`kickstart` 可用 |
| BMP 行序 | `biHeight<0`=top-down（勿翻）、`>0`=bottom-up（需翻）——AppPicker 灰调曾因解析错定错色 |
| T1 无 RTC | 日志时间戳会倒错（fake-hwclock），考古用 uptime 反推 |
| T1 硬约束 | **禁止高频反复开关 tty**（会内核卡死 + watchdog 复位循环 + 关机链路异常）；设备实验必须 dry-run→独立看护→断网预案 |
| Electron 焦点元素 | 不响应合成回车——用 `CLICK`（AXPress）；微信=AX 黑洞 |
| pyatv play_pause | pyatv 通用路径"假成功"——须 HID 直发 `(12,0xCD)` |
| Chatterfly | 触发键 = 右⌥(61)；**静默丢弃 ≲3s 间隔注入**（voice_bridge 有 FS 闭环补发） |
| Win CoInit | comtypes≥1.4 的 `CoInitializeEx` 会 TypeError 被吞——改裸 Win32 `ole32.CoInitializeEx(None, 0x0)` |
| T1 服务三件套 | 重启后重拉遥控链路需 `bluetooth + t1bt-bluetooth + t1-evwatch` 三个都起（漏 `bluetooth` 遥控器连不上） |
| macOS 27 本地网络隐私 | launchd 上下文**解释器出站被拦**（UDP 静默丢 / `EHOSTUNREACH`；route/ping 正常）——系统二进制 `nc`/`curl` 豁免（TN3179）；持续发 LAN 包用「bash + 系统工具」形态（见 §4.12） |
| macOS nc 的 -w | **只接受整数**（`-w 0.5` = 参数错误 exit 1 且静默不发包——「秒退」易误判为发送成功）；UDP 发包用「后台扇出 + 固定节拍」而非前台等待 |
