package main

import (
	"fmt"
	"runtime"
)

func main() {
	fmt.Printf("Hello from Nix on %s/%s!\n", runtime.GOOS, runtime.GOARCH)
}
