#!/bin/bash
# 小米 RC003 遥控器配对探针 (在 T1 上运行)
# 用法:
#   rc_probe.sh scan        扫描 20 秒, 列出发现的设备
#   rc_probe.sh pair <MAC>  配对+信任+连接 指定设备, 并导出 input 设备信息
set -u
LOG=/root/remote-hub/rc_probe.log
mkdir -p /root/remote-hub

cmd="${1:-scan}"

case "$cmd" in
scan)
    {
    echo "===== $(date '+%F %T') 扫描 ====="
    timeout 25 bluetoothctl --timeout 20 scan on 2>&1 | grep -aE "\[NEW\]|\[CHG\]" | tail -80
    echo "----- 当前已知设备表 -----"
    bluetoothctl devices 2>&1
    } | tee -a "$LOG"
    ;;
pair)
    MAC="${2:?用法: rc_probe.sh pair <MAC>}"
    {
    echo "===== $(date '+%F %T') 配对 $MAC ====="
    echo "--- 停止扫描 ---"
    bluetoothctl scan off 2>/dev/null || true
    echo "--- 配对 (交互会话 + Just Works agent) ---"
    timeout 90 bluetoothctl <<BTEOF
power on
agent NoInputNoOutput
default-agent
pair $MAC
trust $MAC
connect $MAC
info $MAC
quit
BTEOF
    sleep 2
    echo "--- 复检 info ---"
    bluetoothctl info "$MAC" 2>&1
    echo "--- /dev/input 节点 ---"
    ls -la /dev/input/
    echo "--- 输入设备名称列表 ---"
    for d in /sys/class/input/event*; do
        [ -e "$d" ] && echo "$d: $(cat "$d/device/name" 2>/dev/null)"
    done
    echo "--- HID 相关模块 ---"
    lsmod | grep -E "hid|uhid" | head -10
    } | tee -a "$LOG"
    ;;
*)
    echo "用法: $0 {scan|pair <MAC>}"; exit 1;;
esac
