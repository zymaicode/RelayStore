package main

import (
	"os/exec"
)

// a1Version is replaced at build time via -ldflags "-X main.a1Version=vX.Y.Z".
var a1Version = "dev"

// openInExplorer opens a folder in Windows Explorer.
func openInExplorer(path string) error {
	return exec.Command("explorer.exe", path).Start()
}
