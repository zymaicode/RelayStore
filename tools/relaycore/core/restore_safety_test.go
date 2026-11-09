package core

import (
	"os"
	"path/filepath"
	"testing"
)

// A failed chunk must leave the previously installed file untouched.
func TestRestoreKeepsExistingFileOnChunkFailure(t *testing.T) {
	out := t.TempDir()
	target := filepath.Join(out, "data", "content.bin")
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("ORIGINAL"), 0o644); err != nil {
		t.Fatal(err)
	}

	// seed a cached chunk with the wrong size so assembly fails without network access
	cache := filepath.Join(out, ".chunks")
	if err := os.MkdirAll(cache, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cache, "deadbeef"), []byte("xx"), 0o644); err != nil {
		t.Fatal(err)
	}

	manifest := &Manifest{Files: []FileEntry{{
		Names:      []string{"data/content.bin"},
		Size:       4,
		ShaContent: "0000000000000000000000000000000000000000",
		Chunks:     []Chunk{{SHA: "deadbeef", Offset: 0, CbOriginal: 4}},
	}}}
	restorer := &Restorer{Depot: 1, Key: make([]byte, 32), OutDir: out, Workers: 1}
	stats, _ := restorer.Run(manifest, 0)
	if stats.FilesFailed != 1 {
		t.Fatalf("expected one failure, got %+v", stats)
	}
	remaining, readErr := os.ReadFile(target)
	if readErr != nil || string(remaining) != "ORIGINAL" {
		t.Fatalf("original file was damaged: %q %v", string(remaining), readErr)
	}
	if _, err := os.Stat(target + ".part"); !os.IsNotExist(err) {
		t.Fatalf("staging file left behind: %v", err)
	}
}
