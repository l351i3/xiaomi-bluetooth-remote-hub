#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# presence_beater.py — Mac 端「presence 心跳」独立常驻 v1.0 (2026-10-14)
#
# 【为何独立进程 + 必须系统 python】macOS 27 本地网络隐私实测（10-14）:
#   · launchd 拉起、ad-hoc 签名的解释器（.workbuddy/binaries 的 python）向
#     局域网出站被系统拦截（UDP/TCP 均 EHOSTUNREACH 或静默丢）——三服务内联
#     心跳方案不可行（03:2x 实测），故独立进程;
#   · Apple 签名的 /usr/bin/python3 在 launchd 上下文被放行（实测: UDP 出站
#     到达 + ACK 回程 6ms; TCP 5ms×3 稳定）——故本进程必须用 /usr/bin/python3
#     运行（见 plist ProgramArguments）。
#   · 依据: Apple TN3179 (Local Network Privacy) —— 系统签名二进制获自动放行，
#     第三方 ad-hoc 二进制需本地网络授权; 佐证: launchd 上下文 curl 200 实测。
#
# 职责: 代表 Mac 整机向 T1 presence 服务（UDP :8790）注册心跳 ——
#   role=mac, svcs=(voice:8788, key:8791, audio:8789);
#   启动即拍（首拍=IP 学习源）→ 2s/拍; 无 ACK 自适应退避（presence_beat 逻辑）。
#   供 T1 侧投递闸门判定「体面断开 / 优雅连上」与地址学习。
#
# 运行: launchd com.remotehub.presence-beater（RunAtLoad + KeepAlive）
#   (手动: /usr/bin/python3 -u presence_beater.py)
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import presence_beat  # noqa: E402


def main():
    hb = presence_beat.start(
        "mac",
        [("voice", 8788), ("key", 8791), ("audio", 8789)],
        log_fn=lambda m: print(time.strftime("[%m-%d %H:%M:%S] ") + m, flush=True),
    )
    print("presence_beater v1.0 就绪: role=mac [voice:8788,key:8791,audio:8789] -> %s:%d"
          % (hb.host, hb.port), flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
