// crash.cpp
//
// Deterministically faults so DAP exception/stop-on-signal and postmortem
// (core-dump) tests have something to attach to. Mode is chosen by
// `--mode=segv|abort|divzero` (default: segv).
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void do_segv() {
    int *p = nullptr;
    *p = 42; // @dap:before_crash
}

static void do_abort() {
    std::abort(); // @dap:before_crash_abort
}

static void do_divzero(int z) {
    volatile int x = 1;
    volatile int y = x / z; // @dap:before_crash_div
    std::printf("%d\n", y);
}

int main(int argc, char **argv) {
    const char *mode = "segv";
    for (int i = 1; i < argc; ++i) {
        if (std::strncmp(argv[i], "--mode=", 7) == 0) {
            mode = argv[i] + 7;
        }
    }
    std::printf("crash mode=%s\n", mode);
    std::fflush(stdout);

    if (std::strcmp(mode, "abort") == 0) {
        do_abort();
    } else if (std::strcmp(mode, "divzero") == 0) {
        do_divzero(0);
    } else {
        do_segv();
    }
    return 0;
}
