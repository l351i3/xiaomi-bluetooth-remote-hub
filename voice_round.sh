#!/bin/bash
# voice_round.sh — Mac 端语音合成 全链验收脚本 v1.0
# 用途: IOHIDPostEvent 注入右⌥/右⌘ 两个语音快捷键, 验证 Chatterfly 接收合成按键 → 录音 → 识别 → 上屏
# 用法: ./voice_round.sh [每轮说话秒数, 默认7]
# 流程: 聽到 Tink=准备, Ping=开始说话, Glass=结束. 全程自动核对计数器.
cd "$(dirname "$0")"
SECS=${1:-7}
D=com.tencent.inputmethod.chatterfly
PING=/System/Library/Sounds/Ping.aiff
TINK=/System/Library/Sounds/Tink.aiff
GLASS=/System/Library/Sounds/Glass.aiff

cnt() { defaults read $D "$1" 2>/dev/null; }

echo "============ Mac 语音输入 全链验收 ============"
echo "两轮: ① 右⌥ 点按式(语音输入)  ② 右⌘ 按住式(语音指令)"
echo "听到 Tink=准备, Ping=开始说话, Glass=结束。"
echo "请把光标放在输入框里。10 秒后开始第一轮……"
sleep 10

# ---------- 回合1: 右⌥ 点按式 ----------
echo ""
echo "▶ 回合1: 右⌥ 点按式（语音输入）"
b1=$(cnt YBSpeechShortcutStartCount_voice)
afplay $TINK
sleep 2
afplay $PING
./iohid_post ropt-tap1
echo "[$(date +%H:%M:%S)] tap#1 已发（开始录音，说 ${SECS} 秒）"
sleep "$SECS"
afplay $GLASS
./iohid_post ropt-tap1
echo "[$(date +%H:%M:%S)] tap#2 已发（结束录音，等待识别上屏…）"
sleep 4
a1=$(cnt YBSpeechShortcutStartCount_voice)
echo "→ voice 计数: $b1 -> $a1"

# ---------- 回合2: 右⌘ 按住式 ----------
echo ""
echo "▶ 回合2: 右⌘ 按住式（语音指令）"
echo "准备……"
afplay $TINK
sleep 2
b2=$(cnt YBSpeechShortcutStartCount_voiceCommand)
afplay $PING
echo "[$(date +%H:%M:%S)] 开始按住（说 ${SECS} 秒）"
./iohid_post rcmd-hold "$SECS"
afplay $GLASS
echo "[$(date +%H:%M:%S)] 已松开（等待识别上屏…）"
sleep 4
a2=$(cnt YBSpeechShortcutStartCount_voiceCommand)
echo "→ voiceCommand 计数: $b2 -> $a2"

echo ""
echo "============ 结果 ============"
echo "voice: $b1 -> $a1    voiceCommand: $b2 -> $a2"
echo "请检查输入框是否出现两段识别文字。"
