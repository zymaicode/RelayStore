package core

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// manifestArchHint guesses which architecture a depot targets from its file paths.
func manifestArchHint(m *Manifest) string {
	if m == nil || len(m.Files) == 0 {
		return ""
	}
	x64, x32 := 0, 0
	for _, file := range m.Files {
		path := ""
		if len(file.Names) > 0 {
			path = file.Names[0]
		}
		lower := strings.ToLower(path)
		switch {
		case strings.Contains(lower, "x86_64") || strings.Contains(lower, "amd64"):
			x64++
		case strings.Contains(lower, "x86/") || strings.Contains(lower, "plugins/x86/") || strings.HasSuffix(lower, "/x86"):
			x32++
		}
	}
	if x64 == 0 && x32 == 0 {
		return ""
	}
	if x64 >= x32*3 {
		return "x64"
	}
	if x32 >= x64*3 {
		return "x32"
	}
	return ""
}

type DepotResult struct {
	DepotID   int    `json:"depot_id"`
	Status    string `json:"status"`
	FilesOK   int    `json:"files_ok"`
	Failed    int    `json:"files_failed"`
	Bytes     uint64 `json:"bytes"`
	GID       string `json:"gid,omitempty"`
	Source    string `json:"source_url,omitempty"`
	Error     string `json:"error,omitempty"`
	Seconds   float64 `json:"seconds"`
}

type AppResult struct {
	AppID   int           `json:"appid"`
	OutDir  string        `json:"out_dir"`
	OK      bool          `json:"ok"`
	Depots  []DepotResult `json:"depots"`
	FilesOK int           `json:"files_ok"`
	Bytes   uint64        `json:"bytes"`
}

func loadState(path string) map[int]string {
	state := map[int]string{}
	if path == "" {
		return state
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return state
	}
	var raw map[string]string
	if json.Unmarshal(data, &raw) != nil {
		return state
	}
	for key, value := range raw {
		if id, err := strconv.Atoi(key); err == nil {
			state[id] = value
		}
	}
	return state
}

func saveState(path string, state map[int]string) {
	if path == "" {
		return
	}
	raw := map[string]string{}
	for key, value := range state {
		raw[strconv.Itoa(key)] = value
	}
	if err := WriteJSON(path, raw); err != nil {
		fmt.Println("state write failed:", err)
	}
}

// RestoreApp restores every depot of an app, in parallel when depotWorkers > 1.
func RestoreApp(appid int, outDir string, keys map[int]string, idx *Index, cacheDir string, workers, depotWorkers int, statePath string, preferArch string, onProgress func(DepotResult)) (*AppResult, error) {
	depots, err := PublicDepots(appid, cacheDir)
	if err != nil {
		return nil, err
	}
	depots = WindowsDepots(depots)
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return nil, err
	}
	state := loadState(statePath)
	mirror := NewMirror()
	result := &AppResult{AppID: appid, OutDir: outDir}
	var mu sync.Mutex

	process := func(info DepotInfo) DepotResult {
		started := time.Now()
		row := DepotResult{DepotID: info.DepotID, GID: info.GID}
		defer func() { row.Seconds = time.Since(started).Seconds() }()
		if state[info.DepotID] == "ok" {
			row.Status = "skipped"
			row.Error = "resumed: already ok"
			return row
		}
		keyHex, ok := keys[info.DepotID]
		if !ok {
			row.Status = "missing_key"
			row.Error = "no depot key"
			return row
		}
		key, err := HexKey(keyHex)
		if err != nil {
			row.Status = "failed"
			row.Error = err.Error()
			return row
		}
		manifest, source, gidUsed, err := mirror.Fetch(info.DepotID, info.GID, idx)
		if err != nil {
			row.Status = "missing_manifest"
			row.Error = err.Error()
			return row
		}
		if hint := manifestArchHint(manifest); hint != "" && preferArch != "" && hint != preferArch && len(depots) > 1 {
			// platform twins ship the same content for another arch; keep only ours
			row.Status = "skipped_arch"
			row.Error = fmt.Sprintf("skipped: %s only (app is %s)", hint, preferArch)
			return row
		}
		row.Source = source
		row.GID = gidUsed
		restorer := &Restorer{Depot: info.DepotID, Key: key, OutDir: outDir, Workers: workers}
		stats, err := restorer.Run(manifest, 0)
		row.FilesOK = stats.FilesOK
		row.Failed = stats.FilesFailed
		row.Bytes = stats.Bytes
		if err != nil || stats.FilesFailed > 0 {
			row.Status = "failed"
			if err != nil {
				row.Error = err.Error()
			} else if len(stats.Errors) > 0 {
				row.Error = stats.Errors[0]
			}
			return row
		}
		row.Status = "ok"
		return row
	}

	if depotWorkers > 1 {
		sem := make(chan struct{}, depotWorkers)
		var wg sync.WaitGroup
		rows := make([]DepotResult, len(depots))
		for i, info := range depots {
			wg.Add(1)
			go func(i int, info DepotInfo) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				row := process(info)
				mu.Lock()
				rows[i] = row
				if row.Status != "skipped" {
					state[info.DepotID] = row.Status
					saveState(statePath, state)
				}
				if onProgress != nil {
					onProgress(row)
				}
				mu.Unlock()
			}(i, info)
		}
		wg.Wait()
		result.Depots = rows
	} else {
		for _, info := range depots {
			row := process(info)
			result.Depots = append(result.Depots, row)
			if row.Status != "skipped" {
				state[info.DepotID] = row.Status
				saveState(statePath, state)
			}
			if onProgress != nil {
				onProgress(row)
			}
		}
	}

	for _, row := range result.Depots {
		if row.Status == "ok" || row.Status == "skipped" {
			result.FilesOK += row.FilesOK
			result.Bytes += row.Bytes
		}
	}
	result.OK = len(result.Depots) > 0
	allComplete := true
	for _, row := range result.Depots {
		switch row.Status {
		case "ok", "skipped", "skipped_arch":
		default:
			result.OK = false
			allComplete = false
		}
	}
	// the chunk cache only exists to resume interrupted depots: drop it once everything landed
	if allComplete {
		_ = os.RemoveAll(filepath.Join(outDir, ".chunks"))
	}
	return result, nil
}