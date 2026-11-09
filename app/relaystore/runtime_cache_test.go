package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRuntimeCacheClearKeepsLinkedFiles(t *testing.T) {
	root := t.TempDir()
	dataDir := filepath.Join(root, "data")
	gameDir := filepath.Join(root, "games")
	cacheDir := filepath.Join(dataDir, "runtime", "steamclient_experimental")
	if err := os.MkdirAll(cacheDir, 0o755); err != nil {
		t.Fatal(err)
	}
	payload := strings.Repeat("Z", 1<<20)
	source := filepath.Join(cacheDir, "steamclient.dll")
	if err := os.WriteFile(source, []byte(payload), 0o644); err != nil {
		t.Fatal(err)
	}

	app := &App{settings: Settings{GameDir: gameDir, DataDir: dataDir}}
	info := app.RuntimeCacheInfo()
	if info["files"].(int) != 1 {
		t.Fatalf("unexpected cache info: %+v", info)
	}
	if info["bytes"].(int64) != int64(len(payload)) {
		t.Fatalf("unexpected cache size: %+v", info)
	}

	// hard link the same file into a "game folder"
	gameFolder := filepath.Join(gameDir, "Undertale")
	if err := os.MkdirAll(gameFolder, 0o755); err != nil {
		t.Fatal(err)
	}
	linked := filepath.Join(gameFolder, "steamclient.dll")
	if _, err := linkOrCopy(source, linked); err != nil {
		t.Fatal(err)
	}

	if _, err := app.ClearRuntimeCache(); err != nil {
		t.Fatalf("clear cache: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "runtime")); !os.IsNotExist(err) {
		t.Fatalf("cache dir still present: %v", err)
	}
	remaining, err := os.ReadFile(linked)
	if err != nil || len(remaining) != len(payload) {
		t.Fatalf("hard-linked game file was damaged: %v (len=%d)", err, len(remaining))
	}
}
