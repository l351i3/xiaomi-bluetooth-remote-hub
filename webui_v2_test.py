#!/usr/bin/env python3
"""t1_webui v2.17 离线全量测试（临时目录副本起服务 :18765, 不碰生产配置）"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

SRC = os.path.dirname(os.path.abspath(__file__))  # 自动定位（仓库克隆后任意位置可跑）
TMP = "/tmp/webui_v2_test"
PY = sys.executable
PORT = 18765
BASE = f"http://127.0.0.1:{PORT}"

ok = [0]
fail = [0]


def check(name, got, want):
    if got == want:
        ok[0] += 1
        print(f"  PASS {name}: {got}")
    else:
        fail[0] += 1
        print(f"  FAIL {name}: got={got} want={want}")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def post(path, obj, rev="auto"):
    """v2.7: /api/keymap 默认自动带最新 rev（模拟正常页面保存）。
    rev=None → 不带指纹（测 409）；rev='<字符串>' → 显式注入（测过期快照）。"""
    if path == "/api/keymap" and rev is not None:
        if rev == "auto":
            _, d = get("/api/keymap")
            rev = d["rev"]
        obj = dict(obj)
        obj["rev"] = rev
    data = json.dumps(obj).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def read_file_cfg():
    with open(os.path.join(TMP, "keymap.json")) as f:
        return json.load(f)


def main():
    # 布置临时目录：t1_webui.py(换端口) + v2 默认 + v1 现网(模拟迁移前)
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)
    code = open(os.path.join(SRC, "t1_webui.py")).read().replace("PORT = 8765", f"PORT = {PORT}")
    with open(os.path.join(TMP, "t1_webui.py"), "w") as f:
        f.write(code)
    shutil.copy(os.path.join(SRC, "keymap.default.json"), TMP)
    v1 = {"version": 1, "hold_threshold": 0.6, "double_window": 0.3, "keys": {
        "63": {"label": "语音", "locked": True, "note": "x", "single": None, "double": None, "long": None, "repeat": False},
        "102": {"label": "主页", "single": "home", "double": None, "long": "home_hold", "repeat": False},
        "158": {"label": "返回", "single": "menu", "double": None, "long": None, "repeat": False},
        "103": {"label": "上", "single": "up", "double": None, "long": None, "repeat": True},
        "108": {"label": "下", "single": "down", "double": None, "long": None, "repeat": True},
        "105": {"label": "左", "single": "left", "double": None, "long": None, "repeat": True},
        "106": {"label": "右", "single": "right", "double": None, "long": None, "repeat": True},
        "28": {"label": "OK", "single": "select", "double": None, "long": None, "repeat": False},
        "115": {"label": "音量+", "single": "volume_up", "double": None, "long": None, "repeat": True},
        "114": {"label": "音量-", "single": "volume_down", "double": None, "long": None, "repeat": True},
        "116": {"label": "电源", "single": "__POWER__", "double": None, "long": None, "repeat": False},
        "41": {"label": "直播", "single": "__LAUNCH__:com.zentraedi.zspaceTV", "double": None, "long": None, "repeat": False},
        "127": {"label": "菜单", "single": "__PLAY_PAUSE__", "double": None, "long": None, "repeat": False},
    }}
    with open(os.path.join(TMP, "keymap.json"), "w") as f:
        json.dump(v1, f, ensure_ascii=False)
    with open(os.path.join(TMP, "voice_target"), "w") as f:
        f.write("atv\n")
    shutil.copy(os.path.join(SRC, "presence.py"), TMP)   # v2.16: /api/presence 依赖同目录 presence.py
    # v2.17: fake busctl（模式文件驱动: 缺省 fail / ok / disc）注入 PATH，测 /api/remote 双路
    os.makedirs(os.path.join(TMP, "bin"))
    shim = f'''#!/bin/sh
mode=$(cat "{TMP}/busctl_mode" 2>/dev/null)
case "$mode" in
  ok)
    case "$*" in
      *Battery1*) echo '{{"type":"y","data":77}}' ;;
      *Connected*) echo '{{"type":"b","data":true}}' ;;
      *) exit 1 ;;
    esac ;;
  disc)
    case "$*" in
      *Battery1*) echo '{{"type":"y","data":88}}' ;;
      *Connected*) echo '{{"type":"b","data":false}}' ;;
      *) exit 1 ;;
    esac ;;
  *) exit 1 ;;
esac
'''
    shim_path = os.path.join(TMP, "bin", "busctl")
    with open(shim_path, "w") as f:
        f.write(shim)
    os.chmod(shim_path, 0o755)
    srv_env = dict(os.environ)
    srv_env["PATH"] = os.path.join(TMP, "bin") + os.pathsep + srv_env.get("PATH", "")

    srv = subprocess.Popen([PY, "-u", "t1_webui.py"], cwd=TMP, env=srv_env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                get("/api/state")
                break
            except Exception:
                time.sleep(0.1)

        # 1. 读: v1 现网 -> 归一化为 v2
        _, d = get("/api/keymap")
        check("GET v1归一化 targets", sorted(d["cfg"]["targets"].keys()), ["atv", "mac", "win"])
        check("GET atv OK=select", d["cfg"]["targets"]["atv"]["keys"]["28"]["single"], "select")
        check("GET choices mac 含 ENTER", ["ENTER", "回车"] in d["choices"]["mac"], True)

        # 2. 主页/配置页 HTML 可达
        with urllib.request.urlopen(BASE + "/", timeout=5) as r:
            html = r.read().decode()
        check("主页含三按钮", all(x in html for x in ["ATV", "macOS", "Windows"]), True)
        with urllib.request.urlopen(BASE + "/keymap", timeout=5) as r:
            html2 = r.read().decode()
        check("配置页含三 tab", all(x in html2 for x in ['data-t="atv"', 'data-t="mac"', 'data-t="win"']), True)

        # 3. 保存 mac 份（OK=ENTER/返回=ESC/方向/102 空了）
        st, r = post("/api/keymap", {"target": "mac", "hold_threshold": 0.6, "double_window": 0.3, "keys": {
            "28": {"single": "ENTER", "repeat": False},
            "158": {"single": "ESC", "repeat": False},
            "103": {"single": "UP", "repeat": True},
        }})
        cfg = read_file_cfg()
        check("保存 mac ok", [st, r["ok"]], [200, True])
        check("落盘 mac OK=ENTER", cfg["targets"]["mac"]["keys"]["28"]["single"], "ENTER")
        check("落盘 atv 未被触碰(28=select)", cfg["targets"]["atv"]["keys"]["28"]["single"], "select")
        check("落盘 其他键保持默认(108=DOWN)", cfg["targets"]["mac"]["keys"]["108"]["single"], "DOWN")

        # 4. mac 份: 双击强制置空; 长按（v2.3）解禁保留
        post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "ENTER", "double": "ESC", "long": "TAB"}}})
        cfg = read_file_cfg()
        check("mac 双击强制空", cfg["targets"]["mac"]["keys"]["28"]["double"], None)
        check("mac 长按保留(v2.3)", cfg["targets"]["mac"]["keys"]["28"]["long"], "TAB")

        # 5. 校验拒绝: mac 份用 ATV 动作 / atv 份用键盘动作
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "home"}}})
        check("mac 拒绝 home", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "atv", "keys": {"28": {"single": "ENTER"}}})
        check("atv 拒绝 ENTER", [st, r["ok"]], [400, False])

        # 5b. mac 份 APP: 应用动作（v2.1 新增）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:TOGGLE"}}})
        cfg = read_file_cfg()
        check("mac 接受 APP:TOGGLE", [st, r["ok"], cfg["targets"]["mac"]["keys"]["102"]["single"]],
              [200, True, "APP:TOGGLE"])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:微信"}}})
        cfg = read_file_cfg()
        check("mac 接受 APP:中文名", cfg["targets"]["mac"]["keys"]["102"]["single"], "APP:微信")
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:"}}})
        check("mac 拒绝 APP:空后缀", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:bad name"}}})
        check("mac 拒绝 APP:带空格", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "atv", "keys": {"28": {"single": "APP:TOGGLE"}}})
        check("atv 拒绝 APP:TOGGLE", [st, r["ok"]], [400, False])
        check("choices mac 含 APP:TOGGLE", ["APP:TOGGLE", "★ 切换应用 · 最近两个间跳（≈⌘Tab）"] in d["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:CYCLE"}}})
        cfg = read_file_cfg()
        check("mac 接受 APP:CYCLE", [st, r["ok"], cfg["targets"]["mac"]["keys"]["102"]["single"]],
              [200, True, "APP:CYCLE"])
        check("choices mac 含 APP:CYCLE", ["APP:CYCLE", "★ 切换应用 · 全部轮询（连按依次遍历）"] in d["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "APP:CYCLE", "long": "APP:PICK"}}})
        cfg = read_file_cfg()
        check("mac 接受长按 APP:PICK", [st, r["ok"], cfg["targets"]["mac"]["keys"]["102"]["single"], cfg["targets"]["mac"]["keys"]["102"]["long"]],
              [200, True, "APP:CYCLE", "APP:PICK"])
        check("choices mac 含 APP:PICK", ["APP:PICK", "★ 应用选择器（唤出列表 · 左右选 · OK 打开）"] in d["choices"]["mac"], True)
        check("choices mac 含自定义入口", ["__CUSTOM_APP__", "打开应用…（自定义输入）"] in d["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "__CUSTOM_APP__"}}})
        check("mac 拒绝自定义占位落盘", [st, r["ok"]], [400, False])

        # 6. [v2.15] atv 63 解锁可自由改绑; mac 63 仍锁定（按住说话语音链保护）
        post("/api/keymap", {"target": "atv", "keys": {"63": {"single": "home"}, "28": {"single": "skip_forward"}}})
        cfg = read_file_cfg()
        check("atv 63 解锁可改 -> home", cfg["targets"]["atv"]["keys"]["63"]["single"], "home")
        check("atv 28 改为 skip_forward", cfg["targets"]["atv"]["keys"]["28"]["single"], "skip_forward")
        post("/api/keymap", {"target": "mac", "keys": {"63": {"single": "ENTER"}}})
        cfg = read_file_cfg()
        check("mac 63 locked 保护", cfg["targets"]["mac"]["keys"]["63"]["single"], None)

        # 7. repeat 键清 double/long（atv 103 配 double 被清）
        post("/api/keymap", {"target": "atv", "keys": {"103": {"single": "up", "double": "menu"}}})
        cfg = read_file_cfg()
        check("repeat 清 double", cfg["targets"]["atv"]["keys"]["103"]["double"], None)
        post("/api/keymap", {"target": "mac", "keys": {"103": {"single": "LEFT", "long": "APP:PICK", "repeat": True}}})
        cfg = read_file_cfg()
        check("mac repeat 键清 long", [cfg["targets"]["mac"]["keys"]["103"]["single"], cfg["targets"]["mac"]["keys"]["103"]["long"]], ["LEFT", None])

        # 8. 分目标 reset: 改动 mac 102 后 reset mac, atv 改动保留
        post("/api/keymap", {"target": "mac", "keys": {"102": {"single": "SPACE"}}})
        st, r = post("/api/keymap/reset", {"target": "mac"})
        cfg = read_file_cfg()
        check("reset mac ok", [st, r["ok"]], [200, True])
        check("reset 后 mac 102.single=APP:CYCLE(新默认)", cfg["targets"]["mac"]["keys"]["102"]["single"], "APP:CYCLE")
        check("reset 后 mac 102.long=APP:PICK(新默认)", cfg["targets"]["mac"]["keys"]["102"]["long"], "APP:PICK")
        check("reset 后 atv 保留改动(skip_forward)", cfg["targets"]["atv"]["keys"]["28"]["single"], "skip_forward")

        # 9. 阈值钳制
        post("/api/keymap", {"target": "atv", "hold_threshold": 5, "double_window": 0.05,
                             "keys": {"28": {"single": "select"}}})
        cfg = read_file_cfg()
        check("阈值钳制", [cfg["hold_threshold"], cfg["double_window"]], [2.0, 0.15])

        # 10. 全部 reset（无 target）→ 与默认一致
        st, r = post("/api/keymap/reset", {})
        cfg = read_file_cfg()
        dflt = json.load(open(os.path.join(TMP, "keymap.default.json")))
        check("全部 reset ok", [st, r["ok"]], [200, True])
        check("全部 reset == 默认", json.dumps(cfg, sort_keys=True), json.dumps(dflt, sort_keys=True))

        # 11. voice_target 切换
        st, r = post("/api/voice_target", {"target": "mac"})
        check("目标切换", [st, r["voice_target"]], [200, "mac"])

        # 12. v2.4: 长按列「⟳ 按住连发」哨兵（__REPEAT__ = repeat 连发 UI 化）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"158": {"single": "BACKSPACE", "long": "__REPEAT__", "repeat": True}}})
        cfg = read_file_cfg()
        m158 = cfg["targets"]["mac"]["keys"]["158"]
        check("mac 哨兵被接受", [st, r["ok"]], [200, True])
        check("哨兵->repeat=True", m158["repeat"], True)
        check("哨兵->long=None", m158["long"], None)
        # 哨兵 + double 互斥（atv 上双清验证）
        post("/api/keymap", {"target": "atv", "keys": {"103": {"single": "up", "double": "menu", "long": "__REPEAT__"}}})
        a103 = read_file_cfg()["targets"]["atv"]["keys"]["103"]
        check("atv 哨兵->repeat=True", a103["repeat"], True)
        check("atv 哨兵清 double", a103["double"], None)
        check("atv 哨兵清 long", a103["long"], None)
        # 撤回：改回空长按（模拟前端：显式送 repeat=False）
        post("/api/keymap", {"target": "mac", "keys": {"158": {"single": "BACKSPACE", "long": None, "repeat": False}}})
        check("撤回哨兵 repeat=False", read_file_cfg()["targets"]["mac"]["keys"]["158"]["repeat"], False)
        # single 位置送哨兵应被拒（哨兵仅长按列合法）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"158": {"single": "__REPEAT__"}}})
        check("single 拒哨兵", [st, r["ok"]], [400, False])
        # GET 响应含 repeat_opt（前端下拉数据源）
        _, d2 = get("/api/keymap")
        check("GET repeat_opt", d2.get("repeat_opt"), ["__REPEAT__", "⟳ 按住连发（连续重复）"])

        # 13. v2.5: FOCUS_INPUT「跳转输入框」（mac/win 键盘动作白名单扩展）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"41": {"single": "FOCUS_INPUT"}}})
        cfg = read_file_cfg()
        check("mac 接受 FOCUS_INPUT", [st, r["ok"], cfg["targets"]["mac"]["keys"]["41"]["single"]],
              [200, True, "FOCUS_INPUT"])
        _, d3 = get("/api/keymap")
        check("choices mac 含 FOCUS_INPUT",
              ["FOCUS_INPUT", "★ 跳转输入框（聚焦输入框 · 修复失焦）"] in d3["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "atv", "keys": {"41": {"single": "FOCUS_INPUT"}}})
        check("atv 拒绝 FOCUS_INPUT", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "win", "keys": {"41": {"single": "FOCUS_INPUT"}}})
        check("win 接受 FOCUS_INPUT", [st, r["ok"]], [200, True])

        # 14. v2.6: CLICK「点击焦点元素」（mac/win 键盘动作白名单扩展）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "CLICK"}}})
        cfg = read_file_cfg()
        check("mac 接受 CLICK", [st, r["ok"], cfg["targets"]["mac"]["keys"]["28"]["single"]],
              [200, True, "CLICK"])
        _, d4 = get("/api/keymap")
        check("choices mac 含 CLICK",
              ["CLICK", "★ 点击（激活当前焦点元素 · 任务/列表项）"] in d4["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "atv", "keys": {"28": {"single": "CLICK"}}})
        check("atv 拒绝 CLICK", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "win", "keys": {"28": {"single": "CLICK"}}})
        check("win 接受 CLICK", [st, r["ok"]], [200, True])

        # 15. v2.7: 配置指纹（防旧页面回写；POST 需带匹配的 rev）
        st, d5 = get("/api/keymap")
        check("GET 含 rev(12hex)", isinstance(d5.get("rev"), str) and len(d5["rev"]) == 12, True)
        rev0 = d5["rev"]
        # 带最新 rev 正常保存 -> 200 + 新 rev
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "TAB"}}}, rev="auto")
        check("带最新 rev 保存 ok", [st, r["ok"]], [200, True])
        check("响应含新 rev 且变化", isinstance(r.get("rev"), str) and r["rev"] != rev0, True)
        rev1 = r["rev"]
        check("保存已落盘(mac 28=TAB)", read_file_cfg()["targets"]["mac"]["keys"]["28"]["single"], "TAB")
        # 过期 rev（旧页面快照）保存 -> 409 且不落盘
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "SPACE"}}}, rev=rev0)
        check("过期 rev 被拒 409", [st, r["ok"]], [409, False])
        check("409 未落盘(mac 28 仍=TAB)", read_file_cfg()["targets"]["mac"]["keys"]["28"]["single"], "TAB")
        # 不带 rev -> 409
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "SPACE"}}}, rev=None)
        check("缺 rev 被拒 409", [st, r["ok"]], [409, False])
        # 新 rev 可用
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "SPACE"}}}, rev=rev1)
        check("新 rev 可用", [st, r["ok"]], [200, True])
        rev2 = r["rev"]
        # 同内容重复保存 -> rev 稳定（语义指纹）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"28": {"single": "SPACE"}}}, rev="auto")
        check("同内容保存 rev 稳定", [st, r["ok"], r["rev"]], [200, True, rev2])

        # 16. v2.8: PAGEUP/PAGEDOWN「翻页」（mac/win 键盘动作白名单扩展）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"127": {"single": "PAGEDOWN"}}})
        check("mac 接受 PAGEDOWN", [st, r["ok"], read_file_cfg()["targets"]["mac"]["keys"]["127"]["single"]],
              [200, True, "PAGEDOWN"])
        _, d6 = get("/api/keymap")
        check("choices mac 含 PAGEDOWN", ["PAGEDOWN", "★ 下一页（PageDown）"] in d6["choices"]["mac"], True)
        check("choices mac 含 PAGEUP", ["PAGEUP", "★ 上一页（PageUp）"] in d6["choices"]["mac"], True)
        st, r = post("/api/keymap", {"target": "atv", "keys": {"127": {"single": "PAGEDOWN"}}})
        check("atv 拒绝 PAGEDOWN", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "win", "keys": {"127": {"single": "PAGEUP"}}})
        check("win 接受 PAGEUP", [st, r["ok"]], [200, True])

        # 17. v2.9: /keymap 初始 tab 跟随当前激活目标（数据面 + 页面引用）
        st, r = post("/api/voice_target", {"target": "win"})
        check("POST voice_target=win", [st, r.get("ok"), r.get("voice_target")], [200, True, "win"])
        _, s2 = get("/api/state")
        check("GET state 回读 win", s2["voice_target"], "win")
        st, r = post("/api/voice_target", {"target": "atv"})
        check("还原 voice_target=atv", [st, r.get("ok")], [200, True])
        check("配置页含 boot()（v2.9）", "boot()" in html2, True)
        check("配置页引用 /api/state（v2.9）", "/api/state" in html2, True)

        # 18. v2.10: URL: / RUN: 扩展动作（遥控一键开网页/跑命令）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "URL:https://www.baidu.com"}}})
        cfg = read_file_cfg()
        check("mac 接受 URL:前缀", [st, r["ok"], cfg["targets"]["mac"]["keys"]["116"]["single"]],
              [200, True, "URL:https://www.baidu.com"])
        st, r = post("/api/keymap", {"target": "win", "keys": {"116": {"single": "RUN:/path/to/MyScript.sh"}}})
        check("win 接受 RUN:前缀(大小写保真)",
              [st, r["ok"], read_file_cfg()["targets"]["win"]["keys"]["116"]["single"]],
              [200, True, "RUN:/path/to/MyScript.sh"])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "URL:"}}})
        check("mac 拒绝 URL:空后缀", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "RUN:bad cmd"}}})
        check("mac 拒绝 RUN:带空格", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "atv", "keys": {"116": {"single": "URL:https://a.b"}}})
        check("atv 拒绝 URL:", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "URL:" + "u" * 501}}})
        check("mac 拒绝超长(值>500)", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "URL:" + "u" * 500}}})
        check("mac 接受恰 500 值长", [st, r["ok"]], [200, True])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "__CUSTOM_URL__"}}})
        check("mac 拒绝自定义URL占位落盘", [st, r["ok"]], [400, False])
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "__CUSTOM_RUN__"}}})
        check("mac 拒绝自定义RUN占位落盘", [st, r["ok"]], [400, False])
        _, d8 = get("/api/keymap")
        check("choices mac 含自定义网页入口",
              ["__CUSTOM_URL__", "打开网页…（自定义输入）"] in d8["choices"]["mac"], True)
        check("choices mac 含自定义命令入口",
              ["__CUSTOM_RUN__", "执行命令…（自定义输入）"] in d8["choices"]["mac"], True)

        # 19. v2.11: APP:CLOSE（长按电源键关闭当前应用）
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "APP:workbuddy", "long": "APP:CLOSE"}}})
        cfg = read_file_cfg()
        check("mac 接受 APP:CLOSE", [st, r["ok"], cfg["targets"]["mac"]["keys"]["116"]["long"]],
              [200, True, "APP:CLOSE"])
        st, r = post("/api/keymap", {"target": "win", "keys": {"116": {"single": "APP:workbuddy", "long": "APP:CLOSE"}}})
        check("win 接受 APP:CLOSE",
              [st, r["ok"], read_file_cfg()["targets"]["win"]["keys"]["116"]["long"]],
              [200, True, "APP:CLOSE"])
        st, r = post("/api/keymap", {"target": "atv", "keys": {"116": {"long": "APP:CLOSE"}}})
        check("atv 拒绝 APP:CLOSE", [st, r["ok"]], [400, False])
        _, d9 = get("/api/keymap")
        check("choices mac 含 APP:CLOSE",
              ["APP:CLOSE", "★ 关闭当前应用（长按电源键）"] in d9["choices"]["mac"], True)
        check("配置页含 extLabel 特判（v2.11）",
              "关闭当前应用（长按电源键）" in html2, True)

        # 20. v2.14: TARGET:SWITCH「★ 电源（连击切设备）」（三份动作清单扩展; 电源键重定义）
        _, d10 = get("/api/keymap")
        check("choices mac 含 TARGET:SWITCH",
              ["TARGET:SWITCH", "★ 电源（连击切设备：1 击=ATV · 2 击=Mac · 3 击=Windows; 长按=关闭应用）"]
              in d10["choices"]["mac"], True)
        check("choices atv 含 TARGET:SWITCH",
              ["TARGET:SWITCH", "★ 电源（连击切设备：1 击=电视电源 · 2 击=Mac · 3 击=Windows）"]
              in d10["choices"]["atv"], True)
        check("choices mac 含 MOUSE:TOGGLE（v2.13 补录）",
              ["MOUSE:TOGGLE", "★ 鼠标模式开/关（长按直播; 方向=移光标 · OK=点击 · 音量=滚动）"]
              in d10["choices"]["mac"], True)
        check("atv __POWER__ 新标注（立即，无连击）",
              ["__POWER__", "电源切换（立即，无连击）"] in d10["choices"]["atv"], True)
        # 三份校验均接受 TARGET:SWITCH
        st, r = post("/api/keymap", {"target": "mac", "keys": {"116": {"single": "TARGET:SWITCH"}}})
        check("mac 接受 TARGET:SWITCH",
              [st, r["ok"], read_file_cfg()["targets"]["mac"]["keys"]["116"]["single"]],
              [200, True, "TARGET:SWITCH"])
        st, r = post("/api/keymap", {"target": "win", "keys": {"116": {"single": "TARGET:SWITCH"}}})
        check("win 接受 TARGET:SWITCH",
              [st, r["ok"], read_file_cfg()["targets"]["win"]["keys"]["116"]["single"]],
              [200, True, "TARGET:SWITCH"])
        st, r = post("/api/keymap", {"target": "atv", "keys": {"116": {"single": "TARGET:SWITCH"}}})
        check("atv 接受 TARGET:SWITCH",
              [st, r["ok"], read_file_cfg()["targets"]["atv"]["keys"]["116"]["single"]],
              [200, True, "TARGET:SWITCH"])
        # reset 回到默认: 默认三份 #116.single=TARGET:SWITCH + 长按=APP:CLOSE + note 在场
        st, r = post("/api/keymap/reset", {"target": "mac"})
        cfg = read_file_cfg()
        check("reset mac 后 #116=默认(连击网关)",
              [st, r["ok"], cfg["targets"]["mac"]["keys"]["116"]["single"],
               cfg["targets"]["mac"]["keys"]["116"]["long"]],
              [200, True, "TARGET:SWITCH", "APP:CLOSE"])
        check("默认 mac #116 note 在场",
              "连击切换设备" in (cfg["targets"]["mac"]["keys"]["116"].get("note") or ""), True)
        check("默认 atv #116.single=TARGET:SWITCH",
              cfg["targets"]["atv"]["keys"]["116"]["single"], "TARGET:SWITCH")
        check("配置页含 extLabel 特判（v2.14）",
              "★ 电源（连击切设备）" in html2, True)
        # ---- v2.16: /api/presence（设备在线状态; 降级安全）----
        st, r = get("/api/presence")
        check("无 presence.json -> available=False（降级）", [st, r.get("available")], [200, False])
        check("降级 devices 为空", r.get("devices"), {})
        st_dir = os.path.join(TMP, "state")
        os.makedirs(st_dir, exist_ok=True)
        now_t = time.time()
        snap = {"v": 1, "ts": now_t, "pid": 1, "ttl": 6.0, "confirm_switch": 12.0,
                "confirm_restore": 10.0,
                "devices": {
                    "atv": {"ip": "T1_IP", "state": "online", "last_seen": now_t - 1,
                            "since": now_t - 100, "svcs": {"relay": {"port": 0, "last_seen": now_t - 1}}},
                    "mac": {"ip": "MACOS_IP", "state": "online", "last_seen": now_t - 2,
                            "since": now_t - 100, "svcs": {"voice": {"port": 8788, "last_seen": now_t - 2}}},
                    "win": {"ip": "WINDOWS_IP", "state": "offline", "last_seen": now_t - 30,
                            "since": now_t - 30, "svcs": {"voice": {"port": 8788, "last_seen": now_t - 30}}}},
                "target": "mac", "desired": "mac", "auto": False, "hostname": "t", "events": []}
        with open(os.path.join(st_dir, "presence.json"), "w") as f:
            json.dump(snap, f)
        st, r = get("/api/presence")
        check("有效快照 -> available=True", [st, r.get("available")], [200, True])
        check("三设备齐全", sorted((r.get("devices") or {}).keys()), ["atv", "mac", "win"])
        check("mac state=online", r["devices"]["mac"]["state"], "online")
        check("win offline + age 28-32s", 28 <= r["devices"]["win"]["age"] <= 32, True)
        check("ip 透传", r["devices"]["win"]["ip"], "WINDOWS_IP")
        snap["ts"] = now_t - 200          # 过期（>max_age 90s）-> 降级
        with open(os.path.join(st_dir, "presence.json"), "w") as f:
            json.dump(snap, f)
        st, r = get("/api/presence")
        check("过期快照 -> available=False", [st, r.get("available")], [200, False])
        check("主页含 devbar（v2.16）", 'id="devbar"' in html, True)
        check("主页引用 /api/presence（v2.16）", "/api/presence" in html, True)
        # ---- v2.17: /api/remote（遥控器电量; 降级安全 + fake busctl 三态）----
        st, r = get("/api/remote")
        check("busctl 失败 -> available=False（降级）", [st, r.get("available")], [200, False])
        check("降级 percent=None / connected=False", [r.get("percent"), r.get("connected")], [None, False])
        check("降级 note 在场", "未连接" in (r.get("note") or ""), True)
        with open(os.path.join(TMP, "busctl_mode"), "w") as f:
            f.write("ok")
        st, r = get("/api/remote")
        check("busctl ok -> 77% 在线", [st, r.get("available"), r.get("connected"), r.get("percent")],
              [200, True, True, 77])
        check("ok 模式无 note", "note" not in r, True)
        with open(os.path.join(TMP, "busctl_mode"), "w") as f:
            f.write("disc")
        st, r = get("/api/remote")
        check("disc -> 缓存 88% / connected=False",
              [r.get("available"), r.get("connected"), r.get("percent")], [True, False, 88])
        check("主页含 renderBatt（v2.17）", "renderBatt" in html, True)
        check("主页引用 /api/remote（v2.17）", "/api/remote" in html, True)
        check("电量 10s 轮询（v2.17）", "setInterval(refreshRemoteBattery, 10000)" in html, True)
        check("主页含遥控器文案（v2.17）", "🎮 遥控器" in html, True)
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=3)
        except Exception:
            srv.kill()

    print(f"\n== 结果: {ok[0]} PASS / {fail[0]} FAIL ==")
    return 0 if fail[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
