# 开发文档 —— 架构 · 协议 · 模块 · 流程

> 现网版本：T1 `voice_fwd` v2.3 / `relay_min` v0.10 / `t1_webui` v2.11 / `atvv_service` v1.1 ｜ Mac `key_bridge` v1.12 / `voice_bridge` v0.9 / `atvv_receiver` v1.2 / `app_switch` v1.2 / `AppPicker` v1.3 / `hs_health` v1.0 ｜ Win `win_receiver` v1.6 / `win_actions` v1.10 / `win_audio_switch` v1.2 / `win_audio_receiver` v1.0

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
│  /dev/input/event2 ──┬─► relay_min      v0.10 ──pyatv(Companion)──► ATV4K │
│                      │        （target=atv 时全键 + 语音开 YouTube）       │
│                      │                                                    │
│                      ├─► voice_fwd      v2.3  ─┬─ UDP :8788 "VOICE down/up"
│                      │   （键分类/连发/长按状态机）└─ UDP :8791 "KEY <A> DOWN/UP"
│                      │                              （→ mac 或 win，按 keymap）│
│  MIC(ATVV) ──────────┴─► atvv_service   v1.1  ── UDP :8789 音频流 双播 ──┐ │
│                                                                          │ │
│  t1_webui  v2.11  :8765（目标切换 + /keymap 配置 + rev 指纹）              │ │
└──────────────────────────────────────────────────────────────────────────┘ │
                                                                             │
        ┌────────────────────────────────────────────┬───────────────────────┘
        ▼                                            ▼
┌───────────────────────────────┐    ┌────────────────────────────────────────┐
│ macOS（本机）                 │    │ Windows（Win11）                       │
│                               │    │                                        │
│ key_bridge v1.12 :8791        │    │ win_receiver v1.6 :8791                │
│   └─ CGPost serve 常驻注入    │    │   ├─ win_actions v1.10（扩展动作库）   │
│   └─ app_switch v1.2 /        │    │   ├─ win_audio_switch v1.2（麦克风切换）│
│      AppPicker v1.3 /         │    │   └─ 键盘注入（SendInput）             │
│      hammerspoon 焦点子系统   │    │                                        │
│ voice_bridge v0.9 :8788       │    │ win_audio_receiver v1.0 :8789          │
│   └─ 右⌥ 注入 → Chatterfly    │    │   └─ CABLE Input → 微信输入法          │
│ atvv_receiver v1.2 :8789      │    │                                        │
│   └─ 高通+AGC → BlackHole     │    │ 计划任务自启（%USERPROFILE%\remotehub-win\）│
│ hs_health v1.0（每小时巡检）  │    │                                        │
│ launchd ×5 常驻               │    │                                        │
└───────────────────────────────┘    └────────────────────────────────────────┘
```

**数据总线 = 三条 UDP + 一条 HTTP**：

| 通道 | 端口 | 方向 | 载荷 |
|---|---|---|---|
| 语音指令 | UDP 8788 | T1 → Mac | `VOICE down` / `VOICE up` |
| 按键 | UDP 8791 | T1 → Mac / Win | `KEY <动作> DOWN` / `KEY <动作> UP` |
| 语音流 | UDP 8789 | T1 → Mac + Win（双播） | RC003 音频包（ImaADPCM 解码前） |
| 网页台/API | TCP 8765 | 浏览器 → T1 | 目标切换 + keymap 读写 |

---

## 二、协议参考

### 2.1 按键协议（T1 → 接收端，UDP :8791）

```
KEY <ACTION> DOWN      ← 动作触发（单击/长按/连发的每一次都以此形式发出）
KEY <ACTION> UP        ← 配对释放（长按触发后松开）或普通键抬起
```

- **配对纪律**：`voice_fwd` 保证 DOWN/UP 成对；接收端对 UP 的处置按动作类型（多数动作仅 DOWN 触发、UP 忽略）；
- **动作取值**：基础键 `ENTER/ESC/TAB/SPACE/BACKSPACE/UP/DOWN/LEFT/RIGHT/PAGEUP/PAGEDOWN`；扩展动作 `CLICK / FOCUS_INPUT / APP:* / APP:CLOSE / URL:<网址> / RUN:<命令>`。

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

---

## 三、模块说明

### 3.1 T1 端

| 模块 | 关键设计 |
|---|---|
| `voice_fwd.py` v2.3 | ① 键分类：语音键→8788 / 普通键→8791；② **自建连发**：遥控器固件不发 `EV_REP`，`repeat=true` 的键在满 0.5s 后由本进程每 0.12s 补发 DOWN；③ **长按状态机**：`pending_long`/`long_fired` 严格互斥——未满 0.6s 松开→发 single（补 down+up）；满阈值→发 long；触发 long 后松开→补发 long 的 UP；④ 配对纪律；⑤ WIN_IP（WINDOWS_IP）双目标转发 |
| `relay_min.py` v0.10 | RC003 → pyatv 中继（Companion 协议）；配置外置（keymap atv 份）；语音键在 atv 目标 = 一键开 YouTube；`play_pause` 须 HID 直发 `(12,0xCD)`（pyatv 通用路径"假成功"） |
| `t1_webui.py` v2.11 | 标准库 http.server；`/`=三按钮；`/keymap`=三 tab 配置；rev 指纹防回写；改配置即写 `keymap.json`（voice_fwd 热读，无需重启） |
| `atvv_service.py` v1.1 | RC003 语音流 → UDP 双播（Mac + Windows）；失败隔离（一路不通不影响另一路）；与按键 target 解耦（音频恒双播） |

### 3.2 Mac 端

| 模块 | 关键设计 |
|---|---|
| `key_bridge.py` v1.12 | 动作分发中枢：基础键→CGPost 注入；`APP:*`→`app_switch` 工具；`APP:PICK`→`AppPicker.app`；`FOCUS_INPUT/CLICK`→Hammerspoon（`hs -c`）；`URL:`→`open`；`RUN:`→`/bin/sh`。**注入模型 = CGPost serve 常驻**（`/tmp/cgpost.sock`，零启动开销）+ 15s 无响应熔断回退 submit 一次性 job。各动作独立防抖（见 §四） |
| `voice_bridge.py` v0.9 | 纯长按语义；FS 闭环（丢事件自动补发）；注入=右⌥（61）→ Chatterfly 触发语音输入 |
| `atvv_receiver.py` v1.2 | 语音流落地：80Hz 高通 + AGC 上限 24 + 限幅 → BlackHole 2ch |
| `app_switch.swift` v1.2 | `cycle`（全应用轮询：冻结快照+前台校验）、`toggle`、`next`、`pick`、`close`（NSRunningApplication.terminate() 优雅退出；Finder 保护） |
| `AppPicker.swift` v1.3 | 常驻 Tk 风格 NSWindow 网格选择器：6 列 / 初始第 2 项 / 环绕 / 10s 自动取消 / 方向导航 / 长名跑马灯；socket `/tmp/apppicker.sock` 接收按键路由 |
| `hs_health.py` v1.0 | 12 项检查（App/CLI/进程/IPC/AX/Lua/初始化/冒烟/各服务）+ 自动修复 + 通知 |
| `remotehub_focus.lua` v1.1 | `focusInput()` 五阶段（窗口修复→缓存→坐标网格→树遍历→设焦点读回）；`clickFocused()` 四段（AXPress→直接子→向上≤6→坐标兜底） |

### 3.3 Windows 端（Windows）

| 模块 | 关键设计 |
|---|---|
| `win_receiver.py` v1.6 | UDP 接收 + 防抖 + 异步日志（队列+句柄常开，杜绝收包线程写盘）；语音键=**先切麦克风后注入**；`picker_route()` 选择器期间按键直连路由（50ms 消费，不依赖焦点）；防抖首击修复（None 哨兵） |
| `win_actions.py` v1.10 | 扩展动作库（2755 行）：CLICK 四段 / FOCUS_INPUT 五阶段（均移植自 Mac 对应件）/ APP:* 全家 / URL: / RUN: / `APP:CLOSE`（WM_CLOSE 优雅关闭：`SendMessageTimeoutW(SMTO_ABORTIFHUNG)` + `close_poll` 轮询 ≤2s + UWP 真身窗口定位）；选择器 v2.6（网格导航 + UWP Shell 图标 + 光学尺寸归一 + 长名滚动） |
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

## 六、测试体系（12 套 / 736 断言）

```bash
# Mac/T1 侧（在 remote-hub/ 下）
python3 relay_logic_test.py            # 14
python3 key_fwd_logic_test.py          # 45
python3 webui_v2_test.py               # 89
/Users/username/.workbuddy/binaries/node/versions/22.22.2-6/bin/node webui_js_test.mjs   # 42
python3 apppicker_grid_test.py         # 33
python3 apppicker_name_test.py         # 16
python3 close_app_test.py              # 18

# Win 侧（在 windows/ 下；本机双解释器 3.9 + 3.13 均须全过）
python3 offline_test.py                # 22
python3 audio_offline_test.py          # 26
python3 actions_offline_test.py        # 329  ★ 含"源码约定守护"（如断言禁用 TerminateProcess）
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
| T1 | `/root/remote-hub/` + `/etc/systemd/system/` | systemd（7 服务 enabled） |
| Mac | 工作区 `remote-hub/`（launchd WorkingDirectory 指向） | launchd ×5（4 个 KeepAlive） |
| Win | `%USERPROFILE%\remotehub-win\` | 计划任务 |

### 7.2 标准升级流程（施工单模式）
1. 本地改代码 → 编辑脚本定式（备份 `.bak-<时间>-preV*` + 逐处 `count==1` 断言 + `py_compile -W error::SyntaxWarning` + sha256）；
2. 跑离线测试全绿；
3. 分发：scp/T1:8000 → 目标端；**三重核对**（scp 后双端 sha256 一致 + HTTP 取回验证）；
4. 目标端执行施工单（`TASK-*.md`：施工步骤 + 验收清单 + 回滚指引）；
5. 回传验收报告 + 任何 `*.patched` **必回收合入上游**（防下轮全量分发覆盖）。

### 7.3 分发服务
- `8000`：T1 静态分发（根 `/root/remote-hub/windows/`，绑 T1_IP）；现已关停，用时重启；
- `8001`：`upload_recv.py` 回传接收（存 `/root/remote-hub/inbox/`）。

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
