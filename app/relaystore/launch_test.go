package main

import (
	"os"
	"path/filepath"
	"testing"
)

func writeFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestInspectGameVerdicts(t *testing.T) {
	cases := []struct {
		name     string
		files    map[string]string
		expected string
	}{
		{
			name:     "plain single player",
			files:    map[string]string{"game.exe": "MZ fake binary", "data.bin": "x"},
			expected: "ready",
		},
		{
			name:     "steamworks dependency",
			files:    map[string]string{"game.exe": "MZ fake", "steam_api64.dll": "dll"},
			expected: "needs_steam",
		},
		{
			name:     "denuvo",
			files:    map[string]string{"game.exe": "MZ fake", "steam_api64.dll": "dll", "Denuvo64.dll": "dll"},
			expected: "drm_locked",
		},
		{
			name:     "runtime layer present",
			files:    map[string]string{"game.exe": "MZ fake", "steam_api64.dll": "dll", "steamclient_loader.exe": "MZ"},
			expected: "ready",
		},
		{
			name:     "only installer junk",
			files:    map[string]string{"unins000.exe": "MZ", "vc_redist.x64.exe": "MZ"},
			expected: "no_exe",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			gameDir := filepath.Join(root, "games")
			install := filepath.Join(gameDir, "480")
			for name, content := range tc.files {
				writeFile(t, filepath.Join(install, name), content)
			}
			app := &App{settings: Settings{GameDir: gameDir, DataDir: t.TempDir()}}
			report := app.InspectGame(480)
			if report.Verdict != tc.expected {
				t.Fatalf("verdict = %q, want %q (flags=%v detail=%q)", report.Verdict, tc.expected, report.Flags, report.Detail)
			}
		})
	}
}