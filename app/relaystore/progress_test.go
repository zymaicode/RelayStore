package main

import (
	"path/filepath"
	"testing"
)

func TestInspectReportsPartialDownload(t *testing.T) {
	root := t.TempDir()
	gameDir := filepath.Join(root, "games")
	dataDir := filepath.Join(root, "data")
	install := filepath.Join(gameDir, "RimWorld")
	writeFile(t, filepath.Join(install, "RimWorldWin64.exe"), "MZ")
	writeFile(t, filepath.Join(install, ".relaystore-state.json"), `{"294101":"ok","294104":"failed"}`)

	app := &App{settings: Settings{GameDir: gameDir, DataDir: dataDir}}
	app.saveMetaCache(map[string]GameMeta{"294100": {Name: "RimWorld", TS: 1}})

	report := app.InspectGame(294100)
	if !report.Partial {
		t.Fatalf("expected partial download, got %+v", report)
	}
	if len(report.Pending) != 1 || report.Pending[0] != 294104 {
		t.Fatalf("unexpected pending depots: %v", report.Pending)
	}

	writeFile(t, filepath.Join(install, ".relaystore-state.json"), `{"294101":"ok","294104":"ok"}`)
	app2 := &App{settings: Settings{GameDir: gameDir, DataDir: filepath.Join(root, "data2")}}
	app2.saveMetaCache(map[string]GameMeta{"294100": {Name: "RimWorld", TS: 1}})
	if again := app2.InspectGame(294100); again.Partial {
		t.Fatalf("expected complete install, pending=%v", again.Pending)
	}
}
