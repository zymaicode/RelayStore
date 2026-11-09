package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// TestUpdateDrill runs the whole in-app update path against a local server:
// metadata fetch -> download -> sha256 verify -> silent launch of the installer.
// It is gated by RELAYSTORE_DRILL=1 because it compiles a helper binary.
func TestUpdateDrill(t *testing.T) {
	if os.Getenv("RELAYSTORE_DRILL") == "" {
		t.Skip("set RELAYSTORE_DRILL=1 to run the end-to-end update drill")
	}
	dir := t.TempDir()

	// 1) build a dummy installer that records how it was launched
	srcDir := filepath.Join(dir, "dummy")
	if err := os.MkdirAll(srcDir, 0o755); err != nil {
		t.Fatal(err)
	}
	src := `package main

import (
	"fmt"
	"os"
)

func main() {
	path := os.Getenv("RELAYSTORE_DRILL_MARKER")
	if path == "" {
		path = os.TempDir() + string(os.PathSeparator) + "relaystore-drill.marker"
	}
	_ = os.WriteFile(path, []byte(fmt.Sprintf("launched args=%v", os.Args[1:])), 0o644)
}
`
	if err := os.WriteFile(filepath.Join(srcDir, "main.go"), []byte(src), 0o644); err != nil {
		t.Fatal(err)
	}
	dummyPath := filepath.Join(dir, "drill-installer.exe")
	build := exec.Command("go", "build", "-o", dummyPath, "main.go")
	build.Dir = srcDir
	build.Env = append(os.Environ(), "CGO_ENABLED=0")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build dummy installer: %v\n%s", err, out)
	}

	// 2) serve it together with a v99 metadata document
	payload, err := os.ReadFile(dummyPath)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(payload)
	meta := map[string]any{
		"version": "v99.0.0",
		"installer": map[string]any{
			"name":   "drill-installer.exe",
			"sha256": hex.EncodeToString(sum[:]),
		},
		"portable": map[string]any{"name": "relaystore.exe", "sha256": ""},
		"source":   "drill.zip",
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/latest.json":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(meta)
		case "/drill-installer.exe":
			_, _ = w.Write(payload)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	t.Setenv("RELAYSTORE_UPDATE_URL", server.URL+"/latest.json")
	marker := filepath.Join(dir, "launch.marker")
	t.Setenv("RELAYSTORE_DRILL_MARKER", marker)

	// headless Wails runtime replacements
	emitEvent = func(context.Context, string, map[string]any) {}
	quitApp = func(context.Context) {}

	app := &App{settings: defaultSettings()}
	app.settings.DataDir = filepath.Join(dir, "data")

	status := app.CheckUpdate()
	if status.Error != "" {
		t.Fatalf("check update error: %s", status.Error)
	}
	if !status.HasUpdate || status.Latest != "v99.0.0" {
		t.Fatalf("expected v99.0.0 update, got %+v", status)
	}

	path, err := app.DownloadInstaller(server.URL+"/drill-installer.exe", "drill-installer.exe", hex.EncodeToString(sum[:]))
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if info, err := os.Stat(path); err != nil || info.Size() != int64(len(payload)) {
		t.Fatalf("downloaded file mismatch: %v", err)
	}

	if _, err := app.DownloadInstaller(server.URL+"/drill-installer.exe", "bad.exe", strings.Repeat("0", 64)); err == nil {
		t.Fatal("expected sha256 mismatch to be rejected")
	}

	if err := app.RunInstaller(path); err != nil {
		t.Fatalf("run installer: %v", err)
	}
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(marker); err == nil {
			break
		}
		time.Sleep(200 * time.Millisecond)
	}
	content, err := os.ReadFile(marker)
	if err != nil {
		t.Fatalf("installer was not launched: %v", err)
	}
	if !strings.Contains(string(content), "/S") {
		t.Fatalf("expected silent flag, marker=%q", content)
	}
	t.Logf("drill ok: download+verify+launch, marker=%q", content)
}
// TestUpdateProductionDrill exercises the real release metadata end to end:
// check -> download -> sha256 verify -> silent install over D:\RelayStore.
// Gated by RELAYSTORE_DRILL_PROD=1 because it really installs the latest release.
func TestUpdateProductionDrill(t *testing.T) {
	if os.Getenv("RELAYSTORE_DRILL_PROD") == "" {
		t.Skip("set RELAYSTORE_DRILL_PROD=1 to run against the live release channel")
	}
	os.Unsetenv("RELAYSTORE_UPDATE_URL")
	emitEvent = func(context.Context, string, map[string]any) {}
	quitApp = func(context.Context) {}

	a1Version = "v0.62.0"
	app := &App{settings: defaultSettings()}
	status := app.CheckUpdate()
	if status.Error != "" {
		t.Fatalf("check update error: %s", status.Error)
	}
	if !status.HasUpdate {
		t.Skipf("no newer release than %s yet", a1Version)
	}
	t.Logf("detected %s -> %s", status.Current, status.Latest)

	path, err := app.DownloadInstaller(status.InstallerURL, status.InstallerName, status.InstallerSHA)
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	t.Logf("downloaded %s", path)

	if err := app.RunInstaller(path); err != nil {
		t.Fatalf("run installer: %v", err)
	}
	time.Sleep(25 * time.Second)
	installed := "D:\\RelayStore\\relaystore.exe"
	info, err := os.Stat(installed)
	if err != nil {
		t.Fatalf("installed exe missing: %v", err)
	}
	t.Logf("installed exe: %d bytes, modified %s", info.Size(), info.ModTime().Format(time.RFC3339))
}
