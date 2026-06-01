// crash.rs - Rust counterpart of crash.cpp.
//
// Note Rust's integer divide-by-zero is a runtime panic (not SIGFPE), and
// `abort` calls std::process::abort(); both produce a debugger stop.
use std::env;

fn do_segv() {
    let p: *mut i32 = std::ptr::null_mut();
    unsafe {
        *p = 42; // @dap:before_crash
    }
}

fn do_abort() {
    std::process::abort(); // @dap:before_crash_abort
}

fn do_divzero(z: i32) {
    let x = 1;
    let y = std::hint::black_box(x) / std::hint::black_box(z); // @dap:before_crash_div
    println!("{}", y);
}

fn main() {
    let mode = env::args()
        .skip(1)
        .find_map(|a| a.strip_prefix("--mode=").map(str::to_owned))
        .unwrap_or_else(|| "segv".to_owned());
    println!("crash mode={}", mode);

    match mode.as_str() {
        "abort" => do_abort(),
        "divzero" => do_divzero(0),
        _ => do_segv(),
    }
}
