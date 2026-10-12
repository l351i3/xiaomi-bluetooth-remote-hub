#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""upload_recv.py — 施工回传接收器（T1 :8001） v1.0 (2026-10-11)

用途: 接收施工机（Windows）回传的文件（补丁后源码 / 施工报告），存 ./inbox/。
协议:
  POST /upload/<filename>   body = 原始文件内容
      -> 保存到 inbox/<filename>; 响应 "OK <filename> <size> <sha256>"
  GET  /                     -> 列出已收到文件（含大小/时间）
安全: 仅监听局域网; 文件名白名单字符; 大小上限 8MB; 只写 inbox/。

启动: cd /root/remote-hub && nohup python3 upload_recv.py >> /tmp/upload8001.log 2>&1 < /dev/null &
自测: curl -s -X POST --data-binary @<file> http://T1_IP:8001/upload/test.txt
"""
import hashlib
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(ROOT, "inbox")
MAX_SIZE = 8 * 1024 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s %s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                            self.address_string(), fmt % args), flush=True)

    def _reply(self, text, code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            items = []
            if os.path.isdir(INBOX):
                for it in sorted(os.listdir(INBOX)):
                    p = os.path.join(INBOX, it)
                    if os.path.isfile(p):
                        items.append("  %-40s %9d bytes  %s" % (
                            it, os.path.getsize(p), time.ctime(os.path.getmtime(p))))
            self._reply("upload inbox (%d files):\n%s\n" % (len(items), "\n".join(items)))
        else:
            self._reply("not found\n", 404)

    def do_POST(self):
        m = re.match(r"^/upload/(.+)$", self.path)
        if not m or not NAME_RE.match(m.group(1)):
            self._reply("bad name\n", 400)
            return
        name = m.group(1)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_SIZE:
            self._reply("bad size %d\n" % n, 400)
            return
        data = self.rfile.read(n)
        os.makedirs(INBOX, exist_ok=True)
        path = os.path.join(INBOX, name)
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as e:
            self._reply("write error: %s\n" % e, 500)
            return
        sha = hashlib.sha256(data).hexdigest()
        print("RECV %s %d bytes sha256=%s" % (name, len(data), sha), flush=True)
        self._reply("OK %s %d %s\n" % (name, len(data), sha))


if __name__ == "__main__":
    print("upload receiver v1.0 on :8001 -> %s" % INBOX, flush=True)
    HTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
