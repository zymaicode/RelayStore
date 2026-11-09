package main

import (
	"os"
	"os/exec"
	"encoding/json"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// GameInspection is the pre-launch report for one installed game.
type GameInspection struct {
	AppID     int      `json:"appid"`
	Path      string   `json:"path"`
	Exe       string   `json:"exe"`
	SizeBytes int64    `json:"bytes"`
	Files     int      `json:"files"`
	Flags     []string `json:"flags"`
	Verdict   string   `json:"verdict"`
	Detail    string   `json:"detail"`
	LastExit  int      `json:"lastExit"`
	LastExitAt int64   `json:"lastExitAt"`
}

var junkExe = []string{
	"unins", "setup", "redist", "vcredist", "dxsetup", "dxwebsetup", "dotnet",
	"crashpad", "crashreport", "unitycrashhandler", "ue4prereqsetup", "ue5prereqsetup",
	"installer", "launcher_installer", "easyanticheat", "battleye", "notepad",
}

// isEmuName spots a Steam runtime replacement shipped next to the game.
func isEmuName(name string) bool {
	for _, token := range []string{"goldberg", "steamclient_loader", "smartsteam", "creamapi", "steam_api_emu"} {
		if strings.Contains(name, token) {
			return true
		}
	}
	return false
}

func isJunkExe(name string) bool {
	lower := strings.ToLower(name)
	for _, token := range junkExe {
		if strings.Contains(lower, token) {
			return true
		}
	}
	return false
}

func containsBytes(path string, needle []byte, limit int64) bool {
	file, err := os.Open(path)
	if err != nil {
		return false
	}
	defer file.Close()
	buf := make([]byte, 4<<20)
	var read int64
	carry := []byte{}
	for read < limit {
		n, err := file.Read(buf)
		if n > 0 {
			read += int64(n)
			chunk := append(carry, buf[:n]...)
			if strings.Contains(strings.ToLower(string(chunk)), strings.ToLower(string(needle))) {
				return true
			}
			if len(chunk) >= len(needle) {
				carry = chunk[len(chunk)-len(needle)+1:]
			}
		}
		if err != nil {
			break
		}
	}
	return false
}

// InspectGame scans the install folder and reports what it will take to launch.
func (a *App) InspectGame(appid int) GameInspection {
	path := a.InstallPathFor(appid)
	key := strconv.Itoa(appid)
	useCache := a.settings.DataDir != ""
	if cached, ok := a.loadCache()[key]; useCache && ok && time.Since(time.Unix(cached.CheckedAt, 0)) < inspectionTTL {
		return GameInspection{
			AppID:     appid,
			Path:      path,
			Exe:       cached.Exe,
			SizeBytes: cached.Bytes,
			Files:     cached.Files,
			Flags:     cached.Flags,
			Verdict:   cached.Verdict,
			Detail:    cached.Detail,
		}
	}
	report := GameInspection{AppID: appid, Path: path, Flags: []string{}}
	info, err := os.Stat(path)
	if err != nil || !info.IsDir() {
		report.Verdict = "missing"
		report.Detail = "安装目录不存在"
		return report
	}

	type candidate struct {
		path string
		size int64
	}
	var exes, dlls []candidate
	hasSteamAPI, hasEmu, hasDenuvo, hasAntiCheat := false, false, false, false
	_ = filepath.Walk(path, func(p string, fi os.FileInfo, err error) error {
		if err != nil || fi == nil || fi.IsDir() {
			return nil
		}
		report.Files++
		report.SizeBytes += fi.Size()
		lower := strings.ToLower(fi.Name())
		switch {
		case strings.HasSuffix(lower, ".exe"):
			if isEmuName(lower) {
				hasEmu = true
			}
			if !isJunkExe(lower) {
				exes = append(exes, candidate{p, fi.Size()})
			}
		case strings.HasSuffix(lower, ".dll"):
			dlls = append(dlls, candidate{p, fi.Size()})
		}
		return nil
	})

	sort.Slice(exes, func(i, j int) bool { return exes[i].size > exes[j].size })
	if len(exes) > 0 {
		report.Exe = exes[0].path
	}
	if override := a.loadOverrides()[strconv.Itoa(appid)]; override != "" {
		if info, err := os.Stat(override); err == nil && !info.IsDir() {
			report.Exe = override
			report.Flags = append(report.Flags, "exe_pinned")
		}
	}
	for _, dll := range dlls {
		lower := strings.ToLower(filepath.Base(dll.path))
		switch {
		case strings.HasPrefix(lower, "steam_api"), lower == "steamclient64.dll", lower == "steamclient.dll":
			hasSteamAPI = true
		case isEmuName(lower):
			hasEmu = true
		case strings.Contains(lower, "denuvo"):
			hasDenuvo = true
		case strings.Contains(lower, "easyanticheat") || strings.Contains(lower, "battleye"):
			hasAntiCheat = true
		}
	}

	if report.Exe != "" && hasDenuvo {
		hasDenuvo = hasDenuvo || containsBytes(report.Exe, []byte("Denuvo"), 24<<20)
	}
	if report.Exe != "" && !hasSteamAPI {
		hasSteamAPI = containsBytes(report.Exe, []byte("steam_api64.dll"), 24<<20) ||
			containsBytes(report.Exe, []byte("SteamAPI_Init"), 24<<20) ||
			containsBytes(report.Exe, []byte("RestartAppIfNecessary"), 24<<20)
	}

	if hasSteamAPI {
		report.Flags = append(report.Flags, "steam_api")
	}
	if hasEmu {
		report.Flags = append(report.Flags, "runtime_layer")
	}
	if hasDenuvo {
		report.Flags = append(report.Flags, "denuvo")
	}
	if hasAntiCheat {
		report.Flags = append(report.Flags, "anticheat")
	}

	switch {
	case report.Exe == "":
		report.Verdict = "no_exe"
		report.Detail = "没有找到可执行文件"
	case hasDenuvo:
		report.Verdict = "drm_locked"
		report.Detail = "含 Denuvo 保护，当前不支持启动"
	case hasSteamAPI && !hasEmu:
		report.Verdict = "needs_steam"
		report.Detail = "依赖 Steamworks 授权；直接启动会被要求通过 Steam 拉起"
	case hasAntiCheat:
		report.Verdict = "anticheat"
		report.Detail = "含反作弊组件，联机模式需要官方客户端"
	default:
		report.Verdict = "ready"
		report.Detail = "不依赖 Steam 授权，可直接启动"
	}

	if result, ok := a.lastLaunchResult(appid); ok {
		report.LastExit = result.ExitCode
		report.LastExitAt = result.At
	}
	if !useCache {
		return report
	}
	cache := a.loadCache()
	cache[strconv.Itoa(appid)] = inspectionCacheEntry{
		Verdict:   report.Verdict,
		Detail:    report.Detail,
		Exe:       report.Exe,
		Flags:     report.Flags,
		Bytes:     report.SizeBytes,
		Files:     report.Files,
		CheckedAt: time.Now().Unix(),
	}
	a.saveCache(cache)
	return report
}

// ensureRuntimeForLaunch installs the runtime layer when a game needs it.
// It returns a human note when something was changed or when it could not help.
func (a *App) ensureRuntimeForLaunch(appid int) string {
	report := a.InspectGame(appid)
	if report.Verdict != "needs_steam" {
		return ""
	}
	status := a.RuntimeStatus(appid)
	needLoader := status.Mode == ""
	if status.Mode == "shim" {
		if result, ok := a.lastLaunchResult(appid); ok && result.ExitCode != 0 {
			needLoader = true // the shim did not survive last time, escalate to the loader
		}
	}
	if !needLoader {
		return ""
	}
	if _, err := a.InstallRuntimeLoader(appid); err != nil {
		return "运行时层不可用：" + err.Error()
	}
	// the shim DLL would shadow the loader for some titles, so restore the original
	if status.Backup {
		_, _ = a.RemoveRuntime(appid)
	}
	return "已自动启用运行时层（loader）"
}

// LaunchGame starts the game executable with the install folder as working directory.
// It auto-enables the runtime layer for Steam-dependent titles.
func (a *App) LaunchGame(appid int) string {
	report := a.InspectGame(appid)
	if report.Exe == "" {
		return report.Detail
	}
	note := a.ensureRuntimeForLaunch(appid)
	target := report.Exe
	if status := a.RuntimeStatus(appid); status.Mode == "loader" && status.Loader != "" {
		target = status.Loader
	}
	cmd := exec.Command(target)
	cmd.Dir = filepath.Dir(report.Exe)
	cmd.Env = append(os.Environ(), "SteamAppId="+strconv.Itoa(appid), "SteamGameId="+strconv.Itoa(appid))
	if err := cmd.Start(); err != nil {
		return err.Error()
	}
	go func() {
		err := cmd.Wait()
		code := 0
		if err != nil {
			if exitErr, ok := err.(*exec.ExitError); ok {
				code = exitErr.ExitCode()
			} else {
				code = -1
			}
		}
		a.recordLaunchResult(appid, code)
		a.RefreshInspection(appid)
	}()
	return note
}
// ---- executable overrides + inspection cache (both live in the data dir) ----

type exeOverrides map[string]string

type inspectionCacheEntry struct {
	Verdict   string   `json:"verdict"`
	Detail    string   `json:"detail"`
	Exe       string   `json:"exe"`
	Flags     []string `json:"flags"`
	Bytes     int64    `json:"bytes"`
	Files     int      `json:"files"`
	CheckedAt int64    `json:"checkedAt"`
}

const inspectionTTL = 30 * time.Minute

func (a *App) overridePath() string {
	return filepath.Join(a.settings.DataDir, "exe-overrides.json")
}

func (a *App) cachePath() string {
	return filepath.Join(a.settings.DataDir, "inspect-cache.json")
}

func (a *App) loadOverrides() exeOverrides {
	out := exeOverrides{}
	if data, err := os.ReadFile(a.overridePath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	return out
}

func (a *App) loadCache() map[string]inspectionCacheEntry {
	out := map[string]inspectionCacheEntry{}
	if data, err := os.ReadFile(a.cachePath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	return out
}

func (a *App) saveCache(cache map[string]inspectionCacheEntry) {
	if err := os.MkdirAll(filepath.Dir(a.cachePath()), 0o755); err != nil {
		return
	}
	if data, err := json.Marshal(cache); err == nil {
		_ = os.WriteFile(a.cachePath(), data, 0o644)
	}
}

// SetGameExe pins a specific executable for a game and drops its cache entry.
func (a *App) SetGameExe(appid int, exe string) string {
	overrides := a.loadOverrides()
	key := strconv.Itoa(appid)
	if exe == "" {
		delete(overrides, key)
	} else {
		overrides[key] = exe
	}
	if err := os.MkdirAll(filepath.Dir(a.overridePath()), 0o755); err == nil {
		if data, err := json.Marshal(overrides); err == nil {
			_ = os.WriteFile(a.overridePath(), data, 0o644)
		}
	}
	cache := a.loadCache()
	delete(cache, key)
	a.saveCache(cache)
	return exe
}

// PickGameExe opens a file dialog inside the install folder.
func (a *App) PickGameExe(appid int) string {
	dir := a.InstallPathFor(appid)
	choice, err := runtime.OpenFileDialog(a.ctx, runtime.OpenDialogOptions{
		Title:            "选择游戏主程序",
		DefaultDirectory: dir,
		Filters:          []runtime.FileFilter{{DisplayName: "可执行文件 (*.exe)", Pattern: "*.exe"}},
	})
	if err != nil || choice == "" {
		return ""
	}
	return a.SetGameExe(appid, choice)
}

// RefreshInspection clears the cached verdict for one app.
func (a *App) RefreshInspection(appid int) string {
	cache := a.loadCache()
	delete(cache, strconv.Itoa(appid))
	a.saveCache(cache)
	return "ok"
}
// ---- launch results (so a crash is remembered and shown next time) ----

type launchResult struct {
	ExitCode int   `json:"exitCode"`
	At       int64 `json:"at"`
}

func (a *App) launchResultsPath() string {
	return filepath.Join(a.settings.DataDir, "launch-results.json")
}

func (a *App) recordLaunchResult(appid int, code int) {
	if a.settings.DataDir == "" {
		return
	}
	all := map[string]launchResult{}
	if data, err := os.ReadFile(a.launchResultsPath()); err == nil {
		_ = json.Unmarshal(data, &all)
	}
	all[strconv.Itoa(appid)] = launchResult{ExitCode: code, At: time.Now().Unix()}
	if err := os.MkdirAll(filepath.Dir(a.launchResultsPath()), 0o755); err == nil {
		if data, err := json.Marshal(all); err == nil {
			_ = os.WriteFile(a.launchResultsPath(), data, 0o644)
		}
	}
}

func (a *App) lastLaunchResult(appid int) (launchResult, bool) {
	if a.settings.DataDir == "" {
		return launchResult{}, false
	}
	all := map[string]launchResult{}
	if data, err := os.ReadFile(a.launchResultsPath()); err == nil {
		_ = json.Unmarshal(data, &all)
	}
	result, ok := all[strconv.Itoa(appid)]
	return result, ok
}