// cgpost.c — CGEventPost 按键注入器 v0.1 (2026-10-10)
// ------------------------------------------------------------------
// 背景（10-10 实证）:
//   IOHIDPostEvent 对「裸键」（无 flags 的 NX_KEYDOWN/KEYUP）在本机
//   kr=0 但事件不进系统事件流（监听器零捕获）；而对 flags/修饰键形态
//   有效。普通按键（回车/Esc/方向键）改走 CGEventPost —— 该通道 10-09
//   已实证能进系统事件流（代价: 带 srcPid 脚印，普通 App 不介意）。
//
//   与 iohid_post 分立为两个二进制：iohid_post 的 PostEvent 授权已绑
//   定其文件路径/签名，重编译会换 cdhash 致授权失效（→ 破坏语音链），
//   故不触碰；cgpost 为新路径新授权，独立演进。
//
// 编译:
//   clang -O2 -o cgpost cgpost.c -framework CoreGraphics \
//         -framework CoreFoundation -framework ApplicationServices
//
// v0.2 (2026-10-10 午后) 背景:
//   裸二进制经 macOS 27 "手动 + 添加" 的 TCC 记录无法匹配进程
//   （tccd: Failed to match existing code requirement; 二进制自添加
//   以来字节未变）。改用 App Bundle 形态 + 弹窗登记流程（prompt 模式）。
//   ⚠ 冻结约定: 一旦系统授权落地，本 App 内的二进制不得再重编译/重签
//   （除非已验证授权与 cdhash 无关）。改动逻辑请先另存新 bundle。
//
// 用法:
//   cgpost check                打印权限状态（AX / PostEvent / ListenEvent）
//   cgpost request              触发授权请求（单次, 不驻留）
//   cgpost prompt               触发授权请求并轮询 ~180s, 状态写文件日志
//                               （供从 Aqua 上下文经 open 启动时使用）
//   cgpost serve                常驻 UNIX socket /tmp/cgpost.sock 低延迟注入
//                               （KEY <kc> <0|1> / PING / STATUS）
//   cgpost key <nxkc> <0|1>     裸键 down(1)/up(0) —— CGEvent 通道
//   cgpost tap <nxkc> <gap_ms>  单击（down; gap; up 单进程原子完成, 诊断用）
// ------------------------------------------------------------------

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdarg.h>
#include <time.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <CoreGraphics/CoreGraphics.h>
#include <CoreFoundation/CoreFoundation.h>
#include <ApplicationServices/ApplicationServices.h>

// ---- 文件+stdout 双写日志（launchd / open 启动时 stdout 会丢, 文件兜底）----
static const char *g_logpath = "/tmp/cgpost.log";

static void plog(const char *fmt, ...) {
    char buf[640];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    time_t t = time(NULL);
    struct tm lt;
    localtime_r(&t, &lt);
    char line[768];
    snprintf(line, sizeof line, "[%02d:%02d:%02d] %s",
             lt.tm_hour, lt.tm_min, lt.tm_sec, buf);
    fputs(line, stdout);
    fflush(stdout);
    FILE *f = fopen(g_logpath, "a");
    if (f) { fputs(line, f); fclose(f); }
}

static void warn_if_blocked(void) {
    if (!CGPreflightPostEventAccess()) {
        plog("警告: PostEvent 权限未授权 (CGPreflightPostEventAccess=0), 事件会被系统丢弃\n");
    }
}

static int post_key(int kc, int down) {
    CGEventSourceRef src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState);
    CGEventRef ev = CGEventCreateKeyboardEvent(src, (CGKeyCode)kc, down != 0);
    if (!ev) {
        fprintf(stderr, "CGEventCreateKeyboardEvent(kc=%d) 失败\n", kc);
        if (src) CFRelease(src);
        return 2;
    }
    CGEventSetFlags(ev, 0);              // 显式清零 flags: 注入"干净"的裸键
    CGEventPost(kCGHIDEventTap, ev);     // HID 层入口, 最接近物理键盘
    plog("CGEventPost(key=%d, %s) 已投递 (pid=%d)\n",
         kc, down ? "DOWN" : "UP", (int)getpid());
    CFRelease(ev);
    if (src) CFRelease(src);
    return 0;
}

// ---- prompt 模式: 触发授权登记并轮询（从 Aqua 上下文经 open 启动）----
static int prompt_mode(void) {
    g_logpath = "/tmp/cgpost_prompt.log";
    plog("=== prompt 模式启动 pid=%d ppid=%d\n", (int)getpid(), (int)getppid());
    plog("初始: PostEvent=%d AX=%d Listen=%d\n",
         CGPreflightPostEventAccess() ? 1 : 0,
         AXIsProcessTrusted() ? 1 : 0,
         CGPreflightListenEventAccess() ? 1 : 0);
    int ax_prompted = 0;
    for (int i = 0; i < 60; i++) {                 // 最长 ~180s
        if (CGPreflightPostEventAccess()) {
            plog("★ PostEvent 已授权 (第 %d 秒)\n", i * 3);
            return 0;
        }
        if (i == 0) {
            plog("调用 CGRequestPostEventAccess() 触发授权弹窗...\n");
            CGRequestPostEventAccess();
        }
        if (i == 8 && !ax_prompted && !AXIsProcessTrusted()) {
            plog("调用 AXIsProcessTrustedWithOptions(prompt) 登记到列表...\n");
            ax_prompted = 1;
            const void *keys[] = { kAXTrustedCheckOptionPrompt };
            const void *vals[] = { kCFBooleanTrue };
            CFDictionaryRef o = CFDictionaryCreate(NULL, keys, vals, 1,
                                &kCFTypeDictionaryKeyCallBacks,
                                &kCFTypeDictionaryValueCallBacks);
            if (o) { AXIsProcessTrustedWithOptions(o); CFRelease(o); }
        }
        sleep(3);
        if (i % 2 == 1)
            plog("等待中 %ds: PostEvent=%d AX=%d\n", (i + 1) * 3,
                 CGPreflightPostEventAccess() ? 1 : 0,
                 AXIsProcessTrusted() ? 1 : 0);
    }
    plog("超时退出（仍未授权）\n");
    return 1;
}

// ---- serve 模式: 常驻 UNIX 数据报 socket, 供 key_bridge 低延迟注入 ----
static int serve_mode(void) {
    g_logpath = "/tmp/cgpost_serve.log";
    const char *sockpath = "/tmp/cgpost.sock";
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof addr);
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, sockpath, sizeof(addr.sun_path) - 1);

    // 已有实例探测（避免抢占现有 socket）
    int probe = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (probe >= 0) {
        if (connect(probe, (struct sockaddr *)&addr, sizeof addr) == 0) {
            struct timeval tv = {0, 300000};
            setsockopt(probe, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
            const char *ping = "PING\n";
            send(probe, ping, strlen(ping), 0);
            char rb[64];
            if (recv(probe, rb, sizeof rb, 0) > 0 && !strncmp(rb, "PONG", 4)) {
                plog("已有 serve 实例在运行, 本进程退出\n");
                close(probe);
                return 0;
            }
        }
        close(probe);
    }

    unlink(sockpath);
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) { plog("socket() 失败 errno=%d\n", errno); return 1; }
    if (bind(fd, (struct sockaddr *)&addr, sizeof addr) < 0) {
        plog("bind(%s) 失败 errno=%d\n", sockpath, errno);
        close(fd);
        return 1;
    }
    chmod(sockpath, 0600);
    plog("=== serve 模式启动 pid=%d socket=%s\n", (int)getpid(), sockpath);
    plog("权限: PostEvent=%d AX=%d Listen=%d\n",
         CGPreflightPostEventAccess() ? 1 : 0,
         AXIsProcessTrusted() ? 1 : 0,
         CGPreflightListenEventAccess() ? 1 : 0);

    for (;;) {
        char buf[256];
        struct sockaddr_un peer;
        socklen_t plen = sizeof peer;
        ssize_t n = recvfrom(fd, buf, sizeof buf - 1, 0,
                             (struct sockaddr *)&peer, &plen);
        if (n <= 0) continue;
        buf[n] = 0;
        char *nl = strchr(buf, '\n');
        if (nl) *nl = 0;
        int kc = 0, val = 0;
        if (!strncmp(buf, "KEY ", 4) &&
            sscanf(buf + 4, "%d %d", &kc, &val) == 2 &&
            kc >= 0 && kc <= 255) {
            post_key(kc, val);
            const char *ok = "OK\n";
            sendto(fd, ok, strlen(ok), 0, (struct sockaddr *)&peer, plen);
        } else if (!strcmp(buf, "PING")) {
            const char *p = "PONG v2\n";
            sendto(fd, p, strlen(p), 0, (struct sockaddr *)&peer, plen);
        } else if (!strcmp(buf, "STATUS")) {
            char st[160];
            snprintf(st, sizeof st, "STATUS pid=%d Post=%d AX=%d Listen=%d\n",
                     (int)getpid(),
                     CGPreflightPostEventAccess() ? 1 : 0,
                     AXIsProcessTrusted() ? 1 : 0,
                     CGPreflightListenEventAccess() ? 1 : 0);
            sendto(fd, st, strlen(st), 0, (struct sockaddr *)&peer, plen);
        } else {
            const char *bad = "ERR\n";
            sendto(fd, bad, strlen(bad), 0, (struct sockaddr *)&peer, plen);
        }
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr,
                "usage: cgpost <mode> [args]\n"
                "  check               权限状态\n"
                "  request             触发授权请求（单次）\n"
                "  prompt              触发授权并轮询 ~180s（写文件日志）\n"
                "  serve               常驻 socket 注入模式\n"
                "  key <nxkc> <0|1>    裸键 down/up\n"
                "  tap <nxkc> <gap_ms> 单击\n");
        return 1;
    }
    const char *mode = argv[1];

    if (!strcmp(mode, "check")) {
        printf("AXIsProcessTrusted()        = %d  (1=辅助功能已授权)\n",
               AXIsProcessTrusted() ? 1 : 0);
        printf("CGPreflightPostEventAccess()= %d  (1=可投递事件)\n",
               CGPreflightPostEventAccess() ? 1 : 0);
        printf("CGPreflightListenEventAccess()=%d  (1=可监听事件)\n",
               CGPreflightListenEventAccess() ? 1 : 0);
        return 0;
    }

    if (!strcmp(mode, "request")) {
        // CGEventPost 所需授权 = kTCCServicePostEvent（与 Accessibility 分离的
        // 独立 TCC 服务；界面同在 系统设置>隐私与安全性>辅助功能）。
        // 本调用触发系统授权弹窗（若系统允许从本上下文弹出）。
        Boolean pe = CGRequestPostEventAccess();
        printf("CGRequestPostEventAccess() -> %d  (1=已授权, 0=未授权/待允许)\n", pe ? 1 : 0);
        fflush(stdout);
        return 0;
    }

    if (!strcmp(mode, "prompt")) return prompt_mode();
    if (!strcmp(mode, "serve"))  return serve_mode();

    if (!strcmp(mode, "key")) {
        if (argc < 4) { fprintf(stderr, "key <nxkc> <0|1>\n"); return 1; }
        int kc = atoi(argv[2]);
        int down = atoi(argv[3]);
        if (kc < 0 || kc > 255) { fprintf(stderr, "keycode 越界: %d\n", kc); return 1; }
        warn_if_blocked();
        return post_key(kc, down);
    }

    if (!strcmp(mode, "tap")) {
        if (argc < 3) { fprintf(stderr, "tap <nxkc> [gap_ms=80]\n"); return 1; }
        int kc = atoi(argv[2]);
        int gap = argc > 3 ? atoi(argv[3]) : 80;
        warn_if_blocked();
        int r = post_key(kc, 1);
        if (r) return r;
        usleep(gap * 1000);
        return post_key(kc, 0);
    }

    fprintf(stderr, "unknown mode: %s\n", mode);
    return 1;
}
