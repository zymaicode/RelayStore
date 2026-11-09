package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
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
	ctx      context.Context
	version  string
	settings Settings
	keys     map[int]string
	idx      *core.Index
	mu       sync.Mutex
}

func NewApp(version string) *App { return &App{version: version} }

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.settings = loadSettings()
	// persist defaults on first run so the effective paths are discoverable
	if _, err := os.Stat(settingsPath()); err != nil {
		_ = saveSettings(a.settings)
	}
	a.reload()
}

// findRepoFile walks up from cwd/exe to locate repo-relative data (development mode).
func findRepoFile(rel string) string {
	var starts []string
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	starts = append(starts, exeDir())
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

func (a *App) keysPath() string {
	return filepath.Join(a.settings.DataDir, "keys.json")
}

func (a *App) indexPath() string {
	return filepath.Join(a.settings.DataDir, "index.json")
}

func (a *App) reload() {
	a.mu.Lock()
	defer a.mu.Unlock()

	keysPath := a.keysPath()
	if _, err := os.Stat(keysPath); err != nil {
		if dev := findRepoFile(filepath.Join("src", "data", "keys", "merged.json")); dev != "" {
			keysPath = dev
		}
	}
	if keys, err := core.LoadKeys(keysPath); err == nil {
		a.keys = keys
	}

	indexPath := a.indexPath()
	if _, err := os.Stat(indexPath); err != nil {
		if dev := findRepoFile(filepath.Join("tests", "reports", "mirror-index.json")); dev != "" {
			indexPath = dev
		}
	}
	if idx, err := core.LoadIndex(indexPath); err == nil {
		a.idx = idx
	}
}

func (a *App) appinfoDir() string {
	dir := filepath.Join(a.settings.DataDir, "appinfo")
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

// AppVersion returns the build version injected by CI.
func (a *App) AppVersion() string { return a.version }

// PortableMode reports whether this copy runs from a portable.flag folder.
func (a *App) PortableMode() bool { return isPortable() }

// DataSync reports what is loaded plus the effective paths.
func (a *App) DataSync() map[string]any {
	a.mu.Lock()
	defer a.mu.Unlock()
	depots := 0
	if a.idx != nil {
		depots = len(a.idx.Depots)
	}
	keys := len(a.keys)
	return map[string]any{
		"theme":     a.settings.Theme,
		"fontSize":  a.settings.FontSize,
		"keys":      keys,
		"depots":    depots,
		"needsData": keys == 0,
		"dataDir":   a.settings.DataDir,
		"gameDir":   a.settings.GameDir,
		"settings":  settingsPath(),
		"portable":  isPortable(),
		"version":   a.version,
		"corpora":   len(keyCorpora),
	}
}

// SetTheme switches the UI theme and persists it.
func (a *App) SetTheme(name string) string {
	theme := normalizeTheme(name)
	a.settings.Theme = theme
	_ = saveSettings(a.settings)
	return theme
}

// SetFontSize switches the UI density preset and persists it.
func (a *App) SetFontSize(name string) string {
	size := normalizeFontSize(name)
	a.settings.FontSize = size
	_ = saveSettings(a.settings)
	return size
}

// GetSettings returns the current configuration for the settings panel.
func (a *App) GetSettings() Settings { return a.settings }

// SaveSettings validates both folders, optionally migrates data, then persists.
func (a *App) SaveSettings(next Settings) (string, error) {
	if err := validatePath("数据目录", next.DataDir); err != nil {
		return "", err
	}
	if err := validatePath("游戏目录", next.GameDir); err != nil {
		return "", err
	}
	if filepath.Clean(next.DataDir) == filepath.Clean(next.GameDir) {
		return "", fmt.Errorf("数据目录和游戏目录不能相同")
	}
	if next.DepotWorkers <= 0 {
		next.DepotWorkers = 1
	}
	if next.ChunkWorkers <= 0 {
		next.ChunkWorkers = 8
	}

	oldDir := a.settings.DataDir
	migrated := 0
	if filepath.Clean(oldDir) != filepath.Clean(next.DataDir) {
		migrated = migrateData(oldDir, next.DataDir)
	}

	a.settings = next
	if err := saveSettings(next); err != nil {
		return "", err
	}
	a.reload()
	if migrated > 0 {
		return fmt.Sprintf("已保存，并迁移 %d 个数据文件", migrated), nil
	}
	return "已保存", nil
}

// migrateData copies known data files into the new folder; failures are non-fatal.
func migrateData(from, to string) int {
	moved := 0
	for _, name := range []string{"keys.json", "index.json"} {
		src := filepath.Join(from, name)
		if _, err := os.Stat(src); err != nil {
			continue
		}
		dst := filepath.Join(to, name)
		if _, err := os.Stat(dst); err == nil {
			continue
		}
		if err := copyFile(src, dst); err == nil {
			moved++
		}
	}
	return moved
}

func copyFile(src, dst string) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

// PickFolder opens the native folder picker.
func (a *App) PickFolder(title, startDir string) string {
	dir, err := runtime.OpenDirectoryDialog(a.ctx, runtime.OpenDialogOptions{
		Title:            title,
		DefaultDirectory: startDir,
	})
	if err != nil {
		return ""
	}
	return dir
}

// OpenFolder reveals a folder in Explorer.
func (a *App) OpenFolder(path string) string {
	if err := os.MkdirAll(path, 0o755); err != nil {
		return err.Error()
	}
	if err := openInExplorer(path); err != nil {
		return err.Error()
	}
	return ""
}

func fetchJSON(url string) (map[string]string, error) {
	client := &http.Client{Timeout: 180 * time.Second}
	request, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", "relaystore/"+a1Version)
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

// BootstrapData downloads the depot key corpora into the configured data folder.
func (a *App) BootstrapData() string {
	go func() {
		target := a.keysPath()
		runtime.EventsEmit(a.ctx, "data:progress", map[string]any{"stage": "prepare", "target": target})
		if err := os.MkdirAll(a.settings.DataDir, 0o755); err != nil {
			runtime.EventsEmit(a.ctx, "data:error", "数据目录不可写："+err.Error())
			return
		}
		merged := map[string]string{}
		for i, url := range keyCorpora {
			runtime.EventsEmit(a.ctx, "data:progress", map[string]any{
				"stage": "download", "index": i + 1, "total": len(keyCorpora),
				"percent": float64(i) / float64(len(keyCorpora)) * 100, "source": url,
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
		if err := os.WriteFile(target, data, 0o644); err != nil {
			runtime.EventsEmit(a.ctx, "data:error", err.Error())
			return
		}
		a.reload()
		runtime.EventsEmit(a.ctx, "data:done", map[string]any{"keys": len(merged), "path": target})
	}()
	return "started"
}

// Coverage returns the downloadable report as JSON (same shape as the CLI).
func (a *App) Coverage(appid int) (string, error) {
	report, err := core.CheckCoverage(appid, a.keys, a.idx, a.appinfoDir(), nil)
	if err != nil {
		return "", err
	}
	data, err := json.Marshal(report)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// GamePath suggests <gameDir>\<appid> for the given app.
func (a *App) GamePath(appid int) string {
	return filepath.Join(a.settings.GameDir, fmt.Sprint(appid))
}

// Restore starts a background restore and streams per-depot events to the UI.
func (a *App) Restore(appid int, target string, depotWorkers int) string {
	go func() {
		if strings.TrimSpace(target) == "" {
			target = a.GamePath(appid)
		}
		runtime.EventsEmit(a.ctx, "restore:start", appid)
		preferArch := ""
		if report := a.InspectGame(appid); report.Exe != "" {
			preferArch = peArch(report.Exe)
		}
		result, err := core.RestoreApp(
			appid,
			target,
			a.keys,
			a.idx,
			a.appinfoDir(),
			a.settings.ChunkWorkers,
			depotWorkers,
			filepath.Join(target, ".relaystore-state.json"),
			preferArch,
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