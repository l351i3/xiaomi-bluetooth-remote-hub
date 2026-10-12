import CoreGraphics
import Foundation

// mac_click.swift — 合成一次鼠标移动+左键单击到指定屏幕坐标（备用工具）
// 用途: 例如"点击面板外区域"以关闭挂起面板 等场景
// 用法: swift mac_click.swift <x> <y>
// 注意: 会真实点击坐标处的东西——坐标要选安全区域!

let x = CommandLine.arguments.count > 2 ? (Double(CommandLine.arguments[1]) ?? 10) : 10
let y = CommandLine.arguments.count > 2 ? (Double(CommandLine.arguments[2]) ?? 1040) : 1040
let pt = CGPoint(x: x, y: y)

guard let src = CGEventSource(stateID: .hidSystemState) else { exit(1) }
let move = CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: pt, mouseButton: .left)
move?.post(tap: .cghidEventTap)
usleep(50_000)
let down = CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: pt, mouseButton: .left)
down?.post(tap: .cghidEventTap)
usleep(60_000)
let up = CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: pt, mouseButton: .left)
up?.post(tap: .cghidEventTap)
print("clicked at \(x),\(y)")
