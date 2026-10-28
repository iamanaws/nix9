package main

import (
	"fmt"
	"runtime"

	"example.org/greeting"
)

func greeting() string { return greetinglib.Upper("héllo") }

func main() {
	fmt.Printf("Go %s/%s: %s\n", runtime.GOOS, runtime.GOARCH, greeting())
}
