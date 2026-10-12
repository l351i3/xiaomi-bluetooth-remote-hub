import CoreGraphics
import Foundation

// mac_flags.swift — 读取系统/会话的当前修饰键状态（检查合成按键有无"残留按下"）
// 用法: swift mac_flags.swift

func dump(_ label: String, _ s: CGEventSourceStateID) {
    let f = CGEventSource.flagsState(s)
    print("\(label) raw=0x\(String(f.rawValue, radix: 16, uppercase: false))  alt=\(f.contains(.maskAlternate)) cmd=\(f.contains(.maskCommand)) shift=\(f.contains(.maskShift)) ctrl=\(f.contains(.maskControl))  devRAlt=\((f.rawValue & 0x40) != 0) devLAlt=\((f.rawValue & 0x20) != 0) devRCmd=\((f.rawValue & 0x10) != 0) devLCmd=\((f.rawValue & 0x8) != 0)")
}

dump("hidSystemState ", .hidSystemState)
dump("combinedSession", .combinedSessionState)
dump("privateState   ", .privateState)
