#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""close_app_test.py — Mac「关闭当前应用」（APP:CLOSE）源码约定静态测试
---------------------------------------------------------------
覆盖（v1.12 / v1.2 交付的纵深约定, 防未来回归）:
  · key_bridge v1.12: close 子命令路由 / CLOSE_DEBOUNCE=2.0 强防抖 / 免 focus assist
    / 版本号 / banner 与接收串 / docstring
  · app_switch v1.2: close 调度分支 / doClose / Finder 保护 / terminate 语义 / 用法串
用法: python3 close_app_test.py   （无需网络; 只读源码断言）
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
kb = open(os.path.join(HERE, "key_bridge.py"), encoding="utf-8").read()
sw = open(os.path.join(HERE, "app_switch.swift"), encoding="utf-8").read()

ok = [0]
fail = [0]


def check(name, got, want=True):
    if got == want:
        ok[0] += 1
        print("  PASS %s" % name)
    else:
        fail[0] += 1
        print("  FAIL %s: got=%r want=%r" % (name, got, want))


# ---------------- key_bridge v1.12 ----------------
check("kb 标题 v1.12", "# key_bridge.py — Mac 端「遥控器按键」注入桥 v1.12 (2026-10-12)" in kb)
check("kb changelog v1.12 段", "v1.12（10-12）: 新增 APP:CLOSE" in kb)
check("kb VERSION=1.12", 'VERSION = "1.12"' in kb)
check("kb CLOSE_DEBOUNCE=2.0", re.search(r"CLOSE_DEBOUNCE\s*=\s*2\.0", kb) is not None)
check("kb close 走强防抖分支", 'd = CLOSE_DEBOUNCE if v.lower() == "close" else APP_DEBOUNCE' in kb)
check("kb close 映射 app_switch 子命令", '("toggle", "next", "cycle", "close")' in kb)
check("kb close 免 focus assist", 'if r.returncode == 0 and v.lower() != "close":' in kb)
check("kb docstring 含 CLOSE", "TOGGLE|NEXT|CYCLE|CLOSE" in kb)
check("kb banner 含 关闭", "APP动作(切换/轮询/选择器/关闭)" in kb)
check("kb 接收串含 PICK|CLOSE", "PICK|CLOSE DOWN" in kb)

# ---------------- app_switch v1.2 ----------------
check("sw 标题 v1.2", "「应用切换器」 v1.2 (2026-10-12)" in sw)
check("sw changelog v1.2 段", "v1.2（10-12）: 新增 close" in sw)
check("sw doClose 函数", "func doClose() -> Never" in sw)
check("sw Finder 保护", ("com.apple.finder" in sw) and ("Finder 为系统组件, 拒绝关闭" in sw))
check("sw terminate 调用", "front.terminate()" in sw)
check("sw 调度分支 close", 'case "close":' in sw)
check("sw 用法串含 close", "cycle|zlist|close" in sw)
check("sw 子命令说明含 close", "关闭当前前台应用（优雅退出; 长按电源键 #116 生产绑定）" in sw)

print("\n== close_app_test: %d PASS / %d FAIL ==" % (ok[0], fail[0]))
raise SystemExit(1 if fail[0] else 0)
