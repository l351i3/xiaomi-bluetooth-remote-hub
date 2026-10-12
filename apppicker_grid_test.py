#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apppicker_grid_test.py — AppPicker.swift gridMove 逻辑测试
   从源码提取真实函数（零漂移）→ 生成 Swift 测试主程序 → swiftc 编译运行。
   用例 = win_actions(grid_move) 33 例的逐一移植（同语义对账）。
   跑法: python3 apppicker_grid_test.py   （任意 python3; 需 swiftc 可用）"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "AppPicker.swift")
TMP_SWIFT = "/tmp/_apppicker_grid_test.swift"
TMP_BIN = "/tmp/_apppicker_grid_test"

src = open(SRC, encoding="utf-8").read()

# --- 源码约定守护（防回改/防漂移）---
assert 'sel = gridMove(sel, cmd, cols: cols, n: apps.count)' in src, "handleCmd 未接入 gridMove"
assert 'case "LEFT", "RIGHT", "UP", "DOWN":' in src, "移动路由 case 缺失"

# --- 提取 func gridMove 完整函数（到其后首个顶格 '}'）---
m = re.search(r"(?ms)^func gridMove\([^\n]*\n.*?^}\s*$", src)
if not m:
    print("!! gridMove not found in AppPicker.swift")
    sys.exit(1)
fn = m.group(0)
assert "let rows" in fn and "cnt" in fn and "base + (cnt - 1)" in fn, "gridMove 提取不完整"
print("提取 gridMove: %d 字符" % len(fn))

# --- 33 用例（与 windows/actions_offline_test.py 15) 段对齐）---
CASES = [
    ("两行 ↓ 同列", 0, "DOWN", 3, 5, 3),
    ("两行 ↓ 同列（第二列）", 1, "DOWN", 3, 5, 4),
    ("两行 ↓ 末行该列空缺 → 最近列", 2, "DOWN", 3, 5, 4),
    ("两行 ↑ 同列", 4, "UP", 3, 5, 1),
    ("两行 ↑ 同列（第三列）", 3, "UP", 3, 5, 0),
    ("首行 ↑ 回绕末行同列", 0, "UP", 3, 5, 3),
    ("首行 ↑ 回绕末行（第二列）", 1, "UP", 3, 5, 4),
    ("末行 ↓ 回绕首行同列", 3, "DOWN", 3, 5, 0),
    ("末行 ↓ 回绕首行（第二列）", 4, "DOWN", 3, 5, 1),
    ("← 行尾跨到上一行尾", 3, "LEFT", 3, 5, 2),
    ("← 首项回绕", 0, "LEFT", 3, 5, 4),
    ("→ 行尾跨到下一行首", 2, "RIGHT", 3, 5, 3),
    ("→ 末项回绕", 4, "RIGHT", 3, 5, 0),
    ("7/6 ↓ 到末行唯一格", 1, "DOWN", 6, 7, 6),
    ("7/6 首格 ↓ 末行同列", 0, "DOWN", 6, 7, 6),
    ("7/6 ↑ 回绕首行同列", 6, "UP", 6, 7, 0),
    ("7/6 末行再 ↓ 回绕", 6, "DOWN", 6, 7, 0),
    ("7/6 → 行尾跨行", 5, "RIGHT", 6, 7, 6),
    ("7/6 ← 行首跨行", 6, "LEFT", 6, 7, 5),
    ("9/6 ↓ 最近列（3→8）", 3, "DOWN", 6, 9, 8),
    ("9/6 ↑ 同列（8→2）", 8, "UP", 6, 9, 2),
    ("9/6 ↓ 同列（1→7）", 1, "DOWN", 6, 9, 7),
    ("9/6 ↓ 回移（7→1）", 7, "DOWN", 6, 9, 1),
    ("9/6 首行 ↑ 回绕末行同列（2→8）", 2, "UP", 6, 9, 8),
    ("单行 ↓ 线性 +1", 0, "DOWN", 5, 5, 1),
    ("单行 ↑ 线性 -1（回绕）", 0, "UP", 5, 5, 4),
    ("单列 ↓ 线性 +1", 1, "DOWN", 1, 3, 2),
    ("单列 ↑ 线性 -1（回绕）", 0, "UP", 1, 3, 2),
    ("n=0 安全", 3, "DOWN", 3, 0, 0),
    ("n=1 恒 0", 0, "UP", 3, 1, 0),
    ("非法 action 原地", 2, "FOO", 3, 5, 2),
    ("cols 非法按单列", 1, "DOWN", 0, 3, 2),
    ("sel 越界取模安全", 7, "DOWN", 3, 5, 4),
]

# --- 组装 Swift 测试主程序（用 + 拼接避开转义）---
body = []
body.append("import Foundation")
body.append("")
body.append(fn)
body.append("")
body.append("var pass = 0, fail = 0")
body.append("func check(_ name: String, _ got: Int, _ want: Int) {")
body.append('    if got == want { pass += 1; print("  ok  " + name) }')
body.append('    else { fail += 1; print("  FAIL " + name + ": got " + String(got) + " want " + String(want)) }')
body.append("}")
for name, sel, act, cols, n, exp in CASES:
    body.append('check("%s", gridMove(%d, "%s", cols: %d, n: %d), %d)' % (name, sel, act, cols, n, exp))
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
print("(用例数 = %d; 提取自 %s)" % (len(CASES), os.path.basename(SRC)))
sys.exit(r2.returncode)
