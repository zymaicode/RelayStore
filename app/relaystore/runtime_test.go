package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRuntimeLayerInstallAndRemove(t *testing.T) {
	root := t.TempDir()
	gameDir := filepath.Join(root, "games")
	dataDir := filepath.Join(root, "data")
	install := filepath.Join(gameDir, "Undertale")
	writeFile(t, filepath.Join(install, "steam_api.dll"), "original-dll")

	// seed the unpacked emulator package so the drill does not hit the network
	seed := filepath.Join(dataDir, "runtime", "experimental", "x32")
	if err := os.MkdirAll(seed, 0o755); err != nil {
		t.Fatal(err)
	}
	big := strings.Repeat("E", 2<<20)
	if err := os.WriteFile(filepath.Join(seed, "steam_api.dll"), []byte(big), 0o644); err != nil {
		t.Fatal(err)
	}

	app := &App{settings: Settings{GameDir: gameDir, DataDir: dataDir}}
	status := app.RuntimeStatus(391540)
	if status.Installed {
		t.Fatalf("layer should not be installed yet: %+v", status)
	}

	if _, err := app.InstallRuntime(391540); err != nil {
		t.Fatalf("install runtime: %v", err)
	}
	if info, err := os.Stat(filepath.Join(install, "steam_api.dll")); err != nil || info.Size() != int64(len(big)) {
		t.Fatalf("emulator dll not installed: %v", err)
	}
	if _, err := os.Stat(filepath.Join(install, "steam_api.dll.orig")); err != nil {
		t.Fatalf("backup missing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(install, "steam_appid.txt")); err != nil {
		t.Fatalf("steam_appid.txt missing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(install, "steam_settings", "configs.appid")); err != nil {
		t.Fatalf("steam_settings missing: %v", err)
	}

	if _, err := app.RemoveRuntime(391540); err != nil {
		t.Fatalf("remove runtime: %v", err)
	}
	restored, err := os.ReadFile(filepath.Join(install, "steam_api.dll"))
	if err != nil || string(restored) != "original-dll" {
		t.Fatalf("original dll not restored: %q %v", string(restored), err)
	}
	if _, err := os.Stat(filepath.Join(install, "steam_settings")); !os.IsNotExist(err) {
		t.Fatalf("steam_settings not cleaned: %v", err)
	}
}
func TestLoaderInstallSharesFiles(t *testing.T) {
	root := t.TempDir()
	gameDir := filepath.Join(root, "games")
	dataDir := filepath.Join(root, "data")
	install := filepath.Join(gameDir, "Undertale")
	writeFile(t, filepath.Join(install, "UNDERTALE.exe"), "MZ")

	clientDir := filepath.Join(dataDir, "runtime", "steamclient_experimental")
	if err := os.MkdirAll(clientDir, 0o755); err != nil {
		t.Fatal(err)
	}
	big := strings.Repeat("S", 3<<20)
	for _, name := range []string{"steamclient.dll", "steamclient64.dll", "steamclient_loader_x32.exe"} {
		if err := os.WriteFile(filepath.Join(clientDir, name), []byte(big), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	app := &App{settings: Settings{GameDir: gameDir, DataDir: dataDir}}
	if _, err := app.InstallRuntimeLoader(391540); err != nil {
		t.Fatalf("install loader: %v", err)
	}

	source := filepath.Join(clientDir, "steamclient.dll")
	target := filepath.Join(install, "steamclient.dll")
	sourceInfo, err := os.Stat(source)
	if err != nil {
		t.Fatal(err)
	}
	targetInfo, err := os.Stat(target)
	if err != nil {
		t.Fatalf("steamclient.dll not installed: %v", err)
	}
	if !os.SameFile(sourceInfo, targetInfo) {
		t.Fatalf("expected a hard link (same file), got a separate copy")
	}
	if _, err := os.Stat(filepath.Join(install, "GameOverlayRenderer.dll")); !os.IsNotExist(err) {
		t.Fatalf("overlay renderer should not be installed anymore: %v", err)
	}
}
