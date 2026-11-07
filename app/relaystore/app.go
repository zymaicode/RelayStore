package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"relaycore/core"
)

// Upstream key corpora (community mirrors, same sources the Python CLI uses).
var keyCorpora = []string{
	"https://raw.githubusercontent.com/dc190/ManifestHub/main/depotkeys.json",
	"https://raw.githubusercontent.com/ooiiuur/ManifestHubSharing/main/depotkeys.json",
}

type App struct {
	ctx  context.Context
	keys map[int]string
	idx  *core.Index
	mu   sync.Mutex
}

func NewApp() *App { return &App{} }

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.reload()
}

// dataDir is the per-user data folder used once the app runs outside the repo.
func dataDir() string {
	if base, err := os.UserConfigDir(); err == nil {
		dir := filepath.Join(base, "relaystore")
		_ = os.MkdirAll(dir, 0o755)
		return dir
	}
	return "."
}

func localKeysFile() string {
	return filepath.Join(dataDir(), "keys.json")
}

// findRepoFile walks up from cwd/exe to locate repo-relative data (development mode).
func findRepoFile(rel string) string {
	var starts []string
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	for _, start := range starts {
		dir := start
		for i := 0; i < 6; i++ {
			candidate := filepath.Join(dir, rel)
			if _, err := os.Stat(candidate); err == nil {
				return candidate
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}

func (a *App) reload() {
	a.mu.Lock()
	defer a.mu.Unlock()
	keysPath := localKeysFile()
	if _, err := os.Stat(keysPath); err != nil {
		if dev := findRepoFile(filepath.Join("src", "data", "keys", "merged.json")); dev != "" {
			keysPath = dev
		}
	}
	if keys, err := core.LoadKeys(keysPath); err == nil {
		a.keys = keys
	}
	indexPath := filepath.Join(dataDir(), "index.json")
	if _, err := os.Stat(indexPath); err != nil {
		if dev := findRepoFile(filepath.Join("tests", "reports", "mirror-index.json")); dev != "" {
			indexPath = dev
		}
	}
	if idx, err := core.LoadIndex(indexPath); err == nil {
		a.idx = idx
	}
}

// DataSync reports what is loaded and whether the first-run bootstrap is needed.
func (a *App) DataSync() map[string]any {
	a.mu.Lock()
	defer a.mu.Unlock()
	depots := 0
	if a.idx != nil {
		depots = len(a.idx.Depots)
	}
	keys := len(a.keys)
	return map[string]any{
		"keys":      keys,
		"depots":    depots,
		"needsData": keys == 0,
		"dataDir":   dataDir(),
		"corpora":   len(keyCorpora),
	}
}

func fetchJSON(url string) (map[string]string, error) {
	client := &http.Client{Timeout: 180 * time.Second}
	request, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", "relaystore/1.0")
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("%s: HTTP %d", url, response.StatusCode)
	}
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	out := map[string]string{}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// BootstrapData downloads the depot key corpora, merges them and stores keys.json.
func (a *App) BootstrapData() string {
	go func() {
		merged := map[string]string{}
		for i, url := range keyCorpora {
			runtime.EventsEmit(a.ctx, "data:progress", map[string]any{
				"stage":   "download",
				"index":   i + 1,
				"total":   len(keyCorpora),
				"percent": float64(i) / float64(len(keyCorpora)) * 100,
				"source":  url,
			})
			corpus, err := fetchJSON(url)
			if err != nil {
				runtime.EventsEmit(a.ctx, "data:progress", map[string]any{"stage": "warn", "message": err.Error()})
				continue
			}
			for depot, key := range corpus {
				if len(key) == 64 {
					merged[depot] = key
				}
			}
		}
		if len(merged) == 0 {
			runtime.EventsEmit(a.ctx, "data:error", "所有数据源都下载失败，请检查网络后重试")
			return
		}
		runtime.EventsEmit(a.ctx, "data:progress", map[string]any{"stage": "save", "percent": 90.0})
		data, err := json.Marshal(merged)
		if err != nil {
			runtime.EventsEmit(a.ctx, "data:error", err.Error())
			return
		}
		if err := os.WriteFile(localKeysFile(), data, 0o644); err != nil {
			runtime.EventsEmit(a.ctx, "data:error", err.Error())
			return
		}
		a.reload()
		runtime.EventsEmit(a.ctx, "data:done", map[string]any{"keys": len(merged), "path": localKeysFile()})
	}()
	return "started"
}

// Coverage returns the downloadable report as JSON (same shape as the CLI).
func (a *App) Coverage(appid int) (string, error) {
	report, err := core.CheckCoverage(appid, a.keys, a.idx, filepath.Join(dataDir(), "appinfo"), nil)
	if err != nil {
		return "", err
	}
	data, err := json.Marshal(report)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// Restore starts a background restore and streams per-depot events to the UI.
func (a *App) Restore(appid int, target string, depotWorkers int) string {
	go func() {
		runtime.EventsEmit(a.ctx, "restore:start", appid)
		result, err := core.RestoreApp(
			appid,
			target,
			a.keys,
			a.idx,
			filepath.Join(dataDir(), "appinfo"),
			8,
			depotWorkers,
			filepath.Join(target, ".steamclient-state.json"),
			func(row core.DepotResult) {
				runtime.EventsEmit(a.ctx, "restore:depot", row)
			},
		)
		if err != nil {
			runtime.EventsEmit(a.ctx, "restore:error", err.Error())
			return
		}
		runtime.EventsEmit(a.ctx, "restore:done", result)
	}()
	return "started"
}
