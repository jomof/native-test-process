// hello.cpp - the smallest debuggable fixture.
//
// Covers: launch, stdout output events, clean exit code 0, terminate.
// The 'hello' marker is the single executable line a test can break on.
#include <cstdio>

int main() {
    std::printf("hello from native-test-process\n"); // @dap:hello
    std::fflush(stdout);
    return 0;
}
