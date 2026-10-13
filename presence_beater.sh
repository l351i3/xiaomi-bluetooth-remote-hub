#!/bin/bash
# presence_beater.sh — Mac 端「presence 心跳」v2.1（bash + nc 形态） 2026-10-14
#
# 【为何是 bash + nc】macOS 27 本地网络隐私（Local Network Privacy）实测（10-14）:
#   launchd 上下文里，解释器发出的 LAN 出站被系统拦截 ——
#   · .workbuddy 的 python（ad-hoc 签名）: 全拦（EHOSTUNREACH / 静默丢）;
#   · 系统 /usr/bin/python3（xcode shim / CLT 身份）: 同样被拦（UDP 出+ACK 回、TCP 全试）;
#   · 系统自带网络工具 /usr/bin/nc、/usr/bin/curl: **被放行**（实测 nc UDP 双向全通
#     含 ACK 回程; curl HTTP 200）—— 与 Apple TN3179「系统二进制获自动放行」一致。
#   故 beater 采用「bash 循环 + /usr/bin/nc」形态。python 版留档: presence_beater.py
#   （该路径在本机被拦，仅备将来环境变化时参考）。
#
# v2.1（10-14）: 发送改为「后台并发」，主循环不再等待 nc（macOS nc 只认整数 -w，
#   一次调用至少等满 1s；前台收集 3 个 svc = 3s+/轮，节奏贴边）。现在:
#   · 每 2s 一轮、3 svc 后台并发发出（各等满 1s 自退，不阻塞）；
#   · 每 30 轮（≈60s）做一次 ACK 深探（前台 1s），维持链路健康观测。
#   效果: 每 svc 心跳间隔 ~2s（T1 侧 6s 离线阈值 → 3 倍余量）。
#
# 职责: 代表 Mac 整机向 T1 presence 服务（UDP :8790）注册心跳 ——
#   role=mac, svcs=voice:8788 / key:8791 / audio:8789。
#
# 运行: launchd com.remotehub.presence-beater（RunAtLoad + KeepAlive）
#   (手动: bash presence_beater.sh)
HOST="${PRESENCE_HOST:-T1_IP}"
PORT="${PRESENCE_PORT:-8790}"
SVCS=("voice 8788" "key 8791" "audio 8789")

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

log "presence-beater(bash+nc) v2.1 启动: role=mac -> $HOST:$PORT [voice:8788,key:8791,audio:8789] (2s 节拍; 60s ACK 深探)"
misses=0
rounds=0
while :; do
    for s in "${SVCS[@]}"; do
        printf 'PRESENCE mac %s\n' "$s" | /usr/bin/nc -u -w 1 "$HOST" "$PORT" >/dev/null 2>&1 &
    done
    rounds=$((rounds + 1))
    if [ $((rounds % 30)) -eq 0 ]; then
        resp=$(printf 'PRESENCE mac voice 8788\n' | /usr/bin/nc -u -w 1 "$HOST" "$PORT" 2>/dev/null)
        case "$resp" in
            *PRESENCE-ACK*)
                if [ "$misses" -gt 0 ]; then
                    log "presence: ACK 已恢复（此前连续 miss=$misses）"
                    misses=0
                fi ;;
            *)
                misses=$((misses + 1))
                if [ "$misses" -eq 1 ] || [ $((misses % 10)) -eq 0 ]; then
                    log "presence: 深探无 ACK x$misses（心跳照发; 每 10 次提示）"
                fi ;;
        esac
    fi
    sleep 2
done
