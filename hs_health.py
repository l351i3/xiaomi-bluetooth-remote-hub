#!/usr/bin/env python3
"""hs_health.py — 遥控器链路「健康守卫」v1.0 (2026-10-10)

定位（用户需求原话）：「核心就是用户感知最低最好，一旦出现什么故障主动报告，然后安排修复。
如果能自动修复就更好了。」
  · 静默巡检：launchd 每小时跑一次（--quiet 时全绿仅留一行心跳日志）
  · 主动报告：检测到异常 → macOS 通知（说明「已自动修复」或「需人工处理」）
  · 自动修复：能修的全部自动修（CLI 链接 / 焦点脚本 / init.lua 块 / 进程拉起 / 服务重拉）

覆盖范围：
  A. Hammerspoon 焦点域（8 项）：App 版本 / CLI 链接 / 进程 / IPC / 辅助功能授权 /
     焦点脚本一致性 / init.lua IPC 块 / 焦点脚本可加载性
  B. Mac 四服务存活（voice-bridge / atvv-receiver / key-bridge / cgpost-serve）
     —— 掉线自动 kickstart，未加载则 bootstrap（plist 在 ~/Library/LaunchAgents/）

用法：
  hs_health.py                 # 巡检 + 完整报告（不改任何东西）
  hs_health.py --fix           # 巡检 + 自动修复 + 复检
  hs_health.py --fix --notify  # 修复同时发 macOS 通知（launchd 用法）
  hs_health.py --quiet         # 全绿仅心跳一行；异常时完整报告
退出码：0=全绿或已全部修复 / 1=存在未解决异常

背景文档：remote-hub/hammerspoon-focus.md（Hammerspoon 更新风险与修复手册）
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HS_APP = "/Applications/Hammerspoon.app"
HS_CLI = "/opt/homebrew/bin/hs"
HS_CLI_TARGET = HS_APP + "/Contents/Frameworks/hs/hs"
LUA_SRC = os.path.join(HERE, "hammerspoon", "remotehub_focus.lua")
LUA_DEP = os.path.expanduser("~/.hammerspoon/remotehub_focus.lua")
INIT_LUA = os.path.expanduser("~/.hammerspoon/init.lua")
STATE_PATH = os.path.join(HERE, "state", "hs_health_state.json")
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")

PGREP = "/usr/bin/pgrep"
OPEN = "/usr/bin/open"
OSASCRIPT = "/usr/bin/osascript"
LAUNCHCTL = "/bin/launchctl"

HS_PROC_PATTERN = "Hammerspoon.app/Contents/MacOS/Hammerspoon"
SERVICES = [
    ("com.remotehub.voice-bridge", "voice-bridge"),
    ("com.remotehub.atvv-receiver", "atvv-receiver"),
    ("com.remotehub.key-bridge", "key-bridge"),
    ("com.remotehub.cgpost-serve", "cgpost-serve"),
]
IPC_RESTART_COOLDOWN = 1800.0  # 重启 Hammerspoon 的防风暴窗口（秒）

INIT_BLOCK = """
-- remotehub: 启用 `hs` CLI IPC（遥控器「跳输入框/聚焦修复」经 hs -c 调用；2026-10-10）
-- 配套脚本: ~/.hammerspoon/remotehub_focus.lua（主源在 remote-hub/hammerspoon/）
local okIpc, errIpc = pcall(require, "hs.ipc")
if not okIpc then
  hs.console.printStyledtext("remotehub: hs.ipc 加载失败: " .. tostring(errIpc))
end
"""


# ---------- 基础工具 ----------
def run(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except Exception as e:  # noqa: BLE001
        return None, "", repr(e)


def hs(code, timeout=8):
    rc, out, err = run([HS_CLI, "-c", code], timeout)
    return rc, out.strip(), err.strip()


def load_state():
    try:
        with open(STATE_PATH) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass


def notify(title, text):
    def q(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    rc, _, err = run([OSASCRIPT, "-e", f"display notification {q(text)} with title {q(title)}"], 12)
    return rc == 0, err


# ---------- 检查项（返回 (ok: bool, detail: str)） ----------
def check_app():
    try:
        with open(os.path.join(HS_APP, "Contents", "Info.plist"), "rb") as f:
            ver = plistlib.load(f).get("CFBundleShortVersionString")
        if ver:
            return True, f"v{ver}"
    except Exception:  # noqa: BLE001
        pass
    return False, "Hammerspoon.app 缺失或版本不可读（需重装: brew install --cask hammerspoon）"


def check_cli():
    if os.path.islink(HS_CLI):
        target = os.path.realpath(HS_CLI)
        if os.path.exists(target):
            return True, f"symlink → {target}"
        return False, f"符号链接悬空 → {target}"
    if os.path.exists(HS_CLI):
        return False, "存在但非符号链接（人工核查；不自动修改）"
    return False, "不存在"


def check_proc():
    rc, out, err = run([PGREP, "-f", HS_PROC_PATTERN])
    if rc == 0 and out.strip():
        return True, f"pid {out.split()[0]}"
    if rc == 1:
        return False, "未在运行"
    return False, f"检测异常 rc={rc} {err.strip()[:60]}"


def check_ipc():
    rc, out, err = hs('return "ok"')
    if rc == 0 and out == "ok":
        return True, "hs -c 响应正常"
    return False, f"IPC 无响应 (rc={rc} {err[:70] or out[:70]})"


def check_ax():
    rc, out, err = hs("return tostring(hs.accessibilityState())")
    if rc == 0 and out == "true":
        return True, "辅助功能授权在"
    if rc == 0 and out == "false":
        return False, "辅助功能授权缺失（需在 系统设置→隐私与安全性→辅助功能 勾选 Hammerspoon）"
    return False, f"无法查询 (rc={rc} {err[:70] or out[:70]})"


def check_lua():
    try:
        src = open(LUA_SRC, "rb").read()
    except Exception as e:  # noqa: BLE001
        return False, f"主源缺失! {e}"
    try:
        dep = open(LUA_DEP, "rb").read()
    except Exception:  # noqa: BLE001
        return False, "部署副本缺失"
    if hashlib.md5(src).hexdigest() == hashlib.md5(dep).hexdigest():
        return True, f"一致 ({len(src)}B)"
    return False, "部署副本与主源不一致"


def check_init():
    try:
        content = open(INIT_LUA, encoding="utf-8").read()
    except Exception:  # noqa: BLE001
        return False, "init.lua 缺失"
    return (True, "含 hs.ipc 启用块") if "hs.ipc" in content else (False, "缺 hs.ipc 启用块")


def check_smoke():
    rc, out, err = hs(f'return type(dofile("{LUA_DEP}").focusInput)')
    if rc == 0 and out == "function":
        return True, "focusInput 可加载"
    return False, f"脚本加载异常 (rc={rc} {err[:70] or out[:70]})"


def check_service(label):
    rc, out, err = run([LAUNCHCTL, "print", f"gui/{os.getuid()}/{label}"], 12)
    if rc != 0:
        return False, "服务未加载（launchd 中不存在）"
    state_name, pid = None, None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("state = ") and state_name is None:
            state_name = s.split("=", 1)[1].strip()
        elif s.startswith("pid = ") and pid is None:
            pid = s.split("=", 1)[1].strip()
    if state_name == "running" and pid:
        return True, f"running (pid {pid})"
    return False, f"state={state_name or '?'} pid={pid or '-'}"


# ---------- 修复器 ----------
def fix_cli():
    if os.path.islink(HS_CLI):
        os.remove(HS_CLI)
    elif os.path.exists(HS_CLI):
        return False, "非符号链接，拒绝自动修改"
    if not os.path.exists(HS_CLI_TARGET):
        return False, "目标二进制不存在（Hammerspoon 安装异常）"
    os.symlink(HS_CLI_TARGET, HS_CLI)
    return True, "已重建符号链接"


def fix_lua():
    try:
        os.makedirs(os.path.dirname(LUA_DEP), exist_ok=True)
        shutil.copyfile(LUA_SRC, LUA_DEP)
        return True, "已重新部署 remotehub_focus.lua"
    except Exception as e:  # noqa: BLE001
        return False, f"部署失败: {e}"


def fix_init():
    try:
        content = ""
        if os.path.exists(INIT_LUA):
            content = open(INIT_LUA, encoding="utf-8").read()
            if "hs.ipc" not in content:
                shutil.copyfile(INIT_LUA, INIT_LUA + ".autofix.bak")
        if "hs.ipc" in content:
            return True, "已含启用块（跳过）"
        with open(INIT_LUA, "a", encoding="utf-8") as f:
            f.write(INIT_BLOCK)
        return True, "已追加 hs.ipc 启用块"
    except Exception as e:  # noqa: BLE001
        return False, f"写入失败: {e}"


def fix_proc():
    rc, _, err = run([OPEN, "-a", "Hammerspoon"], 15)
    if rc == 0:
        # 等待 IPC 就绪（最多 ~9s），避免刚拉起即被判未就绪而触发无谓重启
        for _ in range(9):
            r, o, _ = hs('return "ok"', timeout=4)
            if r == 0 and o == "ok":
                break
            time.sleep(1)
        return True, "已拉起 Hammerspoon"
    return False, f"启动失败 rc={rc} {err.strip()[:60]}"


def fix_ipc_restart(state):
    last = float(state.get("last_restart_ts", 0) or 0)
    if time.time() - last < IPC_RESTART_COOLDOWN:
        return False, f"{int(IPC_RESTART_COOLDOWN / 60)} 分钟内已尝试过重启，跳过（防风暴）"
    # 用 kill -TERM 而非 osascript quit（后者依赖 AppleEvents 自动化权限，实测被拦 -10004）
    rc, out, _ = run([PGREP, "-f", HS_PROC_PATTERN])
    pids = out.split() if rc == 0 else []
    for pid in pids:
        run(["/bin/kill", "-TERM", pid], 5)
    for _ in range(6):  # 最多等 6s 退出；仍未退则 KILL
        time.sleep(1)
        rc2, out2, _ = run([PGREP, "-f", HS_PROC_PATTERN])
        if rc2 != 0 or not out2.strip():
            break
    else:
        for pid in pids:
            run(["/bin/kill", "-9", pid], 5)
        time.sleep(1)
    run([OPEN, "-a", "Hammerspoon"], 15)
    state["last_restart_ts"] = time.time()
    for _ in range(9):
        r, o, _ = hs('return "ok"', timeout=4)
        if r == 0 and o == "ok":
            break
        time.sleep(1)
    return True, "已重启 Hammerspoon"


def fix_service(label):
    uid = os.getuid()
    rc, _, err = run([LAUNCHCTL, "kickstart", "-k", f"gui/{uid}/{label}"], 15)
    if rc == 0:
        return True, "已 kickstart 重拉"
    plist = os.path.join(LAUNCH_AGENTS, label + ".plist")
    if os.path.exists(plist):
        rc2, _, err2 = run([LAUNCHCTL, "bootstrap", f"gui/{uid}", plist], 15)
        if rc2 == 0:
            return True, "已 bootstrap 重新注册"
        return False, f"kickstart/bootstrap 均失败: {err.strip()[:40]} | {err2.strip()[:40]}"
    return False, f"kickstart 失败且 plist 缺失: {err.strip()[:60]}"


# ---------- 主流程 ----------
def main():
    argv = set(sys.argv[1:])
    do_fix = "--fix" in argv
    do_notify = "--notify" in argv
    quiet = "--quiet" in argv

    state = load_state()
    prev_version = state.get("last_version")

    # 检查清单: (key, label, fn)
    checks = [
        ("app", "Hammerspoon App", check_app),
        ("cli", "hs CLI 符号链接", check_cli),
        ("proc", "Hammerspoon 进程", check_proc),
        ("ipc", "IPC（hs -c）通道", check_ipc),
        ("ax", "辅助功能授权", check_ax),
        ("lua", "焦点脚本部署", check_lua),
        ("init", "init.lua IPC 块", check_init),
        ("smoke", "焦点脚本可加载", check_smoke),
    ]
    for label, short in SERVICES:
        checks.append((f"svc:{label}", f"服务 {short}", (lambda l=label: check_service(l))))

    def eval_all():
        return [(k, lab, *fn()) for k, lab, fn in checks]

    results = eval_all()

    # 修复阶段（按依赖顺序分阶段，每阶段后复检）
    fixes_applied = []   # (label, msg)
    if do_fix:
        phases = [
            ["cli", "lua", "init"],                       # 文件/链接层
            ["proc"],                                     # 进程层
            ["ipc"],                                      # IPC 层（含限速重启）
            [k for k, _, _ in checks if k.startswith("svc:")],  # 服务层
        ]
        for phase in phases:
            failing = {k for k, _, ok, _ in results if not ok}
            for key in phase:
                if key not in failing:
                    continue
                if key == "cli":
                    ok, msg = fix_cli()
                elif key == "lua":
                    ok, msg = fix_lua()
                elif key == "init":
                    ok, msg = fix_init()
                elif key == "proc":
                    ok, msg = fix_proc()
                elif key == "ipc":
                    # 仅当 CLI/进程/init 层已通过时才尝试重启（避免误判与无谓重启）
                    cur = {k: ok for k, _, ok, _ in results}
                    if not (cur.get("cli") and cur.get("proc") and cur.get("init")):
                        continue
                    ok, msg = fix_ipc_restart(state)
                elif key.startswith("svc:"):
                    ok, msg = fix_service(key[4:])
                else:
                    continue
                if ok:
                    fixes_applied.append((key, msg))
            results = eval_all()

    unresolved = [(lab, det) for k, lab, ok, det in results if not ok]
    fixed_labels = [lab for k, lab, ok, det in results
                    if ok and any(k == fk for fk, _ in fixes_applied)]

    # ---- 输出 ----
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    n_ok = sum(1 for *_, ok, _ in results if ok)
    ver_now = next((det for k, _, ok, det in results if k == "app" and ok), "?")

    lines = []
    if unresolved or fixes_applied or not quiet:
        lines.append(f"[hs_health v1.0] {now}")
        if prev_version and ver_now != "?" and prev_version != ver_now.lstrip("v"):
            lines.append(f"  （注: Hammerspoon 已从 {prev_version} 更新到 {ver_now.lstrip('v')}）")
        for k, lab, ok, det in results:
            mark = "✓" if ok else "✗"
            lines.append(f"  {mark} {lab}: {det}")
        if fixes_applied:
            lines.append("  ── 已自动修复 ──")
            for k, msg in fixes_applied:
                lines.append(f"    · {k}: {msg}")
        if unresolved:
            lines.append(f"  结果: {n_ok}/{total} 正常；{len(unresolved)} 项需处理")
        else:
            lines.append(f"  结果: {n_ok}/{total} 全部正常" + ("（含自动修复）" if fixes_applied else ""))
    else:
        lines.append(f"{now} OK {n_ok}/{total} hs={ver_now}")

    for ln in lines:
        print(ln)
    sys.stdout.flush()

    # ---- 通知 ----
    if do_notify and (fixes_applied or unresolved):
        prefix = ""
        if prev_version and ver_now != "?" and prev_version != ver_now.lstrip("v"):
            prefix = f"Hammerspoon 更新 {prev_version}→{ver_now.lstrip('v')}。"
        unresolved_labels = [lab for lab, _ in unresolved]
        if fixes_applied and unresolved:
            title = "遥控器链路守卫 · 部分已修复"
            text = prefix + f"已自动修复：{'、'.join(fixed_labels)}；仍需处理：{'、'.join(unresolved_labels)}。"
        elif fixes_applied:
            title = "遥控器链路守卫 · 已自动修复"
            text = prefix + f"检测到异常（{'、'.join(fixed_labels)}），已自动修复，无需操作。"
        else:
            title = "遥控器链路需要处理"
            text = prefix + f"异常未解决：{'、'.join(unresolved_labels)}。"
            if any(k == "ax" for k, _, ok, _ in results if not ok):
                text += "请在 系统设置→隐私与安全性→辅助功能 中重新勾选 Hammerspoon。"
        n_ok2, n_err = notify(title, text)
        print(f"  [notify] {'已发出' if n_ok2 else '发送失败'} | {title} | {n_err[:50] if not n_ok2 else ''}")
        sys.stdout.flush()

    # ---- 状态落盘 ----
    state["last_run_ts"] = time.time()
    if ver_now != "?":
        state["last_version"] = ver_now.lstrip("v")
    if unresolved:
        state["last_result"] = "PARTIAL" if fixes_applied else "ISSUES"
    else:
        state["last_result"] = "FIXED" if fixes_applied else "OK"
    state["last_ok_count"] = f"{n_ok}/{total}"
    save_state(state)

    return 0 if not unresolved else 1


if __name__ == "__main__":
    sys.exit(main())
