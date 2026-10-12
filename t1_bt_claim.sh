#!/bin/bash
# t1_bt_claim.sh — T1 抢占遥控器连接（Mac 释放后运行）
# 用法: bash /tmp/t1_bt_claim.sh [最大轮数, 默认 15]
# 逻辑: 每轮先查 Connected; 未连则 connect; 成功即报 CLAIM_OK 退出; 全失败报 CLAIM_FAILED
TARGET="C0:5D:39:XX:XX:XX"
TRIES="${1:-15}"
info() { timeout 6 bluetoothctl info "$TARGET" 2>/dev/null; }
for i in $(seq 1 "$TRIES"); do
    if info | grep -q "Connected: yes"; then
        echo "$(date '+%F %T') CLAIM_OK(pre) try=$i"
        info | grep -E "Alias:|Connected:|Paired:|Trusted:"
        exit 0
    fi
    out=$(timeout 12 bluetoothctl connect "$TARGET" 2>&1 | tail -1)
    if info | grep -q "Connected: yes"; then
        echo "$(date '+%F %T') CLAIM_OK try=$i ($out)"
        info | grep -E "Alias:|Connected:|Paired:|Trusted:"
        exit 0
    fi
    echo "$(date '+%F %T') try=$i => $out"
    sleep 2
done
echo "$(date '+%F %T') CLAIM_FAILED (after $TRIES tries)"
exit 1
