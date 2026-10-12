#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小米蓝牙遥控器切换 — 切换 T1（斐讯盒子）上小米蓝牙遥控器的行为目标。

用法:
  python3 switch.py atv|mac|win     # 切换（也认口语别名：电视/apple tv/macos/电脑/windows/笔记本…）
  python3 switch.py status          # 查看当前目标

原理: POST http://<T1>:8765/api/voice_target {"target": …}，再 GET /api/state 复核。
环境变量 T1_WEBUI 可覆盖地址（默认 T1_IP:8765，备选 127.0.0.1:8765）。
退出码: 0=成功 / 1=参数错 / 2=连不上 T1 / 3=服务端拒绝 / 4=复核未生效
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_HOSTS = ["T1_IP:8765", "127.0.0.1:8765"]
HOSTS = [os.environ["T1_WEBUI"]] if os.environ.get("T1_WEBUI") else DEFAULT_HOSTS
VALID = ("atv", "mac", "win")

# 口语别名（精确匹配用；子串兜底在下方的 KW 表）
ALIAS = {
    "atv": "atv", "tv": "atv", "电视": "atv", "apple tv": "atv", "appletv": "atv",
    "apple-tv": "atv", "apple 电视": "atv",
    "mac": "mac", "macos": "mac", "电脑": "mac",
    "macos 主机": "mac",
    "win": "win", "windows": "win", "笔记本": "win",
}
STATUS_HINTS = ("status", "state", "状态", "查询", "当前", "模式")

# 子串扫描（认「帮我切到电视」这类整句）；顺序即优先级
KW = (
    ("atv", ("atv", "apple tv", "appletv", "电视", "tv")),
    ("win", ("windows", "笔记本", "win")),
    ("mac", ("macos", "mac", "电脑")),
)


def log(msg):
    print(msg, flush=True)


def call(method, path, payload=None):
    """对 T1 控制台发请求；地址逐个尝试。返回解析后的 dict（或 {"raw": …}）。"""
    last_err = None
    for host in HOSTS:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            "http://%s%s" % (host, path), data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                raw = resp.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except ValueError:
                return {"raw": raw}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(body)
                if isinstance(j, dict) and not j.get("ok", True):
                    log("FAIL 服务端拒绝: %s" % j.get("error", body[:200]))
                    sys.exit(3)
            except ValueError:
                pass
            last_err = "HTTP %s %s" % (e.code, body[:120])
            break  # T1 可达但报错 → 换地址没有意义
        except Exception as e:  # noqa: BLE001 —— 连接类错误，尝试下一个地址
            last_err = repr(e)
            continue
    if last_err and last_err.startswith("HTTP"):
        log("FAIL 请求失败: %s" % last_err)
    else:
        log("FAIL 无法连接 T1（%s）: %s" % (", ".join(HOSTS), last_err))
        log("提示: 确认 T1（T1_IP）在线、网页控制台（8765）在运行")
    sys.exit(2)


def get_state():
    return call("GET", "/api/state").get("voice_target")


def resolve(arg):
    """识别目标；返回 atv/mac/win，识别不了返回 None。"""
    if arg in VALID:
        return arg
    if arg in ALIAS:
        return ALIAS[arg]
    for target, words in KW:
        if any(w in arg for w in words):
            return target
    return None


def main():
    arg = " ".join(sys.argv[1:]).strip().lower()
    if not arg or arg in ("-h", "--help", "help", "帮助"):
        log("用法: switch.py <atv|mac|win|status>（口语: 电视 / apple tv / macos / 电脑 / windows / 笔记本…）")
        return 0
    if arg in STATUS_HINTS or any(h in arg for h in STATUS_HINTS):
        t = get_state()
        log("OK target=%s" % t)
        return 0
    target = resolve(arg)
    if target is None:
        log("FAIL 无法识别的目标: %r（可选: atv/mac/win）" % arg)
        return 1
    r = call("POST", "/api/voice_target", {"target": target})
    if isinstance(r, dict) and r.get("ok") is False:
        log("FAIL %s" % r.get("error", r))
        return 3
    t = get_state()
    if t == target:
        log("OK target=%s" % t)
        return 0
    log("FAIL 切换未生效（期望 %s, 实际 %s）" % (target, t))
    return 4


if __name__ == "__main__":
    sys.exit(main())
