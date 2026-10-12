// AppPicker.swift — remotehub「应用选择器」 v1.3 (2026-10-12)
// ------------------------------------------------------------------
// v1.3（10-12）: 长名滚动显示（对齐 Windows picker v2.3+ / win_actions fit_prefix·cycle_slice）——
//   非选中超宽名 → 像素预算内截断 + 「…」; 选中超宽名 → 「名 + 3 空格」环形跑马灯（每 180ms
//   进 1 字符, 切换选中从头部重滚）; 预算内短名原样。修复用户实测「app 名称长的显示不全」
//   （Windows v2.3 同名修复的 Mac 对齐轮）。
// v1.2（10-12）: 网格方向导航（对齐 Windows picker v2.4 / win_actions.grid_move）——
//   ↑/↓ 垂直移动（相邻行同列优先; 该列缺失取最近列〔靠左〕; 首行↑ / 末行↓ 回绕另一端）,
//   ←/→ 行内水平（线性环绕）; 单行/单列自然退化为线性（与旧行为一致）。
//   修复用户实测「两行以上时 ↑↓ 也是左右移动, 不符合操作直觉」。
// v1.1（10-10 19:3x）: ENTER 激活目标应用后, 派生 `hs` 子进程调度焦点修复
//   （remotehub_focus.lua.assistLater() → +0.45s 窗口级 raise/main/focus）—— 修复
//   “切换后窗口有时无法获得键盘焦点”（macOS 14+ 后台激活偶发静默失败）。
//   spawn 失败仅记日志, 不影响选择器主流程。
// 由 key_bridge v1.7 的 APP:PICK 触发（长按遥控器主页键）。设计:
//   · LSUIElement（无 Dock 图标）+ nonactivatingPanel: 显示不抢前台焦点;
//   · 列出运行中的常规应用（CGWindowList z-order ≈ 最近使用序, 不足则名称序）,
//     网格显示图标+名称; 初始高亮=第 2 个（≈ 上一个应用）;
//   · 按键不经过系统键盘通道 —— key_bridge 将 LEFT/RIGHT/UP/DOWN/ENTER/ESC
//     经 UNIX dgram /tmp/apppicker.sock 转发到本进程（socket 存在 = 显示中标志）;
//   · OK(ENTER)=激活选中应用; Esc=取消; 10s 无操作自动取消; 每次退出 unlink socket。
// 日志: /tmp/apppicker.log（append）
// 编译: swiftc -O -swift-version 5 -o AppPicker AppPicker.swift
//   bundle 组装: AppPicker.app/Contents/{Info.plist, MacOS/AppPicker}
// 配套: key_bridge.py v1.7（do_app "pick" 启动本 App; PICKER_KEYS 路由）
// ------------------------------------------------------------------
import Cocoa

let SOCK_PATH = "/tmp/apppicker.sock"
let LOG_PATH = "/tmp/apppicker.log"
let TIMEOUT_SEC = 10.0
let COLS_MAX = 6
let CELL_W: CGFloat = 104
let CELL_H: CGFloat = 112
let MARGIN: CGFloat = 20
let HEADER_H: CGFloat = 34
let NAME_BUDGET: CGFloat = CELL_W - 12   // v1.3: 名称像素预算（两侧留白防贴边; 对齐 win 版语义）
let MARQUEE_MS = 180                     // v1.3: 跑马灯步进间隔（对齐 win 版 PICK_MARQUEE_MS）

func plog(_ m: String) {
    let ts = ISO8601DateFormatter().string(from: Date())
    let line = "[\(ts)] \(m)\n"
    if let d = line.data(using: .utf8) {
        let url = URL(fileURLWithPath: LOG_PATH)
        if let h = try? FileHandle(forWritingTo: url) {
            h.seekToEndOfFile()
            h.write(d)
            try? h.close()
        } else {
            try? line.write(to: url, atomically: true, encoding: .utf8)
        }
    }
}

func nameOf(_ a: NSRunningApplication) -> String {
    a.localizedName ?? a.bundleIdentifier ?? "pid\(a.processIdentifier)"
}

// v1.2: 网格方向导航（纯逻辑; 逐语义对齐 win_actions.grid_move —— ↑↓=垂直/回绕/末行不满取最近列,
//   ←→=线性环绕; 单行/单列退化线性）
func gridMove(_ sel: Int, _ action: String, cols: Int, n: Int) -> Int {
    if n <= 0 { return 0 }
    let a = action.uppercased()
    let c = cols < 1 ? 1 : cols                 // 非法 cols 按单列（对齐上游语义）
    if c <= 1 || n <= c {                       // 单列 / 单行 → 线性环绕
        if a == "UP" || a == "LEFT" { return (sel - 1 + n) % n }
        if a == "DOWN" || a == "RIGHT" { return (sel + 1 + n) % n }
        return ((sel % n) + n) % n
    }
    if a == "LEFT" { return (sel - 1 + n) % n }
    if a == "RIGHT" { return (sel + 1 + n) % n }
    if a != "UP" && a != "DOWN" { return ((sel % n) + n) % n }
    let rows = (n + c - 1) / c
    let s = ((sel % n) + n) % n
    let row = s / c
    let col = s % c
    let tr: Int
    if a == "UP" { tr = row > 0 ? row - 1 : rows - 1 }
    else { tr = row < rows - 1 ? row + 1 : 0 }
    let base = tr * c
    let cnt = min(c, n - base)                  // 目标行实际格数（末行可能不满）
    if col < cnt { return base + col }          // 同列存在
    return base + (cnt - 1)                     // 该列缺失 → 最近列（靠左）
}

// v1.3: 长名处理（逐语义对齐 win_actions.fit_prefix / cycle_slice —— 非选中截断+…, 选中跑马灯）
let nameFont = NSFont.systemFont(ofSize: 11)

func measureName(_ s: String) -> CGFloat {
    (s as NSString).size(withAttributes: [.font: nameFont]).width
}

func fitPrefix(_ name: String, budget: CGFloat, measure: (String) -> CGFloat) -> String {
    if name.isEmpty || measure(name) <= budget { return name }
    let ew = measure("…")
    var out = ""
    var w: CGFloat = 0
    for ch in name {
        let cw = measure(String(ch))
        if w + cw + ew > budget { break }
        out.append(ch)
        w += cw
    }
    return (out.isEmpty ? String(name.prefix(1)) : out) + "…"
}

func cycleSlice(_ name: String, offset: Int, budget: CGFloat, measure: (String) -> CGFloat) -> String {
    if name.isEmpty || measure(name) <= budget { return name }
    let seq = Array(name + "   ")
    let n = seq.count
    var out = ""
    var w: CGFloat = 0
    var i = ((offset % n) + n) % n
    while out.count < n {
        let ch = String(seq[i % n])
        let cw = measure(ch)
        if w + cw > budget { break }
        out += ch
        w += cw
        i += 1
    }
    return out
}

// v1.1: 激活后焦点修复（经 Hammerspoon 的 hs CLI; 失败静默, 不干扰主流程）
func spawnFocusAssist() {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/opt/homebrew/bin/hs")
    p.arguments = ["-c", "return dofile(\"/Users/username/.hammerspoon/remotehub_focus.lua\").assistLater()"]
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    do { try p.run() } catch { plog("focus assist spawn fail: \(error)") }
}

func zOrderApps() -> [NSRunningApplication] {
    guard let winfo = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements],
                                                 kCGNullWindowID) as? [[String: Any]] else { return [] }
    var seen = Set<pid_t>()
    var out: [NSRunningApplication] = []
    for w in winfo {
        guard let layer = w[kCGWindowLayer as String] as? Int, layer == 0 else { continue }
        guard let pidNum = w[kCGWindowOwnerPID as String] as? Int else { continue }
        let pid = pid_t(pidNum)
        if seen.contains(pid) { continue }
        seen.insert(pid)
        if let a = NSRunningApplication(processIdentifier: pid),
           a.activationPolicy == .regular, !a.isTerminated {
            out.append(a)
        }
    }
    return out
}

// ---- 防双实例 ----
if FileManager.default.fileExists(atPath: SOCK_PATH) {
    plog("another instance appears running (socket exists); exit")
    exit(0)
}

// ---- 应用列表（z-order 优先, 不足 2 个回退名称序）----
var apps: [NSRunningApplication] = []
do {
    var seen = Set<pid_t>()
    for a in zOrderApps() where seen.insert(a.processIdentifier).inserted {
        apps.append(a)
    }
    if apps.count < 2 {
        let named = NSWorkspace.shared.runningApplications
            .filter { $0.activationPolicy == .regular && !$0.isTerminated }
            .sorted { nameOf($0).localizedStandardCompare(nameOf($1)) == .orderedAscending }
        seen.removeAll()
        apps = []
        for a in named where seen.insert(a.processIdentifier).inserted {
            apps.append(a)
        }
    }
}
if apps.isEmpty {
    plog("no running apps found; exit")
    exit(1)
}

var sel = apps.count > 1 ? 1 : 0

// ---- 面板构建 ----
let cols = min(COLS_MAX, apps.count)
let rows = (apps.count + cols - 1) / cols
let panelW = CGFloat(cols) * CELL_W + MARGIN * 2
let panelH = CGFloat(rows) * CELL_H + HEADER_H + MARGIN * 2

let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: panelW, height: panelH),
                    styleMask: [.borderless, .nonactivatingPanel],
                    backing: .buffered, defer: false)
panel.level = .floating
panel.isFloatingPanel = true
panel.hidesOnDeactivate = false
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
panel.hasShadow = true
panel.isOpaque = false
panel.backgroundColor = .clear

let bg = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: panelW, height: panelH))
bg.material = .hudWindow
bg.blendingMode = .behindWindow
bg.state = .active
bg.wantsLayer = true
bg.layer?.cornerRadius = 18
bg.layer?.masksToBounds = true
bg.layer?.borderWidth = 1
bg.layer?.borderColor = NSColor.white.withAlphaComponent(0.14).cgColor
panel.contentView = bg

let header = NSTextField(labelWithString: "↑ ↓ ← → 选择   ·   OK 打开   ·   Esc 取消")
header.font = .systemFont(ofSize: 12, weight: .medium)
header.textColor = .secondaryLabelColor
header.alignment = .center
header.frame = NSRect(x: MARGIN, y: panelH - MARGIN - 18 + 2, width: panelW - MARGIN * 2, height: 18)
bg.addSubview(header)

var itemViews: [NSView] = []
var nameLabels: [NSTextField] = []   // v1.3
var fullNames: [String] = []         // v1.3
var isOverflow: [Bool] = []          // v1.3: 名宽 > 预算（截断/跑马灯候选）
for (i, app) in apps.enumerated() {
    let r = i / cols
    let c = i % cols
    let x = MARGIN + CGFloat(c) * CELL_W
    let y = panelH - MARGIN - HEADER_H - CGFloat(r + 1) * CELL_H
    let cell = NSView(frame: NSRect(x: x, y: y, width: CELL_W, height: CELL_H))
    cell.wantsLayer = true
    cell.layer?.cornerRadius = 14

    let iv = NSImageView(frame: NSRect(x: (CELL_W - 64) / 2, y: CELL_H - 64 - 10, width: 64, height: 64))
    iv.image = app.icon ?? NSImage(systemSymbolName: "app", accessibilityDescription: nil)
    iv.imageScaling = .scaleProportionallyUpOrDown
    cell.addSubview(iv)

    let nm = nameOf(app)
    let lb = NSTextField(labelWithString: nm)
    lb.font = nameFont
    lb.textColor = .labelColor
    lb.alignment = .center
    lb.lineBreakMode = .byClipping   // v1.3: 长名走自绘截断/跑马灯（不再走系统尾部截断）
    lb.frame = NSRect(x: 4, y: 8, width: CELL_W - 8, height: 16)
    cell.addSubview(lb)
    nameLabels.append(lb)
    fullNames.append(nm)
    isOverflow.append(measureName(nm) > NAME_BUDGET)

    bg.addSubview(cell)
    itemViews.append(cell)
}

var marqueeOff = 0   // v1.3: 跑马灯字符偏移

func displayName(_ i: Int, on: Bool) -> String {
    let nm = fullNames[i]
    if !isOverflow[i] { return nm }
    return on
        ? cycleSlice(nm, offset: marqueeOff, budget: NAME_BUDGET, measure: measureName)
        : fitPrefix(nm, budget: NAME_BUDGET, measure: measureName)
}

func updateHighlight() {
    marqueeOff = 0   // v1.3: 切换选中 → 从名称开头重新滚动
    for (i, v) in itemViews.enumerated() {
        let on = (i == sel)
        v.layer?.backgroundColor = on
            ? NSColor.controlAccentColor.withAlphaComponent(0.32).cgColor
            : NSColor.clear.cgColor
        v.layer?.borderWidth = on ? 2.5 : 0
        v.layer?.borderColor = NSColor.controlAccentColor.cgColor
        nameLabels[i].stringValue = displayName(i, on: on)
    }
}

var lastAct = Date()

func shutdown(code: Int32) -> Never {
    unlink(SOCK_PATH)
    plog("exit (sel=\(sel) \(nameOf(apps[sel])))")
    exit(code)
}

// ---- socket 服务端（UNIX dgram）----
unlink(SOCK_PATH)
let fd = socket(AF_UNIX, SOCK_DGRAM, 0)
if fd < 0 {
    plog("socket() failed errno=\(errno); exit")
    exit(1)
}
var addr = sockaddr_un()
addr.sun_family = sa_family_t(AF_UNIX)
_ = withUnsafeMutablePointer(to: &addr.sun_path) { p in
    p.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: addr.sun_path)) { dst in
        strlcpy(dst, SOCK_PATH, MemoryLayout.size(ofValue: addr.sun_path))
    }
}
let bindRc = withUnsafePointer(to: &addr) { ap in
    ap.withMemoryRebound(to: sockaddr.self, capacity: 1) { sap in
        bind(fd, sap, socklen_t(MemoryLayout<sockaddr_un>.size))
    }
}
if bindRc != 0 {
    plog("bind failed errno=\(errno); exit")
    exit(1)
}
_ = fcntl(fd, F_SETFL, O_NONBLOCK)

func handleCmd(_ cmd: String) {
    lastAct = Date()
    switch cmd {
    case "LEFT", "RIGHT", "UP", "DOWN":
        // v1.2: 网格方向导航（↑↓=垂直移动; ←→=行内线性）——不再与 ←→ 同为线性 ±1
        sel = gridMove(sel, cmd, cols: cols, n: apps.count)
        updateHighlight()
        plog("move \(cmd) -> \(sel) \(nameOf(apps[sel]))")
    case "ENTER":
        let a = apps[sel]
        plog("ENTER -> activate \(nameOf(a)) [\(a.bundleIdentifier ?? "-")] pid=\(a.processIdentifier)")
        _ = a.activate(options: [.activateAllWindows])
        spawnFocusAssist()   // v1.1: 激活后焦点修复（+0.45s）
        shutdown(code: 0)
    case "ESC":
        plog("ESC cancel")
        shutdown(code: 0)
    default:
        plog("unknown cmd: \(cmd)")
    }
}

let src = DispatchSource.makeReadSource(fileDescriptor: fd, queue: .main)
src.setEventHandler {
    var buf = [UInt8](repeating: 0, count: 256)
    while true {
        let n = buf.withUnsafeMutableBytes { recv(fd, $0.baseAddress, $0.count, 0) }
        if n <= 0 { break }
        let cmd = (String(bytes: buf[0..<Int(n)], encoding: .utf8) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !cmd.isEmpty { handleCmd(cmd) }
    }
}
src.resume()

// ---- 超时自动取消 ----
let timer = DispatchSource.makeTimerSource(queue: .main)
timer.schedule(deadline: .now() + 1.0, repeating: 1.0)
timer.setEventHandler {
    if Date().timeIntervalSince(lastAct) > TIMEOUT_SEC {
        plog("timeout \(Int(TIMEOUT_SEC))s -> cancel")
        shutdown(code: 0)
    }
}
timer.resume()

// ---- v1.3: 跑马灯（选中超宽名滚动; 180ms 步进）----
let marquee = DispatchSource.makeTimerSource(queue: .main)
marquee.schedule(deadline: .now() + Double(MARQUEE_MS) / 1000.0,
                 repeating: Double(MARQUEE_MS) / 1000.0)
marquee.setEventHandler {
    guard sel < fullNames.count, isOverflow[sel] else { return }
    marqueeOff = (marqueeOff + 1) % (fullNames[sel].count + 3)
    nameLabels[sel].stringValue = displayName(sel, on: true)
}
marquee.resume()

// ---- 显示（不激活本 app, 不抢焦点）----
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
panel.center()
panel.orderFrontRegardless()
updateHighlight()
plog("shown: \(apps.count) apps, sel=\(sel) \(nameOf(apps[sel]))")

app.run()
