#!/usr/bin/env python3
# speech_forensics.py — Chatterfly(腾讯输入法) 语音历史取证：每段录音的时长/大小/码率 + 状态对账
# 用法: python speech_forensics.py [最近N条, 默认45]
import os
import sqlite3
import sys
from datetime import datetime, timedelta

BASE = os.path.expanduser(
    "~/Library/Application Support/Chatterfly/InputMethod/ChatterflyPY.users/00000001/speech_data")
DB = os.path.join(BASE, "speech_history", "localstore.db")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 45


def ts(ms):
    if not ms:
        return "-"
    return (datetime.utcfromtimestamp(ms / 1000) + timedelta(hours=8)).strftime("%m-%d %H:%M:%S")


def resolve(path):
    if not path:
        return None
    if os.path.isabs(path) and os.path.exists(path):
        return path
    p1 = os.path.join(BASE, path)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(BASE, "speech_audio_file", os.path.basename(path))
    if os.path.exists(p2):
        return p2
    return None


db = sqlite3.connect(DB)
c = db.cursor()

print("== 按天/状态分布 ==")
for d, st, n in c.execute(
        "SELECT date(rec_start_at/1000,'unixepoch','+8 hours') d, status, COUNT(*) "
        "FROM voice_history GROUP BY d, status ORDER BY d DESC LIMIT 40"):
    print(f"  {d}  {st:12s} {n}")

print()
print(f"== 最近 {N} 条明细（码率 = 文件大小/录音时长）==")
print(f"{'id':>4} {'开始时刻':>14} {'时长':>7} {'KB':>7} {'B/s':>7}  status      file")
for r in c.execute(
        f"SELECT id, audio_relpath, status, rec_start_at, rec_end_at "
        f"FROM voice_history ORDER BY id DESC LIMIT {N}"):
    i, path, st, s, e = r
    fp = resolve(path)
    size = os.path.getsize(fp) if fp else -1
    dur = (e - s) / 1000 if (e and s) else 0
    bps = size / dur if dur else 0
    bn = os.path.basename(path)[:30] if path else "-"
    print(f"{i:>4} {ts(s):>14} {dur:>6.2f}s {size/1024:>6.1f}K {bps:>7.0f}  {st:11s} {bn}")

print()
print("== 最近 20 条 success ==")
for r in c.execute(
        "SELECT id, audio_relpath, rec_start_at, rec_end_at FROM voice_history "
        "WHERE status='success' ORDER BY id DESC LIMIT 20"):
    i, path, s, e = r
    fp = resolve(path)
    size = os.path.getsize(fp) if fp else -1
    dur = (e - s) / 1000 if (e and s) else 0
    bps = size / dur if dur else 0
    bn = os.path.basename(path)[:34] if path else "-"
    print(f"{i:>4} {ts(s):>14} {dur:>6.2f}s {size/1024:>6.1f}K {bps:>7.0f}  {bn}")

print()
print("== 最近 15 条 failed_asr ==")
for r in c.execute(
        "SELECT id, audio_relpath, rec_start_at, rec_end_at FROM voice_history "
        "WHERE status='failed_asr' ORDER BY id DESC LIMIT 15"):
    i, path, s, e = r
    fp = resolve(path)
    size = os.path.getsize(fp) if fp else -1
    dur = (e - s) / 1000 if (e and s) else 0
    bps = size / dur if dur else 0
    bn = os.path.basename(path)[:34] if path else "-"
    print(f"{i:>4} {ts(s):>14} {dur:>6.2f}s {size/1024:>6.1f}K {bps:>7.0f}  {bn}")

print()
print("== input_context 最近 12 条（当时聚焦的 App）==")
try:
    for r in c.execute("SELECT id, app, time FROM input_context ORDER BY id DESC LIMIT 12"):
        i, app, t = r
        print(f"{i:>4} {ts(t):>14}  {app}")
except Exception as ex:
    print("  err:", ex)
