#!/bin/bash
# T1 安全上电恢复脚本 (Mac 侧执行)
# 用途: 用户重新给 T1 上电后, 第一时间隔离蓝牙并收集死机现场证据
# 背景: 2026-10-08 12:35-12:40 遥控器"抢连拉锯"后 T1 失联(疑复现历史: BT/HOG 异常→卡死/复位循环)
set -u
T1=t1root

echo "=== [0] 等待 T1 上线 (最多 6 分钟) ==="
UP=0
for i in $(seq 1 72); do
  if ssh -o ConnectTimeout=4 -o BatchMode=yes "$T1" 'echo up' >/dev/null 2>&1; then
    echo ">>> T1 已上线 (探测 ${i}/72) $(date +%T)"
    UP=1
    break
  fi
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "!!! 6 分钟未上线, 请检查电源/网线/指示灯"
  exit 1
fi

echo
echo "=== [1] 立即隔离蓝牙 (停看护+服务+hci0) ==="
ssh "$T1" 'systemctl stop t1bt-bluetooth.service; systemctl stop bluetooth; sleep 1; hciconfig hci0 down 2>/dev/null || btmgmt -i hci0 power off 2>/dev/null; echo "t1bt 服务: $(systemctl is-active t1bt-bluetooth.service)"; echo "bluetooth 服务: $(systemctl is-active bluetooth)"; hciconfig hci0 2>/dev/null | head -3 || echo "hci0 已下线"'

echo
echo "=== [2] 看护/持有进程残留 ==="
ssh "$T1" 'ps aux | grep -E "t1bt-btinit|btflow" | grep -v grep || echo "(无残留)"'

echo
echo "=== [3] 启动历史 (是否复位循环) ==="
ssh "$T1" 'journalctl --list-boots --no-pager 2>/dev/null | tail -10; echo "--- last reboot ---"; last reboot 2>/dev/null | head -6; echo "--- uptime ---"; uptime'

echo
echo "=== [4] 上次启动日志尾部 (死机现场) ==="
ssh "$T1" 'journalctl -b -1 --no-pager 2>/dev/null | tail -150'

echo
echo "=== [5] 内核异常关键词 ==="
ssh "$T1" 'journalctl -b -1 --no-pager 2>/dev/null | grep -iE "watchdog|panic|oops|BUG:|hung task|blocked for|thermal|reset" | tail -50'

echo
echo "=== [6] 轮询日志尾部 (抢连拉锯证据, /root 持久) ==="
ssh "$T1" 'tail -80 /root/remote-hub/steal_test.log 2>/dev/null || echo "(无)"'

echo
echo "=== [7] btmon 日志 (若 /tmp 为 tmpfs 可能已丢) ==="
ssh "$T1" 'ls -la /tmp/btmon_steal.log 2>/dev/null && tail -150 /tmp/btmon_steal.log || echo "(无/已丢失)"'

echo
echo "=== [8] 当前 dmesg 尾部 ==="
ssh "$T1" 'dmesg 2>/dev/null | tail -50'

echo
echo "=== [9] 温度 ==="
ssh "$T1" 'cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -5'

echo
echo ">>> 恢复脚本执行完毕 $(date +%T)"
