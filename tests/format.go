package main

import (
	"debug/plan9obj"
	"fmt"
	"log"
	"os"
)

func main() {
	f, err := plan9obj.Open(os.Args[1])
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	if f.Magic != plan9obj.MagicAMD64 || f.PtrSize != 8 {
		log.Fatalf("expected Plan 9 amd64 executable, got %+v", f.FileHeader)
	}
	if f.Section("text") == nil || f.Section("text").Size == 0 {
		log.Fatal("missing executable text")
	}
	fmt.Println("PASS: Plan 9 amd64 executable header and text section")
}
