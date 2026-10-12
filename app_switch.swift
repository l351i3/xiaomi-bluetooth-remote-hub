// app_switch.swift — remotehub「应用切换器」 v1.2 (2026-10-12)
// ------------------------------------------------------------------
// v1.2（10-12）: 新增 close ——「关闭当前前台应用」（用户需求: 长按电源键关闭当前应用;
//   生产绑定 = keymap #116 long=APP:CLOSE, 与 Windows win_actions v1.10 对等实现）。
//   语义 = 优雅退出（等价 Cmd+Q: 应用自身的保存/确认流程照常触发）; Finder 为系统
//   组件, 拒绝关闭（terminate() 对其无效）; NSWorkspace 直调, 非注入, 无需 TCC。
// v1.1（10-10 16:4x）: 新增 cycle ——「全应用轮询」（用户需求: 主页键要在打开的
//   所有应用之间轮转, 而非 TOGGLE 式两应用回跳）。语义:
//   · 首次按（或用户手动换过应用后）→ 重建快照（默认窗口前后序 ≈ 最近使用序,
//     CGWindowList 取; 取不到则名称序兜底）, 从当前前台位置往后切一个;
//   · 连续按（前台==上次切到的目标）→ 沿冻结快照环状推进, 不退化回跳;
//   · 状态: cycle_list(快照, \n 分隔 bundleID) / cycle_idx / cycle_expect / cycle_ts。
//   · 续期窗口 30 分钟: 超时重置（应用列表久了会变, 重建更合理）。
//   zlist = 诊断: 打印 z-order 快照（无副作用）。
// 用途: 遥控器「切换应用」动作的底层工具。
//   ★ 关键设计: 不经过键盘事件注入 —— 直接用 NSWorkspace/NSRunningApplication
//     公开 API 激活应用（绕过「组合键合成不可行」的机制边界, 无需 TCC 授权）。
// 子命令:
//   list                列出运行中的常规应用（名称 | bundleID | pid | active）
//   front               打印当前前台应用
//   activate <查询>     切换到指定应用; 未运行则 open -a 启动
//                       匹配顺序: bundleID 精确 → 名称精确 → bundleID 包含 → 名称包含
//   toggle              在最近两个应用间切换（≈ cmd+tab 快速点按的等价）
//   next                按应用名排序循环切到下一个（≈ 按住 ⌘ 连按 ⇥ 的简化等价）
//   cycle               全应用轮询（冻结快照环状推进; 主页键 #102 生产绑定）
//   close               关闭当前前台应用（优雅退出; 长按电源键 #116 生产绑定）
// 状态: <二进制目录>/state/app_switch.json —— toggle 的 {prev, cur} 记录
// 配套: key_bridge.py 收到 "KEY APP:xxx DOWN" 时调用本工具（v1.5+）
// 测试: swiftc -O -o app_switch app_switch.swift   （编译约 10-30s）
// ------------------------------------------------------------------

import Cocoa

let args = CommandLine.arguments

func die(_ m: String) -> Never {
    print("ERR: \(m)")
    exit(1)
}

func regularApps() -> [NSRunningApplication] {
    NSWorkspace.shared.runningApplications.filter { $0.activationPolicy == .regular }
}

func nameOf(_ a: NSRunningApplication) -> String {
    a.localizedName ?? a.bundleIdentifier ?? "pid\(a.processIdentifier)"
}

func idOf(_ a: NSRunningApplication) -> String {
    a.bundleIdentifier ?? nameOf(a)
}

func appDir() -> URL {
    let exe = URL(fileURLWithPath: args[0]).resolvingSymlinksInPath()
    return exe.deletingLastPathComponent()
}

func stateURL() -> URL {
    let dir = appDir().appendingPathComponent("state", isDirectory: true)
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir.appendingPathComponent("app_switch.json")
}

func loadState() -> [String: String] {
    guard let d = try? Data(contentsOf: stateURL()),
          let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: String]
    else { return [:] }
    return o
}

func saveState(_ s: [String: String]) {
    if let d = try? JSONSerialization.data(withJSONObject: s) {
        try? d.write(to: stateURL())
    }
}

func findApp(_ query: String, in apps: [NSRunningApplication]) -> NSRunningApplication? {
    let q = query.lowercased()
    if let m = apps.first(where: { ($0.bundleIdentifier ?? "").lowercased() == q }) { return m }
    if let m = apps.first(where: { nameOf($0).lowercased() == q }) { return m }
    if let m = apps.first(where: { ($0.bundleIdentifier ?? "").lowercased().contains(q) }) { return m }
    if let m = apps.first(where: { nameOf($0).lowercased().contains(q) }) { return m }
    return nil
}

func activate(_ a: NSRunningApplication) -> Bool {
    // .activateIgnoringOtherApps 已 deprecated 且无效果（macOS 14+），只用 activateAllWindows
    return a.activate(options: [.activateAllWindows])
}

func doActivate(_ query: String) -> Never {
    let apps = regularApps()
    let oldCur = NSWorkspace.shared.frontmostApplication.map { idOf($0) } ?? ""
    if let m = findApp(query, in: apps) {
        let ok = activate(m)
        if ok && oldCur != idOf(m) {
            // 成功切换后更新 toggle 基准（首次 APP:xxx 后, APP:TOGGLE 即可直接工作）
            saveState(["prev": oldCur, "cur": idOf(m)])
        }
        print(ok ? "OK activated \(nameOf(m)) [\(idOf(m))] pid=\(m.processIdentifier)"
                 : "FAIL activate() returned false for \(nameOf(m)) [\(idOf(m))]")
        exit(ok ? 0 : 1)
    }
    // 未运行 → open -a 启动（LaunchServices, 无需权限）
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    p.arguments = ["-a", query]
    var rc: Int32 = -1
    do {
        try p.run()
        p.waitUntilExit()
        rc = p.terminationStatus
    } catch {
        die("open -a 启动失败: \(error)")
    }
    print("LAUNCH '\(query)' via open -a rc=\(rc)")
    exit(rc == 0 ? 0 : 1)
}

func doToggle() -> Never {
    let cur = NSWorkspace.shared.frontmostApplication
    let curID = cur.map { idOf($0) } ?? ""
    let st = loadState()
    let prev = st["prev"] ?? ""
    let lastCur = st["cur"] ?? ""
    if lastCur.isEmpty {
        die("无切换记录（先执行一次 activate 建立基准即可）")
    }
    // cur 在记录态内 → 切到 prev；否则（用户手动换过）→ 切到最近记录的 cur
    let targetID = (curID == lastCur) ? (prev.isEmpty ? lastCur : prev) : lastCur
    if targetID == curID {
        die("目标与当前前台相同 (\(targetID))，无操作")
    }
    guard let t = regularApps().first(where: { idOf($0) == targetID }) else {
        die("目标应用不在运行: \(targetID)")
    }
    saveState(["prev": curID, "cur": targetID])
    let ok = activate(t)
    print(ok ? "OK toggle \(curID) -> \(nameOf(t)) [\(targetID)]"
             : "FAIL toggle: activate() false -> \(nameOf(t)) [\(targetID)]")
    exit(ok ? 0 : 1)
}

func doNext() -> Never {
    let apps = regularApps().sorted {
        nameOf($0).localizedStandardCompare(nameOf($1)) == .orderedAscending
    }
    guard apps.count > 1 else { die("常规应用不足 2 个") }
    let curID = NSWorkspace.shared.frontmostApplication.map { idOf($0) } ?? ""
    let idx = apps.firstIndex(where: { idOf($0) == curID }) ?? -1
    let nxt = apps[(idx + 1) % apps.count]
    let ok = activate(nxt)
    print(ok ? "OK next -> \(nameOf(nxt)) [\(idOf(nxt))]"
             : "FAIL next: activate() false -> \(nameOf(nxt)) [\(idOf(nxt))]")
    exit(ok ? 0 : 1)
}

func zOrderApps() -> [NSRunningApplication] {
    // 窗口前后序（CGWindowList 前→后）→ 应用序（≈ 最近使用序）
    guard let winfo = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements],
                                                 kCGNullWindowID) as? [[String: Any]] else {
        return []
    }
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

func nameOrderApps() -> [NSRunningApplication] {
    regularApps().sorted {
        nameOf($0).localizedStandardCompare(nameOf($1)) == .orderedAscending
    }
}

func doCycle() -> Never {
    // 「全应用轮询」: 冻结快照 + 前台校验续期; 详见头注 v1.1
    let front = NSWorkspace.shared.frontmostApplication
    let frontID = front.map { idOf($0) } ?? ""
    guard !frontID.isEmpty else { die("无法获取当前前台应用") }

    var st = loadState()
    let listStr = st["cycle_list"] ?? ""
    var names = listStr.isEmpty ? [] : listStr.components(separatedBy: "\n").filter { !$0.isEmpty }
    let expect = st["cycle_expect"] ?? ""
    let lastIdx = Int(st["cycle_idx"] ?? "") ?? -1
    let ts = Double(st["cycle_ts"] ?? "") ?? 0

    let continued = !names.isEmpty && frontID == expect
        && (Date().timeIntervalSince1970 - ts) < 1800   // 续期窗口 30 分钟, 超时重建
    var srcTag = "续"
    if !continued {
        var apps = zOrderApps()
        if apps.count >= 2 {
            srcTag = "z序"
        } else {
            srcTag = "名称序"
            apps = nameOrderApps()
        }
        var seen = Set<String>()
        names = apps.map { idOf($0) }.filter { seen.insert($0).inserted }
    }
    if !names.contains(frontID) { names.insert(frontID, at: 0) }   // 前台不在快照 → 补首位, 保环闭合
    guard names.count > 1 else { die("可切换应用不足 2 个 (count=\(names.count))") }

    let running = regularApps()
    var byID = [String: NSRunningApplication]()
    for a in running { byID[idOf(a)] = a }

    let base: Int = continued ? lastIdx : (names.firstIndex(of: frontID) ?? -1)
    var targetID = ""
    var targetIdx = -1
    for step in 1...names.count {
        let cand = ((base + step) % names.count + names.count) % names.count
        let cid = names[cand]
        if cid == frontID { continue }                  // 跳过自己
        if let a = byID[cid], !a.isTerminated {         // 跳过已退出的应用
            targetID = cid
            targetIdx = cand
            break
        }
    }
    guard targetIdx >= 0, let t = byID[targetID] else { die("环中没有可切换的目标") }

    let ok = activate(t)
    if ok {
        st["cycle_list"] = names.joined(separator: "\n")
        st["cycle_idx"] = String(targetIdx)
        st["cycle_expect"] = idOf(t)
        st["cycle_ts"] = String(Int(Date().timeIntervalSince1970))
        saveState(st)
    }
    print(ok ? "OK cycle[\(continued ? "续" : srcTag) \(targetIdx)/\(names.count - 1)] -> \(nameOf(t)) [\(idOf(t))]"
             : "FAIL cycle: activate() false -> \(nameOf(t)) [\(idOf(t))]")
    exit(ok ? 0 : 1)
}

func doZlist() -> Never {
    let z = zOrderApps()
    if z.isEmpty {
        print("(z-order 为空: CGWindowList 不可用或无屏上窗口)")
        exit(1)
    }
    print("=== z-order 应用序 (\(z.count) 个) ===")
    for (i, a) in z.enumerated() {
        print("\(i). \(nameOf(a))  |  \(idOf(a))  |  pid=\(a.processIdentifier)")
    }
    exit(0)
}

func doClose() -> Never {
    // v1.2: 关闭当前前台应用（优雅退出, 等价 Cmd+Q）——「长按电源键」生产动作。
    guard let front = NSWorkspace.shared.frontmostApplication else { die("无法获取当前前台应用") }
    let bid = front.bundleIdentifier ?? ""
    if bid == "com.apple.finder" { die("Finder 为系统组件, 拒绝关闭") }
    let nm = nameOf(front)
    let ok = front.terminate()
    print(ok ? "OK close -> \(nm) [\(bid)] pid=\(front.processIdentifier)"
             : "FAIL close: terminate() 被拒 -> \(nm) [\(bid)]")
    exit(ok ? 0 : 1)
}

switch args.count > 1 ? args[1] : "" {
case "list":
    // 排序与 next 的循环顺序保持一致（localizedStandardCompare）
    let apps = regularApps().sorted {
        nameOf($0).localizedStandardCompare(nameOf($1)) == .orderedAscending
    }
    print("=== \(apps.count) 个常规应用 ===")
    for a in apps {
        let mark = a.isActive ? " *ACTIVE*" : ""
        print("\(nameOf(a))  |  \(idOf(a))  |  pid=\(a.processIdentifier)\(mark)")
    }
case "front":
    if let a = NSWorkspace.shared.frontmostApplication {
        print("FRONT \(nameOf(a)) [\(idOf(a))] pid=\(a.processIdentifier)")
    } else {
        print("FRONT (none)")
    }
case "activate":
    guard args.count > 2 else { die("用法: app_switch activate <名称>") }
    doActivate(args[2])
case "toggle":
    doToggle()
case "next":
    doNext()
case "cycle":
    doCycle()
case "zlist":
    doZlist()
case "close":
    doClose()
default:
    die("用法: app_switch list|front|activate <名称>|toggle|next|cycle|zlist|close")
}
