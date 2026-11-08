package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCheckUpdateWithLocalMetadata(t *testing.T) {
	meta := updateMeta{
		Version:   "v99.0.0",
		Portable:  updateAsset{Name: "relaystore.exe", SHA256: strings.Repeat("a", 64)},
		Installer: updateAsset{Name: "relaystore-amd64-installer.exe", SHA256: strings.Repeat("b", 64)},
		Source:    "relaystore-v99.0.0.zip",
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(meta)
	}))
	defer server.Close()

	t.Setenv("RELAYSTORE_UPDATE_URL", server.URL)
	app := &App{version: "v0.49.0"}
	status := app.CheckUpdate()
	if status.Error != "" {
		t.Fatalf("unexpected error: %s", status.Error)
	}
	if !status.HasUpdate || status.Latest != "v99.0.0" {
		t.Fatalf("unexpected status: %+v", status)
	}
	if status.InstallerSHA != strings.Repeat("b", 64) {
		t.Fatalf("installer sha mismatch: %s", status.InstallerSHA)
	}
	if status.InstallerURL == "" {
		t.Fatal("installer url not built from version + name")
	}
}
