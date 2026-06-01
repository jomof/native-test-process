// crash.go - Go counterpart of crash.cpp.
//
// Go has no abort(); a nil dereference and an integer divide-by-zero both
// raise a runtime panic that surfaces as a fatal signal to the debugger.
package main

import (
	"fmt"
	"os"
	"strings"
)

func doSegv() {
	var p *int
	*p = 42 // @dap:before_crash
}

func doDivzero(z int) {
	x := 1
	y := x / z // @dap:before_crash_div
	fmt.Println(y)
}

func main() {
	mode := "segv"
	for _, a := range os.Args[1:] {
		if strings.HasPrefix(a, "--mode=") {
			mode = strings.TrimPrefix(a, "--mode=")
		}
	}
	fmt.Printf("crash mode=%s\n", mode)

	switch mode {
	case "divzero":
		doDivzero(0)
	default:
		doSegv()
	}
}
