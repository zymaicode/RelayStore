package main

import (
	"os"
	"testing"

	"relaycore/core"
)

func TestAppNameLive(t *testing.T) {
	dir := t.TempDir()
	name, err := core.AppName(480, dir)
	if err != nil {
		t.Fatalf("AppName error: %v", err)
	}
	if name == "" {
		t.Fatal("empty name")
	}
	if _, statErr := os.Stat(dir + "/480.name"); statErr != nil {
		t.Fatalf("cache not written: %v", statErr)
	}
	t.Logf("name=%s", name)
}
