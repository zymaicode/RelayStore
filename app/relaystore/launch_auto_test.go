package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEnsureRuntimeForLaunch(t *testing.T) {
	root := t.TempDir()
	gameDir := filepath.Join(root, "games")
	dataDir := filepath.Join(root, "data")
	install := filepath.Join(gameDir, "Undertale")
	writeFile(t, filepath.Join(install, "UNDERTALE.exe"), "MZ")
	writeFile(t, filepath.Join(install, "steam_api.dll"), "original")

	// seed the emulator package so no network is needed
	for _, v := range []string{"x32", "x64"} {
		dir := filepath.Join(dataDir, "runtime", "experimental", v)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, "steam_api.dll"), []byte(strings.Repeat("E", 2<<20)), 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, "steam_api64.dll"), []byte(strings.Repeat("E", 2<<20)), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	clientDir := filepath.Join(dataDir, "runtime", "steamclient_experimental")
	if err := os.MkdirAll(clientDir, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"steamclient.dll", "steamclient64.dll", "steamclient_loader_x32.exe", "steamclient_loader_x64.exe"} {
		if err := os.WriteFile(filepath.Join(clientDir, name), []byte(strings.Repeat("C", 1<<20)), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	app := &App{settings: Settings{GameDir: gameDir, DataDir: dataDir}}
	note := app.ensureRuntimeForLaunch(391540)
	if !strings.Contains(note, "自动启用") {
		t.Fatalf("expected auto-enable note, got %q", note)
	}
	status := app.RuntimeStatus(391540)
	if status.Mode != "loader" {
		t.Fatalf("expected loader mode, got %q (targets=%v)", status.Mode, status.Targets)
	}
	if _, err := os.Stat(filepath.Join(install, "ColdClientLoader.ini")); err != nil {
		t.Fatalf("loader ini missing: %v", err)
	}

	// second call must be a no-op
	if again := app.ensureRuntimeForLaunch(391540); again != "" {
		t.Fatalf("expected no-op, got %q", again)
	}

	// a game that does not need Steam is left alone
	plain := filepath.Join(gameDir, "Plain")
	writeFile(t, filepath.Join(plain, "plain.exe"), "MZ")
	app.SetGameExe(105600, filepath.Join(plain, "plain.exe"))
	if note := app.ensureRuntimeForLaunch(105600); note != "" {
		t.Fatalf("expected no runtime for a plain game, got %q", note)
	}
}
