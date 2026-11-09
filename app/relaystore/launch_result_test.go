package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLaunchResultIsRecorded(t *testing.T) {
	root := t.TempDir()
	dataDir := filepath.Join(root, "data")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		t.Fatal(err)
	}
	app := &App{settings: Settings{GameDir: filepath.Join(root, "games"), DataDir: dataDir}}
	app.recordLaunchResult(480, -1073741819)
	result, ok := app.lastLaunchResult(480)
	if !ok || result.ExitCode != -1073741819 {
		t.Fatalf("result not recorded: %+v ok=%v", result, ok)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "launch-results.json")); err != nil {
		t.Fatalf("state file missing: %v", err)
	}
}
