// spin.cpp
//
// The central long-running DAP fixture. It spins forever printing a tick
// roughly every 100ms, but each iteration is deliberately rich so a single
// program exercises a wide slice of debugger behaviour:
//
//   - typed locals at the loop_body marker (int/double/string/array/struct/
//     pointer) for scopes / variables / evaluate / setVariable tests;
//   - recursion via descend() (recurse_base marker) for deep stackTrace and
//     step-out tests;
//   - step_demo()/doubler() (step_over / step_into markers) for stepping
//     and stepInTargets;
//   - a global g_ticks (global marker) as a data/watchpoint target;
//   - worker threads so the thread list has more than one entry.
//
// The marker comments are resolved to line numbers by the builder
// and published in fixture.json, so tests never hard-code a line number.
//
// Threads are compiled out when FIXTURE_SINGLE_THREADED is defined (WASM,
// where pthreads aren't available in the default wasi target).
#include <atomic>
#include <chrono>
#include <cstdio>
#include <string>
#include <vector>
#ifndef FIXTURE_SINGLE_THREADED
#include <thread>
#endif

// Mutated every tick; the canonical data-watchpoint target.
static std::atomic<long long> g_ticks{0}; // @dap:global

struct Point {
    int x;
    int y;
};

// Simple deep recursion: sum 1..n. Base case is the stack-trace anchor.
static long long descend(int n) {
    if (n <= 0) {
        return 0; // @dap:recurse_base
    }
    return n + descend(n - 1);
}

static int doubler(int v) {
    return v * 2; // @dap:step_into
}

static int step_demo(int seed) {
    int a = doubler(seed); // @dap:step_over
    int b = a + 1;
    return b;
}

#ifndef FIXTURE_SINGLE_THREADED
static void worker() {
    for (;;) {
        g_ticks.fetch_add(1);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}
#endif

int main() {
#ifndef FIXTURE_SINGLE_THREADED
    std::vector<std::thread> workers;
    workers.emplace_back(worker);
    workers.emplace_back(worker);
#endif

    long long counter = 0;
    for (;;) {
        counter += 1;

        // Typed locals visible at the breakpoint below.
        int          i32     = static_cast<int>(counter);
        double       real    = static_cast<double>(counter) * 1.5;
        const char  *text    = "tick";
        int          arr[3]  = {1, 2, 3};
        Point        pt      = {i32, i32 + 1};
        long long    rec     = descend(5);
        int          stepped = step_demo(i32);
        g_ticks.fetch_add(1);

        volatile long long observed = counter; // @dap:loop_body
        std::printf("%s %lld real=%.1f rec=%lld stepped=%d pt=(%d,%d) arr0=%d observed=%lld\n",
                    text, counter, real, rec, stepped, pt.x, pt.y, arr[0],
                    static_cast<long long>(observed));
        std::fflush(stdout);

        std::chrono::milliseconds tick(100);
#ifndef FIXTURE_SINGLE_THREADED
        std::this_thread::sleep_for(tick);
#else
        // Busy-ish wait without pthreads. Coarse but fine for a fixture.
        auto until = std::chrono::steady_clock::now() + tick;
        while (std::chrono::steady_clock::now() < until) {
        }
#endif
    }
    return 0;
}
