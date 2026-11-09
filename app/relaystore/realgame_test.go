package main

import (
	"os"
	"path/filepath"
	"testing"
)

// TestInspectRealGame runs the pre-launch check against a real installed game.
// Gated by RELAYSTORE_REAL_GAME=<install dir>.
func TestInspectRealGame(t *testing.T) {
	dir := os.Getenv("RELAYSTORE_REAL_GAME")
	if dir == "" {
		t.Skip("set RELAYSTORE_REAL_GAME=<install dir> to inspect a real game")
	}
	app := &App{settings: Settings{
		GameDir: filepath.Dir(dir),
		DataDir: t.TempDir(),
	}}
	app.SetGameExe(413150, filepath.Join(dir, "Stardew Valley.exe"))
	report := app.InspectGame(413150)
	t.Logf("verdict=%s exe=%s files=%d bytes=%d flags=%v detail=%q",
		report.Verdict, report.Exe, report.Files, report.SizeBytes, report.Flags, report.Detail)
	if report.Exe == "" {
		t.Fatal("no executable detected")
	}
}
