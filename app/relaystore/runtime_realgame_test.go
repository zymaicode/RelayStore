package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// TestRuntimeRealGame applies or removes the runtime layer on a real install.
// Gated by RELAYSTORE_RUNTIME_APPID=<appid> and RELAYSTORE_RUNTIME_DIR=<parent game dir>.
func TestRuntimeRealGame(t *testing.T) {
	rawID := os.Getenv("RELAYSTORE_RUNTIME_APPID")
	parent := os.Getenv("RELAYSTORE_RUNTIME_DIR")
	if rawID == "" || parent == "" {
		t.Skip("set RELAYSTORE_RUNTIME_APPID and RELAYSTORE_RUNTIME_DIR to touch a real install")
	}
	appid, err := strconv.Atoi(rawID)
	if err != nil {
		t.Fatalf("bad appid: %v", err)
	}
	dataDir := filepath.Join(os.Getenv("TEMP"), "relaystore-runtime-data")
	if name := os.Getenv("RELAYSTORE_RUNTIME_GAME_NAME"); name != "" {
		if err := os.MkdirAll(dataDir, 0o755); err == nil {
			meta := map[string]GameMeta{rawID: {Name: name, TS: 1}}
			if data, marshalErr := json.Marshal(meta); marshalErr == nil {
				_ = os.WriteFile(filepath.Join(dataDir, "meta.json"), data, 0o644)
			}
		}
	}
	app := &App{settings: Settings{
		GameDir: parent,
		DataDir: dataDir,
	}}
	action := os.Getenv("RELAYSTORE_RUNTIME_ACTION")
	switch action {
	case "install":
		message, err := app.InstallRuntime(appid)
		if err != nil {
			t.Fatalf("install runtime: %v", err)
		}
		t.Logf("%s", message)
	case "install-loader":
		message, err := app.InstallRuntimeLoader(appid)
		if err != nil {
			t.Fatalf("install loader: %v", err)
		}
		t.Logf("%s", message)
	case "remove-loader":
		message, err := app.RemoveRuntimeLoader(appid)
		if err != nil {
			t.Fatalf("remove loader: %v", err)
		}
		t.Logf("%s", message)
	case "launch":
		message := app.LaunchGame(appid)
		if strings.HasPrefix(message, "运行时层不可用") {
			t.Fatalf("launch: %s", message)
		}
		t.Logf("launched appid %d note=%q", appid, message)
	case "remove":
		message, err := app.RemoveRuntime(appid)
		if err != nil {
			t.Fatalf("remove runtime: %v", err)
		}
		t.Logf("%s", message)
	default:
		status := app.RuntimeStatus(appid)
		t.Logf("status: installed=%v arch=%s dll=%s backup=%v", status.Installed, status.Arch, status.DLL, status.Backup)
	}
}