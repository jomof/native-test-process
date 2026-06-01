// spin.go - Go counterpart of spin.cpp with the same @dap markers.
//
// Go goroutines work even on the single-threaded wasip1 target, so unlike
// the C++/Rust variants there is no thread-gating here.
package main

import (
	"fmt"
	"os"
	"sync/atomic"
	"time"
)

// Mutated every tick; the canonical data-watchpoint target.
var gTicks int64 // @dap:global

type Point struct {
	X int
	Y int
}

func descend(n int) int64 {
	if n <= 0 {
		return 0 // @dap:recurse_base
	}
	return int64(n) + descend(n-1)
}

func doubler(v int) int {
	return v * 2 // @dap:step_into
}

func stepDemo(seed int) int {
	a := doubler(seed) // @dap:step_over
	b := a + 1
	return b
}

func worker() {
	for {
		atomic.AddInt64(&gTicks, 1)
		time.Sleep(100 * time.Millisecond)
	}
}

func main() {
	go worker()
	go worker()

	var counter int64
	for {
		counter++

		i32v := int(counter)
		real := float64(counter) * 1.5
		text := "tick"
		arr := [3]int{1, 2, 3}
		pt := Point{X: i32v, Y: i32v + 1}
		rec := descend(5)
		stepped := stepDemo(i32v)
		atomic.AddInt64(&gTicks, 1)

		observed := counter // @dap:loop_body
		fmt.Printf("%s %d real=%.1f rec=%d stepped=%d pt=(%d,%d) arr0=%d observed=%d\n",
			text, counter, real, rec, stepped, pt.X, pt.Y, arr[0], observed)
		os.Stdout.Sync()

		time.Sleep(100 * time.Millisecond)
	}
}
