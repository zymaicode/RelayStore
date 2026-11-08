package main

import (
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"
)

// GameEntry is one folder under the configured game directory.
type GameEntry struct {
	AppID   int    `json:"appid"`
	Path    string `json:"path"`
	Bytes   int64  `json:"bytes"`
	Files   int    `json:"files"`
	Updated string `json:"updated"`
}

func dirStats(path string) (int64, int) {
	var bytes int64
	files := 0
	_ = filepath.Walk(path, func(p string, info os.FileInfo, err error) error {
		if err != nil || info == nil || info.IsDir() {
			return nil
		}
		if info.Name() == ".relaystore-state.json" {
			return nil
		}
		bytes += info.Size()
		files++
		return nil
	})
	return bytes, files
}

// InstalledGames lists appid folders under the game directory with their sizes.
func (a *App) InstalledGames() []GameEntry {
	root := a.settings.GameDir
	entries, err := os.ReadDir(root)
	if err != nil {
		return []GameEntry{}
	}
	out := make([]GameEntry, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		appid, err := strconv.Atoi(entry.Name())
		if err != nil {
			continue
		}
		path := filepath.Join(root, entry.Name())
		bytes, files := dirStats(path)
		if files == 0 {
			continue
		}
		updated := ""
		if info, err := entry.Info(); err == nil {
			updated = info.ModTime().Format(time.RFC3339)
		}
		out = append(out, GameEntry{AppID: appid, Path: path, Bytes: bytes, Files: files, Updated: updated})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Updated > out[j].Updated })
	return out
}

// OpenPath reveals any folder/path in Explorer.
func (a *App) OpenPath(path string) string {
	if err := openInExplorer(path); err != nil {
		return err.Error()
	}
	return ""
}
