import CoreGraphics
import ApplicationServices
import Foundation

// mac_synth_test.swift v0.2
// 右⌘/右⌥ 合成测试——验证「电脑端合成按键 → 唤起 Chatterfly」链路。
// 参数:
//   [--check]            仅查辅助功能权限 (无副作用)
//   [--release]          只发一次"松开" (清残留)
//   [rightcmd|rightopt]  目标键 (默认 rightopt)
//   [--tap2]             双点按模式: 点一下 → 3 秒 → 点一下 (间隔内说话)
//   [秒数]               按住模式时长 (默认 2.5)
// 例:
//   swift mac_synth_test.swift rightcmd 2.0     # 右⌘ 按住 2 秒再松开
//   swift mac_synth_test.swift rightopt --tap2  # 右⌥ 点按两次 (开始/结束)

let args = CommandLine.arguments
let checkOnly = args.contains("--check")
let wantPrompt = args.contains("--prompt")
let useRightCmd = args.contains("rightcmd")
let tap2 = args.contains("--tap2")

let key: CGKeyCode = useRightCmd ? 0x36 : 0x3D   // RightCommand(54) / RightOption(61)
let modFlag: CGEventFlags = useRightCmd ? .maskCommand : .maskAlternate
let modName = useRightCmd ? "右⌘" : "右⌥"

var trusted = AXIsProcessTrusted()
if wantPrompt && !trusted {
    let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    trusted = AXIsProcessTrustedWithOptions(opts)
}

print("辅助功能权限: " + (trusted ? "已授权" : "未授权"))
if checkOnly {
    exit(trusted ? 0 : 2)
}
if !trusted {
    print("→ 合成事件不会生效。请到: 系统设置 → 隐私与安全性 → 辅助功能, 把 WorkBuddy 打勾后重跑。")
    exit(2)
}

func post(_ down: Bool) {
    guard let src = CGEventSource(stateID: .hidSystemState),
          let ev = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: down) else {
        print("CGEvent 创建失败")
        exit(1)
    }
    ev.flags = down ? modFlag : []
    ev.post(tap: .cghidEventTap)
}

func selfCheck(_ label: String, expect: Bool) {
    Thread.sleep(forTimeInterval: 0.15)
    let s = CGEventSource.flagsState(.hidSystemState)
    print("自证: \(label) → \(modName) 状态 = \(s.contains(modFlag)) (期望 \(expect))")
}

if args.contains("--release") {
    post(false)
    Thread.sleep(forTimeInterval: 0.15)
    let s = CGEventSource.flagsState(.hidSystemState)
    print("已单独发送 \(modName) 释放; 状态 = \(s.contains(modFlag)) (期望 false)")
    exit(0)
}

if args.contains("--screenshot") || args.contains("--fullshot") {
    func postKey(_ code: CGKeyCode, _ down: Bool, _ flags: CGEventFlags) {
        guard let src = CGEventSource(stateID: .hidSystemState),
              let ev = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: down) else { return }
        ev.flags = flags
        ev.post(tap: .cghidEventTap)
    }
    let combo: CGEventFlags = [.maskCommand, .maskShift]
    let full = args.contains("--fullshot")
    let ch: CGKeyCode = full ? 0x14 : 0x15   // "3" 全屏 / "4" 区域
    // 完整键序（模拟真实物理按键）: L⌘↓ ⇧↓ 3↓ 3↑ ⇧↑ ⌘↑
    postKey(0x37, true, [.maskCommand])
    postKey(0x38, true, [.maskCommand, .maskShift])
    postKey(ch, true, combo)
    postKey(ch, false, combo)
    postKey(0x38, false, [.maskCommand])
    postKey(0x37, false, [])
    if full {
        print("已合成 ⌘⇧3（全屏截图）——若生效, 桌面会出现新截图文件。")
    } else {
        print("已合成 ⌘⇧4（区域截图）——看屏幕: 应出现截图十字光标。3 秒后自动 esc 取消…")
        Thread.sleep(forTimeInterval: 3.0)
        postKey(0x35, true, [])      // esc
        postKey(0x35, false, [])
        print("已发送 esc。若十字光标闪过 = 合成链路对系统级热键有效。")
    }
    exit(0)
}

if args.contains("--testsrc") {
    func fire(_ mode: String, _ down: Bool) {
        let srcMode: CGEventSource?
        switch mode {
        case "B": srcMode = CGEventSource(stateID: .hidSystemState)
        case "C": srcMode = CGEventSource(stateID: .combinedSessionState)
        default:  srcMode = nil
        }
        guard let ev = CGEvent(keyboardEventSource: srcMode, virtualKey: 0x36, keyDown: down) else { return }
        if mode == "B" {
            ev.setIntegerValueField(.eventSourceUnixProcessID, value: 0)
        }
        ev.flags = down ? .maskCommand : []
        ev.post(tap: .cghidEventTap)
    }
    for mode in ["A", "B", "C"] {
        print("变体 \(mode): 右⌘ 按住 0.5s (A=nil源 / B=hid源+setPid0 / C=combined源)")
        fire(mode, true)
        Thread.sleep(forTimeInterval: 0.5)
        fire(mode, false)
        Thread.sleep(forTimeInterval: 1.0)
    }
    print("三个变体已发完——看监听日志里各自 srcPid 值。")
    exit(0)
}

if args.contains("--type") {
    func postPlain(_ code: CGKeyCode, _ down: Bool) {
        guard let src = CGEventSource(stateID: .hidSystemState),
              let ev = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: down) else { return }
        ev.flags = []
        ev.post(tap: .cghidEventTap)
    }
    let digits: [CGKeyCode] = [0x12, 0x13, 0x14, 0x15, 0x17, 0x16]  // 1 2 3 4 5 6
    print("3 秒后开始合成 123456 … (请把光标放在输入框里)")
    Thread.sleep(forTimeInterval: 3.0)
    for d in digits {
        postPlain(d, true)
        Thread.sleep(forTimeInterval: 0.06)
        postPlain(d, false)
        Thread.sleep(forTimeInterval: 0.12)
    }
    print("已合成 123456 —— 看输框: 应该出现了这串数字。")
    exit(0)
}

if tap2 {
    post(true); Thread.sleep(forTimeInterval: 0.08); post(false)
    selfCheck("第 1 次点按后", expect: false)
    print("\(modName) 第 1 次点按已发——Chatterfly 应开始录音; 现在可以说话, 3 秒后自动结束…")
    Thread.sleep(forTimeInterval: 3.0)
    post(true); Thread.sleep(forTimeInterval: 0.08); post(false)
    selfCheck("第 2 次点按后", expect: false)
    print("\(modName) 第 2 次点按已发——应结束录音并识别。")
    exit(0)
}

let hold = args.compactMap { Double($0) }.first ?? 2.5
post(true)
selfCheck("按下后", expect: true)
print("\(modName) 已合成按下 (保持 \(hold) 秒) ——看屏幕: Chatterfly 应进入录音。")
Thread.sleep(forTimeInterval: hold)
post(false)
selfCheck("松开后", expect: false)
print("\(modName) 已合成松开——Chatterfly 应结束录音并上屏。")
