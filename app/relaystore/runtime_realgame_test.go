package main

import (
	"os"
	"path/filepath"
	"strconv"
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
	app := &App{settings: Settings{
		GameDir: parent,
		DataDir: filepath.Join(os.Getenv("TEMP"), "relaystore-runtime-data"),
	}}
	action := os.Getenv("RELAYSTORE_RUNTIME_ACTION")
	switch action {
	case "install":
		message, err := app.InstallRuntime(appid)
		if err != nil {
			t.Fatalf("install runtime: %v", err)
		}
		t.Logf("%s", message)
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
