package main

import (
	"testing"
)

func TestIsNewer(t *testing.T) {
	cases := []struct {
		current, latest string
		want            bool
	}{
		{"v0.49.0", "v0.49.0", false},
		{"v0.48.0", "v0.49.0", true},
		{"v0.49.0", "v0.48.0", false},
		{"v0.9.0", "v0.10.0", true},
		{"0.49.0", "v0.50.0", true},
		{"dev", "v0.49.0", true},
	}
	for _, c := range cases {
		if got := isNewer(c.current, c.latest); got != c.want {
			t.Fatalf("isNewer(%q,%q)=%v want %v", c.current, c.latest, got, c.want)
		}
	}
}

// TestFetchUpdateMetaLive hits the real GitHub API; skipped when offline.
func TestFetchUpdateMetaLive(t *testing.T) {
	meta, release, err := fetchUpdateMeta()
	if err != nil {
		t.Skipf("network unavailable: %v", err)
	}
	if meta.Version == "" {
		t.Fatal("empty version in latest.json")
	}
	if release.Tag == "" {
		t.Fatal("empty release tag")
	}
	if len(meta.Portable.SHA256) != 64 || len(meta.Installer.SHA256) != 64 {
		t.Fatalf("sha256 missing: portable=%q installer=%q", meta.Portable.SHA256, meta.Installer.SHA256)
	}
	t.Logf("latest=%s tag=%s installer=%s", meta.Version, release.Tag, meta.Installer.Name)
}
