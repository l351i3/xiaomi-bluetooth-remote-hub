import CoreGraphics
import Foundation

// mac_listen_keys.swift
// 键盘事件监听器 (listen-only) —— 用于验证「合成按键是否进入系统事件流」。
// 用法: swift mac_listen_keys.swift [秒数=8] > out.txt 2>&1

let dur = CommandLine.arguments.compactMap { Double($0) }.first ?? 8.0

let mask: CGEventMask = (1 << CGEventType.keyDown.rawValue)
    | (1 << CGEventType.keyUp.rawValue)
    | (1 << CGEventType.flagsChanged.rawValue)

let callback: CGEventTapCallBack = { _, type, event, _ in
    let kc = event.getIntegerValueField(.keyboardEventKeycode)
    let f = event.flags
    var parts: [String] = []
    if f.contains(.maskAlternate) { parts.append("ALT") }
    if f.contains(.maskCommand) { parts.append("CMD") }
    if f.contains(.maskShift) { parts.append("SHIFT") }
    if f.contains(.maskControl) { parts.append("CTRL") }
    if f.contains(.maskSecondaryFn) { parts.append("FN") }
    let t = String(format: "%.3f", Date().timeIntervalSince1970)
    let srcPid = event.getIntegerValueField(.eventSourceUnixProcessID)
    let srcState = event.getIntegerValueField(.eventSourceStateID)
    let ud = event.getIntegerValueField(.eventSourceUserData)
    print("\(t) type=\(type.rawValue) key=\(kc) flags=[\(parts.joined(separator: "+"))] srcPid=\(srcPid) srcState=\(srcState) ud=\(ud)")
    fflush(stdout)
    return Unmanaged.passUnretained(event)
}

guard let tap = CGEvent.tapCreate(
    tap: .cghidEventTap,
    place: .headInsertEventTap,
    options: .listenOnly,
    eventsOfInterest: mask,
    callback: callback,
    userInfo: nil) else {
    print("tapCreate 失败 (检查辅助功能权限)")
    exit(1)
}

let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
CGEvent.tapEnable(tap: tap, enable: true)
print("LISTEN START (\(dur) s)")
fflush(stdout)

let deadline = Date().addingTimeInterval(dur)
while Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
}
print("LISTEN END")
