#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apppicker_name_test.py — AppPicker.swift 长名截断/跑马灯逻辑测试（v1.3）
   从源码提取真实 fitPrefix / cycleSlice 函数（零漂移）→ 生成 Swift 测试主程序 → swiftc 编译运行。
   用例 = win_actions（fit_prefix 6 + cycle_slice 7）逐一对齐移植 + Mac 中文/越界 3 条 = 16 条。
   跑法: python3 apppicker_name_test.py   （任意 python3; 需 swiftc 可用）"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "AppPicker.swift")
TMP_SWIFT = "/tmp/_apppicker_name_test.swift"
TMP_BIN = "/tmp/_apppicker_name_test"

src = open(SRC, encoding="utf-8").read()

# --- 源码约定守护（防回改/防漂移）---
assert 'let NAME_BUDGET' in src, "NAME_BUDGET 常量缺失"
assert 'let MARQUEE_MS' in src, "MARQUEE_MS 常量缺失"
assert 'marqueeOff = (marqueeOff + 1) % (fullNames[sel].count + 3)' in src, "跑马灯步进未接入"
assert 'nameLabels[i].stringValue = displayName(i, on: on)' in src, "updateHighlight 文本未接入"
assert 'fitPrefix(nm, budget: NAME_BUDGET, measure: measureName)' in src, "非选中截断未接入"
assert 'cycleSlice(nm, offset: marqueeOff, budget: NAME_BUDGET, measure: measureName)' in src, "选中跑马灯未接入"
assert '.byClipping' in src, "label 截断模式未切换到 byClipping"

# --- 提取 func fitPrefix / func cycleSlice（到其后首个顶格 '}'）---
fns = []
for name in ("fitPrefix", "cycleSlice"):
    m = re.search(r"(?ms)^func %s\([^\n]*\n.*?^}\s*$" % name, src)
    if not m:
        print("!! %s not found in AppPicker.swift" % name)
        sys.exit(1)
    fn = m.group(0)
    assert "return" in fn and "budget" in fn, "%s 提取不完整" % name
    fns.append(fn)
    print("提取 %s: %d 字符" % (name, len(fn)))

# --- 16 用例（13 条移植自 windows/actions_offline_test.py 14) 段 + 3 条 Mac 补充）---
FIT = [
    ("短名原样", "Calc", 50, "Calc"),
    ("长名加省略号", "ABCDEFGH", 50, "ABCD…"),
    ("省略号占宽（55px 仍 4 字）", "ABCDEFGH", 55, "ABCD…"),
    ("极窄保底 1 字", "ABCDEFGH", 19, "A…"),
    ("空名安全", "", 50, ""),
    ("恰好等于预算不截", "ABCDE", 50, "ABCDE"),
    ("中文截断", "微信输入法测试", 30, "微信…"),
]
CYC = [
    ("短名原样", "Calc", 3, 50, "Calc"),
    ("起点窗口", "ABCDEFGHIJKLM", 0, 50, "ABCDE"),
    ("推进 2 步", "ABCDEFGHIJKLM", 2, 50, "CDEFG"),
    ("尾段跨界（含分隔空格）", "ABCDEFGHIJKLM", 11, 50, "LM   "),
    ("环绕回起点", "ABCDEFGHIJKLM", 16, 50, "ABCDE"),
    ("环绕越界取模", "ABCDEFGHIJKLM", 18, 50, "CDEFG"),
    ("空名安全", "", 0, 50, ""),
    ("中文滚动窗口", "微信输入法测试", 0, 40, "微信输入"),
    ("大偏移取模", "ABCDEFGHIJKLM", 100, 50, "EFGHI"),
]

# --- 组装 Swift 测试主程序 ---
body = ["import Foundation", ""]
body.extend(fns)
body.append("")
body.append("func M10(_ s: String) -> CGFloat { CGFloat(10 * s.count) }")
body.append("var pass = 0, fail = 0")
body.append("func checkS(_ name: String, _ got: String, _ want: String) {")
body.append('    if got == want { pass += 1; print("  ok  " + name) }')
body.append('    else { fail += 1; print("  FAIL " + name + ": got [" + got + "] want [" + want + "]") }')
body.append("}")
for name, nm, budget, exp in FIT:
    body.append('checkS("%s", fitPrefix("%s", budget: %s, measure: M10), "%s")'
                % (name, nm, budget, exp))
for name, nm, off, budget, exp in CYC:
    body.append('checkS("%s", cycleSlice("%s", offset: %d, budget: %s, measure: M10), "%s")'
                % (name, nm, off, budget, exp))
body.append('print("== 结果: " + String(pass) + " PASS / " + String(fail) + " FAIL ==")')
body.append("exit(fail == 0 ? 0 : 1)")
open(TMP_SWIFT, "w", encoding="utf-8").write("\n".join(body) + "\n")

# --- 编译并运行 ---
r = subprocess.run(["/usr/bin/swiftc", "-swift-version", "5", TMP_SWIFT, "-o", TMP_BIN],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("!! swiftc 编译失败:")
    print(r.stderr)
    sys.exit(1)
r2 = subprocess.run([TMP_BIN], capture_output=True, text=True)
print(r2.stdout, end="")
if r2.stderr.strip():
    print("[stderr]", r2.stderr.strip())
print("(用例数 = %d; 提取自 %s)" % (len(FIT) + len(CYC), os.path.basename(SRC)))
sys.exit(r2.returncode)
