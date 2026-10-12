// ════════════════════════════════════════════════════════════════════
// ⚠️⚠️⚠️ 生产件保护（2026-10-10 血泪教训，修改前务必读完）⚠️⚠️⚠️
//
//  本目录下的 ./iohid_post 二进制是语音链的生产注入器。它的
//  PostEvent 授权绑定「文件路径 + cdhash」——用本源码重新编译并覆盖
//  ./iohid_post，会立即导致新 cdhash 与系统 TCC 记录失配，表现为：
//  job 照跑、IOHIDPostEvent 返回 kr=0x0，但事件被系统静默丢弃
//  → 遥控器语音键彻底失效（launchd 侧）。2026-10-10 14:15 曾因此
//  重编译一次，15:37 起故障、15:55 恢复旧字节后修复。
//
//  纪律（必须遵守）：
//   1. 禁止重编译覆盖 ./iohid_post（生产路径）。
//   2. 生产正确字节 = iohid_post.bak-20261010-precombo
//      sha256 = 81db49dd0e18b120e33b7dec00beba342b68cdc53316c2a991ab9618be18ce23
//   3. 本文件里 gkeyf/gcombo（组合键 CGEventPost 扩展）等实验性代码，
//      只许编译成独立文件名（如 ./iohid_post_test）或打包为新 .app
//      bundle，不得覆盖生产件。
//   4. macOS 27 对裸二进制 TCC 匹配不可靠；长期方向 = 仿 CGPost.app
//      的「App Bundle + 弹窗授权 + 冻结」形态（新通道再迁移）。
// ════════════════════════════════════════════════════════════════════
//
// iohid_post.c — HID 层按键注入原型 (IOHIDPostEvent) v0.1
// 目的: 绕过 CGEvent 合成的 srcPid 脚印, 验证 HID 层注入能否被 Chatterfly 消费
// 编译: clang -O2 -Wno-deprecated-declarations -o iohid_post iohid_post.c \
//         -framework IOKit -framework CoreFoundation
// 用法:
//   iohid_post check                      查授权状态（PostEvent / ListenEvent）
//   iohid_post key  <nxkc> <0|1>           裸键 down(1)/up(0), 无 flags
//   iohid_post rcmd-hold <secs>            右⌘ 按住 secs 秒 (NX_KEYDOWN/UP 变体)
//   iohid_post rcmd-flags-hold <secs>      右⌘ 按住 (NX_FLAGSCHANGED 变体)
//   iohid_post rcmd-tap2 <gap_ms>          右⌘ 双点按 (KEYDOWN 变体)
//   iohid_post ropt-tap2 <gap_ms>          右⌥ 双点按 (KEYDOWN 变体)
//   iohid_post ropt-flags-tap2 <gap_ms>    右⌥ 双点按 (FLAGSCHANGED 变体)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/hidsystem/IOHIDLib.h>
#include <IOKit/hidsystem/event_status_driver.h>
#include <IOKit/hidsystem/IOLLEvent.h>
#include <CoreGraphics/CoreGraphics.h>   /* 2026-10-10: CGEventPost 带 flags 扩展 */

static io_connect_t g_conn = 0;

static io_connect_t hid_conn(void) {
    if (!g_conn) {
        io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault,
                                                       IOServiceMatching(kIOHIDSystemClass));
        if (!svc) { fprintf(stderr, "IOHIDSystem service not found\n"); exit(1); }
        kern_return_t kr = IOServiceOpen(svc, mach_task_self(), kIOHIDParamConnectType, &g_conn);
        IOObjectRelease(svc);
        if (kr != KERN_SUCCESS) { fprintf(stderr, "IOServiceOpen failed: 0x%x\n", kr); exit(1); }
    }
    return g_conn;
}

static void post(UInt32 type, UInt16 keyCode, UInt32 flags) {
    NXEventData d;
    memset(&d, 0, sizeof(d));
    d.key.keyCode = keyCode;
    d.key.origCharCode = keyCode;
    IOGPoint loc = {0, 0};
    kern_return_t kr = IOHIDPostEvent(hid_conn(), type, loc, &d,
                                      kNXEventDataVersion, flags, 0);
    printf("IOHIDPostEvent(type=%u[%s], key=%u, flags=0x%08x) -> kr=0x%x\n",
           type,
           type == NX_KEYDOWN ? "KEYDOWN" :
           type == NX_KEYUP ? "KEYUP" :
           type == NX_FLAGSCHANGED ? "FLAGS" : "?",
           keyCode, flags, kr);
    fflush(stdout);
}

static void msleep(int ms) { usleep(ms * 1000); }

/* ---- 2026-10-10 扩展: CGEventPost 带 flags 注入（组合键通道，Task#30）---- */
static void cgpost_key(int kc, int down, uint32_t flags) {
    CGEventSourceRef src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState);
    if (!src) { fprintf(stderr, "CGEventSourceCreate failed\n"); return; }
    CGEventRef ev = CGEventCreateKeyboardEvent(src, (CGKeyCode)kc, down != 0);
    if (ev) {
        CGEventSetFlags(ev, (CGEventFlags)flags);
        CGEventPost(kCGHIDEventTap, ev);
        printf("CGEventPost(kc=%d, down=%d, flags=0x%08x)\n", kc, down, flags);
        fflush(stdout);
        CFRelease(ev);
    }
    CFRelease(src);
}

#define KC_RCMD 54
#define KC_ROPT 61
#define FL_CMD_DOWN (NX_COMMANDMASK  | NX_DEVICERCMDKEYMASK)   /* 0x00100010 */
#define FL_OPT_DOWN (NX_ALTERNATEMASK | NX_DEVICERALTKEYMASK)  /* 0x00080040 */

static void tap_once(UInt32 keyCode, UInt32 downFlags, int useFlagsType) {
    if (useFlagsType) {
        post(NX_FLAGSCHANGED, keyCode, downFlags);
        msleep(80);
        post(NX_FLAGSCHANGED, keyCode, 0);
    } else {
        post(NX_KEYDOWN, keyCode, downFlags);
        msleep(80);
        post(NX_KEYUP, keyCode, 0);
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: iohid_post <mode> [args]  (check / key / rcmd-hold / rcmd-tap2 / ropt-tap2 / ropt-flags-tap2 / rcmd-flags-hold)\n");
        return 1;
    }
    const char *mode = argv[1];

    if (!strcmp(mode, "check")) {
        IOHIDAccessType aPost   = IOHIDCheckAccess(kIOHIDRequestTypePostEvent);
        IOHIDAccessType aListen = IOHIDCheckAccess(kIOHIDRequestTypeListenEvent);
        printf("PostEvent   access = %d  (0=granted 1=denied 2=unknown)\n", aPost);
        printf("ListenEvent access = %d\n", aListen);
        return 0;
    }

    if (!strcmp(mode, "request")) {
        // 触发系统授权弹窗（辅助功能/PostEvent），用户点"允许"后本上下文获得授权
        IOHIDAccessType aPost = IOHIDRequestAccess(kIOHIDRequestTypePostEvent);
        printf("PostEvent request -> access = %d (0=granted 1=denied 2=unknown)\n", aPost);
        return 0;
    }

    if (!strcmp(mode, "key")) {
        if (argc < 4) { fprintf(stderr, "key <nxkc> <0|1>\n"); return 1; }
        UInt16 kc = (UInt16)atoi(argv[2]);
        int down = atoi(argv[3]);
        post(down ? NX_KEYDOWN : NX_KEYUP, kc, 0);
        return 0;
    }

    if (!strcmp(mode, "rcmd-hold")) {
        double secs = argc > 2 ? atof(argv[2]) : 2.5;
        post(NX_KEYDOWN, KC_RCMD, FL_CMD_DOWN);
        msleep((int)(secs * 1000));
        post(NX_KEYUP, KC_RCMD, 0);
        return 0;
    }

    if (!strcmp(mode, "rcmd-flags-hold")) {
        double secs = argc > 2 ? atof(argv[2]) : 2.5;
        post(NX_FLAGSCHANGED, KC_RCMD, FL_CMD_DOWN);
        msleep((int)(secs * 1000));
        post(NX_FLAGSCHANGED, KC_RCMD, 0);
        return 0;
    }

    if (!strcmp(mode, "ropt-tap1")) {
        tap_once(KC_ROPT, FL_OPT_DOWN, 0);
        return 0;
    }
    if (!strcmp(mode, "rcmd-tap1")) {
        tap_once(KC_RCMD, FL_CMD_DOWN, 0);
        return 0;
    }
    if (!strcmp(mode, "ropt-down")) { post(NX_KEYDOWN, KC_ROPT, FL_OPT_DOWN); return 0; }
    if (!strcmp(mode, "ropt-up"))   { post(NX_KEYUP,   KC_ROPT, 0);           return 0; }
    if (!strcmp(mode, "rcmd-down")) { post(NX_KEYDOWN, KC_RCMD, FL_CMD_DOWN); return 0; }
    if (!strcmp(mode, "rcmd-up"))   { post(NX_KEYUP,   KC_RCMD, 0);           return 0; }
    if (!strcmp(mode, "rcmd-tap2")) {
        int gap = argc > 2 ? atoi(argv[2]) : 300;
        tap_once(KC_RCMD, FL_CMD_DOWN, 0);
        msleep(gap);
        tap_once(KC_RCMD, FL_CMD_DOWN, 0);
        return 0;
    }
    if (!strcmp(mode, "ropt-tap2")) {
        int gap = argc > 2 ? atoi(argv[2]) : 300;
        tap_once(KC_ROPT, FL_OPT_DOWN, 0);
        msleep(gap);
        tap_once(KC_ROPT, FL_OPT_DOWN, 0);
        return 0;
    }
    if (!strcmp(mode, "ropt-flags-tap2")) {
        int gap = argc > 2 ? atoi(argv[2]) : 300;
        tap_once(KC_ROPT, FL_OPT_DOWN, 1);
        msleep(gap);
        tap_once(KC_ROPT, FL_OPT_DOWN, 1);
        return 0;
    }

    if (!strcmp(mode, "gkeyf")) {
        if (argc < 5) { fprintf(stderr, "gkeyf <nxkc> <0|1> <flags>\n"); return 1; }
        cgpost_key(atoi(argv[2]), atoi(argv[3]), (uint32_t)strtoul(argv[4], NULL, 0));
        return 0;
    }

    if (!strcmp(mode, "gcombo")) {
        /* gcombo <mainkc> <modflag> [gap_ms]: 左⌘down(带flags) -> 主键down/up(带flags) -> 左⌘up */
        if (argc < 4) { fprintf(stderr, "gcombo <mainkc> <modflag> [gap_ms]\n"); return 1; }
        int kc = atoi(argv[2]);
        uint32_t mf = (uint32_t)strtoul(argv[3], NULL, 0);
        int gap = argc > 4 ? atoi(argv[4]) : 40;
        cgpost_key(55, 1, mf);
        msleep(40);
        cgpost_key(kc, 1, mf);
        msleep(gap);
        cgpost_key(kc, 0, mf);
        msleep(40);
        cgpost_key(55, 0, 0);
        return 0;
    }

    fprintf(stderr, "unknown mode: %s\n", mode);
    return 1;
}
