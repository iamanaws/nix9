package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestNativeRuntime(t *testing.T) {
	if greeting() != "HÉLLO" {
		t.Fatal(greeting())
	}
	path := filepath.Join(t.TempDir(), "message")
	if err := os.WriteFile(path, []byte("native Go"), 0600); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil || string(data) != "native Go" {
		t.Fatalf("read: %q, %v", data, err)
	}
	output, err := exec.Command("echo", "child").Output()
	if err != nil || string(output) != "child\n" {
		t.Fatalf("child: %q, %v", output, err)
	}
}
