package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestInspectCacheAndOverride(t *testing.T) {
	root := t.TempDir()
	gameDir := filepath.Join(root, "games")
	install := filepath.Join(gameDir, "480")
	writeFile(t, filepath.Join(install, "game.exe"), "MZ fake")

	app := &App{settings: Settings{GameDir: gameDir, DataDir: filepath.Join(root, "data")}}
	first := app.InspectGame(480)
	if first.Verdict != "ready" {
		t.Fatalf("unexpected verdict %q", first.Verdict)
	}
	if _, err := os.Stat(filepath.Join(root, "data", "inspect-cache.json")); err != nil {
		t.Fatalf("cache not written: %v", err)
	}

	// cached value must be reused even if the folder disappears
	if err := os.RemoveAll(install); err != nil {
		t.Fatal(err)
	}
	cached := app.InspectGame(480)
	if cached.Verdict != "ready" {
		t.Fatalf("cache not used, verdict=%q", cached.Verdict)
	}

	// refreshing drops the cache and now reports the folder as missing
	app.RefreshInspection(480)
	if fresh := app.InspectGame(480); fresh.Verdict != "missing" {
		t.Fatalf("refresh did not bypass cache: %q", fresh.Verdict)
	}

	// pinning an executable overrides detection
	writeFile(t, filepath.Join(install, "real", "launcher.exe"), "MZ real")
	writeFile(t, filepath.Join(install, "steam_api64.dll"), "dll")
	app.RefreshInspection(480)
	auto := app.InspectGame(480)
	if auto.Verdict != "needs_steam" {
		t.Fatalf("expected needs_steam before pinning, got %q", auto.Verdict)
	}
	pinned := filepath.Join(install, "real", "launcher.exe")
	app.SetGameExe(480, pinned)
	report := app.InspectGame(480)
	if report.Exe != pinned {
		t.Fatalf("override not applied: %q", report.Exe)
	}
	found := false
	for _, flag := range report.Flags {
		if flag == "exe_pinned" {
			found = true
		}
	}
	if !found {
		t.Fatalf("exe_pinned flag missing: %v", report.Flags)
	}

	// clearing the override restores automatic detection (no exe_pinned flag)
	app.SetGameExe(480, "")
	restored := app.InspectGame(480)
	for _, flag := range restored.Flags {
		if flag == "exe_pinned" {
			t.Fatalf("override still active: %q", restored.Exe)
		}
	}
}