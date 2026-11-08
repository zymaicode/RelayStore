package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	defaultDataDir = `D:\RelayStoreData`
	defaultGameDir = `D:\RelayGame`
	portableFlag   = "portable.flag"
)

// Settings is the on-disk configuration. It lives in %APPDATA% for the installed
// build and in .\data for the portable build, so the portable config travels.
type Settings struct {
	DataDir      string `json:"dataDir"`
	GameDir      string `json:"gameDir"`
	DepotWorkers int    `json:"depotWorkers"`
	ChunkWorkers int    `json:"chunkWorkers"`
	CheckUpdates bool   `json:"checkUpdates"`
	Theme        string `json:"theme"`
	FontSize     string `json:"fontSize"`
}

// ThemeNames lists the bundled themes (ported from CodeForge).
var ThemeNames = []string{"system", "light", "dark", "animal", "wenyang"}

// FontSizeNames lists the UI density presets.
var FontSizeNames = []string{"compact", "standard", "relaxed"}

func normalizeFontSize(name string) string {
	for _, candidate := range FontSizeNames {
		if candidate == name {
			return name
		}
	}
	return "standard"
}

func normalizeTheme(name string) string {
	for _, candidate := range ThemeNames {
		if candidate == name {
			return name
		}
	}
	return "system"
}

func exeDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

// isPortable: a portable.flag next to the exe switches every path to local folders.
func isPortable() bool {
	_, err := os.Stat(filepath.Join(exeDir(), portableFlag))
	return err == nil
}

func settingsPath() string {
	if isPortable() {
		return filepath.Join(exeDir(), "data", "settings.json")
	}
	base, err := os.UserConfigDir()
	if err != nil {
		return filepath.Join(exeDir(), "settings.json")
	}
	return filepath.Join(base, "relaystore", "settings.json")
}

func defaultSettings() Settings {
	if isPortable() {
		return Settings{
			DataDir:      filepath.Join(exeDir(), "data"),
			GameDir:      filepath.Join(exeDir(), "games"),
			DepotWorkers: 2,
			ChunkWorkers: 8,
			CheckUpdates: true,
			Theme:        "system",
			FontSize:     "standard",
		}
	}
	return Settings{
		DataDir:      defaultDataDir,
		GameDir:      defaultGameDir,
		DepotWorkers: 2,
		ChunkWorkers: 8,
		CheckUpdates: true,
		Theme:        "system",
		FontSize:     "standard",
	}
}

func loadSettings() Settings {
	settings := defaultSettings()
	data, err := os.ReadFile(settingsPath())
	if err != nil {
		return settings
	}
	_ = json.Unmarshal(data, &settings)
	if settings.DataDir == "" {
		settings.DataDir = defaultSettings().DataDir
	}
	if settings.GameDir == "" {
		settings.GameDir = defaultSettings().GameDir
	}
	if settings.DepotWorkers <= 0 {
		settings.DepotWorkers = 2
	}
	if settings.ChunkWorkers <= 0 {
		settings.ChunkWorkers = 8
	}
	settings.Theme = normalizeTheme(settings.Theme)
	settings.FontSize = normalizeFontSize(settings.FontSize)
	return settings
}

func saveSettings(settings Settings) error {
	path := settingsPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

// validatePath rejects roots and checks writability before anything is saved.
func validatePath(label, path string) error {
	trimmed := strings.TrimSpace(path)
	if trimmed == "" {
		return fmt.Errorf("%s 不能为空", label)
	}
	cleaned := filepath.Clean(trimmed)
	if len(cleaned) <= 3 {
		return fmt.Errorf("%s 不能是盘符根目录", label)
	}
	if err := os.MkdirAll(cleaned, 0o755); err != nil {
		return fmt.Errorf("%s 无法创建：%v", label, err)
	}
	probe := filepath.Join(cleaned, ".relaystore-write-test")
	if err := os.WriteFile(probe, []byte("ok"), 0o644); err != nil {
		return fmt.Errorf("%s 不可写（可能需要管理员权限）：%v", label, err)
	}
	_ = os.Remove(probe)
	return nil
}
