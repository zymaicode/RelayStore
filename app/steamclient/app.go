package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sync"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"steamcore/core"
)

// App is the binding surface exposed to the frontend.
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

// findData walks up from the executable / working directory until it finds the data files.
func findData(rel string) string {
	candidates := []string{}
	if wd, err := os.Getwd(); err == nil {
		candidates = append(candidates, wd)
	}
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Dir(exe))
	}
	for _, start := range candidates {
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
	return rel
}

func (a *App) reload() {
	a.mu.Lock()
	defer a.mu.Unlock()
	if keys, err := core.LoadKeys(findData(filepath.Join("src", "data", "keys", "merged.json"))); err == nil {
		a.keys = keys
	}
	if idx, err := core.LoadIndex(findData(filepath.Join("tests", "reports", "mirror-index.json"))); err == nil {
		a.idx = idx
	}
}

// DataSync reports how many keys and indexed depots are loaded.
func (a *App) DataSync() map[string]any {
	a.mu.Lock()
	defer a.mu.Unlock()
	depots := 0
	if a.idx != nil {
		depots = len(a.idx.Depots)
	}
	return map[string]any{"keys": len(a.keys), "depots": depots}
}

// Coverage returns the downloadable report as JSON (same shape as the CLI).
func (a *App) Coverage(appid int) (string, error) {
	report, err := core.CheckCoverage(appid, a.keys, a.idx, findData(filepath.Join("src", "data", "appinfo")), nil)
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
			findData(filepath.Join("src", "data", "appinfo")),
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
