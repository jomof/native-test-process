// spin.rs - Rust counterpart of spin.cpp with the same @dap markers and the
// same per-iteration richness. See spin.cpp for the full rationale.
//
// Worker threads live behind the `threads` cargo feature (default on) so the
// WASM build (`--no-default-features`, no std::thread) still compiles.
use std::hint::black_box;
use std::io::{self, Write};
use std::sync::atomic::{AtomicI64, Ordering};
use std::time::Duration;

// Mutated every tick; the canonical data-watchpoint target.
static G_TICKS: AtomicI64 = AtomicI64::new(0); // @dap:global

#[derive(Debug)]
struct Point {
    x: i32,
    y: i32,
}

fn descend(n: i32) -> i64 {
    if n <= 0 {
        return 0; // @dap:recurse_base
    }
    n as i64 + descend(n - 1)
}

fn doubler(v: i32) -> i32 {
    v * 2 // @dap:step_into
}

fn step_demo(seed: i32) -> i32 {
    let a = doubler(seed); // @dap:step_over
    let b = a + 1;
    b
}

#[cfg(feature = "threads")]
fn spawn_workers() {
    use std::thread;
    for _ in 0..2 {
        thread::spawn(|| loop {
            G_TICKS.fetch_add(1, Ordering::SeqCst);
            thread::sleep(Duration::from_millis(100));
        });
    }
}

#[cfg(not(feature = "threads"))]
fn spawn_workers() {}

fn sleep_tick() {
    let tick = Duration::from_millis(100);
    #[cfg(feature = "threads")]
    std::thread::sleep(tick);
    #[cfg(not(feature = "threads"))]
    {
        let until = std::time::Instant::now() + tick;
        while std::time::Instant::now() < until {}
    }
}

fn main() {
    spawn_workers();

    let mut counter: i64 = 0;
    loop {
        counter += 1;

        let i32v = counter as i32;
        let real = counter as f64 * 1.5;
        let text = "tick";
        let arr = [1, 2, 3];
        let pt = Point { x: i32v, y: i32v + 1 };
        let rec = descend(5);
        let stepped = step_demo(i32v);
        G_TICKS.fetch_add(1, Ordering::SeqCst);

        let observed = black_box(counter); // @dap:loop_body
        println!(
            "{} {} real={:.1} rec={} stepped={} pt=({},{}) arr0={} observed={}",
            text, counter, real, rec, stepped, pt.x, pt.y, arr[0], observed
        );
        io::stdout().flush().ok();

        sleep_tick();
    }
}
