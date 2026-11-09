package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// EmulatorRelease is the community Steamworks replacement we fetch on demand.
// Source: github.com/alex47exe/gse_fork (LGPL-3.0). It is never bundled with the installer.
const emulatorReleaseURL = "https://github.com/alex47exe/gse_fork/releases/download/2026_02_16/emu-win-release.7z"

const emulatorLicenseNote = "运行时层使用 gse_fork（LGPL-3.0），按需下载，不随安装包分发"

// RuntimeStatus describes whether a game carries the emulator layer.
type RuntimeStatus struct {
	AppID     int    `json:"appid"`
	Installed bool   `json:"installed"`
	DLL       string   `json:"dll"`
	Targets   []string `json:"targets"`
	Mode      string   `json:"mode"`
	Loader    string   `json:"loader"`
	Backup    bool   `json:"backup"`
	Arch      string `json:"arch"`
	Note      string `json:"note"`
}

func (a *App) runtimeDir() string {
	return filepath.Join(a.settings.DataDir, "runtime")
}

// peArch reports the machine type of a Windows executable.
func peArch(path string) string {
	data, err := os.ReadFile(path)
	if err != nil || len(data) < 0x40 {
		return ""
	}
	offset := int(uint32(data[0x3C]) | uint32(data[0x3D])<<8 | uint32(data[0x3E])<<16 | uint32(data[0x3F])<<24)
	if offset <= 0 || offset+6 > len(data) || data[offset] != 'P' || data[offset+1] != 'E' {
		return ""
	}
	machine := uint16(data[offset+4]) | uint16(data[offset+5])<<8
	switch machine {
	case 0x014c:
		return "x32"
	case 0x8664:
		return "x64"
	}
	return ""
}

// findSteamDLLs returns every steam_api dll inside a game folder (Unity keeps them under Data/Plugins).
func findSteamDLLs(gameDir string) []string {
	var out []string
	_ = filepath.Walk(gameDir, func(p string, info os.FileInfo, err error) error {
		if err != nil || info == nil || info.IsDir() {
			return nil
		}
		lower := strings.ToLower(info.Name())
		if lower == "steam_api.dll" || lower == "steam_api64.dll" {
			out = append(out, p)
		}
		return nil
	})
	return out
}

func (a *App) gameDLL(appid int, arch string) string {
	dir := a.InstallPathFor(appid)
	found := findSteamDLLs(dir)
	// prefer a dll whose bitness matches the executable
	for _, dll := range found {
		if peArchOfDLL(dll) == arch {
			return dll
		}
	}
	if len(found) > 0 {
		return found[0]
	}
	if arch == "x64" {
		return filepath.Join(dir, "steam_api64.dll")
	}
	return filepath.Join(dir, "steam_api.dll")
}

func peArchOfDLL(path string) string {
	lower := strings.ToLower(filepath.Base(path))
	if strings.Contains(lower, "64") {
		return "x64"
	}
	return "x32"
}

// RuntimeStatus reports the emulator state for one game.
func (a *App) RuntimeStatus(appid int) RuntimeStatus {
	report := a.InspectGame(appid)
	arch := peArch(report.Exe)
	if arch == "" {
		arch = "x32"
	}
	status := RuntimeStatus{AppID: appid, Arch: arch, Note: emulatorLicenseNote}
	dir := a.InstallPathFor(appid)
	targets := findSteamDLLs(dir)
	if len(targets) == 0 {
		targets = []string{a.gameDLL(appid, arch)}
	}
	status.DLL = targets[0]
	for _, target := range targets {
		if info, err := os.Stat(target); err == nil && info.Size() > 1<<20 {
			status.Installed = true
		}
		if _, err := os.Stat(target + ".orig"); err == nil {
			status.Backup = true
		}
	}
	status.Targets = targets
	for _, name := range []string{"steamclient_loader_x32.exe", "steamclient_loader_x64.exe"} {
		candidate := filepath.Join(dir, name)
		if _, err := os.Stat(candidate); err == nil {
			status.Mode = "loader"
			status.Loader = candidate
			break
		}
	}
	if status.Mode == "" && status.Installed {
		status.Mode = "shim"
	}
	return status
}

// linkOrCopy prefers a hard link (no extra disk) and falls back to copying across volumes.
func linkOrCopy(source, target string) (linked bool, err error) {
	_ = os.Remove(target)
	if linkErr := os.Link(source, target); linkErr == nil {
		return true, nil
	}
	in, err := os.Open(source)
	if err != nil {
		return false, err
	}
	defer in.Close()
	out, err := os.Create(target)
	if err != nil {
		return false, err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return false, err
	}
	return false, out.Close()
}

// ensureEmulatorArchive downloads and extracts the emulator package once.
func (a *App) ensureEmulatorArchive() (string, error) {
	dir := a.runtimeDir()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	marker := filepath.Join(dir, "experimental", "x32", "steam_api.dll")
	if _, err := os.Stat(marker); err == nil {
		return dir, nil
	}
	archive := filepath.Join(dir, "emu-win-release.7z")
	if _, err := os.Stat(archive); err != nil {
		client := &http.Client{Timeout: 10 * time.Minute}
		response, err := client.Get(emulatorReleaseURL)
		if err != nil {
			return "", fmt.Errorf("下载运行时层失败：%w", err)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			return "", fmt.Errorf("下载运行时层失败：HTTP %d", response.StatusCode)
		}
		file, err := os.Create(archive)
		if err != nil {
			return "", err
		}
		if _, err := io.Copy(file, response.Body); err != nil {
			file.Close()
			return "", err
		}
		file.Close()
	}
	cmd := exec.Command("tar", "-xf", archive, "-C", dir)
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", fmt.Errorf("解压运行时层失败：%v %s", err, string(out))
	}
	// the archive nests everything under release/; flatten it so paths are stable
	releaseDir := filepath.Join(dir, "release")
	if entries, err := os.ReadDir(releaseDir); err == nil {
		for _, entry := range entries {
			from := filepath.Join(releaseDir, entry.Name())
			to := filepath.Join(dir, entry.Name())
			_ = os.RemoveAll(to)
			_ = os.Rename(from, to)
		}
		_ = os.RemoveAll(releaseDir)
	}
	if _, err := os.Stat(marker); err != nil {
		return "", fmt.Errorf("运行时层解压后缺少 steam_api.dll")
	}
	return dir, nil
}

// InstallRuntime drops the emulator DLL into the game folder, keeping a backup.
func (a *App) InstallRuntime(appid int) (string, error) {
	status := a.RuntimeStatus(appid)
	dir, err := a.ensureEmulatorArchive()
	if err != nil {
		return "", err
	}
	replaced := 0
	for _, target := range status.Targets {
		arch := status.Arch
		if info, statErr := os.Stat(target); statErr == nil {
			_ = info
		}
		arch = peArchOfDLL(target)
		source := filepath.Join(dir, "experimental", arch, "steam_api.dll")
		if arch == "x64" {
			source = filepath.Join(dir, "experimental", "x64", "steam_api64.dll")
		}
		if _, err := os.Stat(source); err != nil {
			continue
		}
		if _, err := os.Stat(target); err == nil {
			if _, err := os.Stat(target + ".orig"); err != nil {
				if err := os.Rename(target, target+".orig"); err != nil {
					return "", fmt.Errorf("备份原 DLL 失败：%v", err)
				}
			}
		} else if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return "", err
		}
		in, err := os.Open(source)
		if err != nil {
			return "", err
		}
		out, err := os.Create(target)
		if err != nil {
			in.Close()
			return "", err
		}
		if _, err := io.Copy(out, in); err != nil {
			out.Close()
			in.Close()
			return "", err
		}
		out.Close()
		in.Close()
		replaced++
	}
	if replaced == 0 {
		return "", fmt.Errorf("没有找到可替换的 steam_api 组件")
	}
	gameDir := a.InstallPathFor(appid)
	_ = os.WriteFile(filepath.Join(gameDir, "steam_appid.txt"), []byte(strconv.Itoa(appid)), 0o644)
	settingsDir := filepath.Join(gameDir, "steam_settings")
	_ = os.MkdirAll(settingsDir, 0o755)
	_ = os.WriteFile(filepath.Join(settingsDir, "configs.appid"), []byte(strconv.Itoa(appid)), 0o644)
	a.RefreshInspection(appid)
	return fmt.Sprintf("已为 AppID %d 启用运行时层（%s，替换 %d 个组件）", appid, status.Arch, replaced), nil
}

// RemoveRuntime restores the original DLL (or deletes the emulator copy).
func (a *App) RemoveRuntime(appid int) (string, error) {
	status := a.RuntimeStatus(appid)
	restored := 0
	for _, target := range status.Targets {
		if _, err := os.Stat(target + ".orig"); err == nil {
			_ = os.Remove(target)
			if err := os.Rename(target+".orig", target); err != nil {
				return "", fmt.Errorf("恢复原 DLL 失败：%v", err)
			}
			restored++
		}
	}
	gameDir := a.InstallPathFor(appid)
	_ = os.Remove(filepath.Join(gameDir, "steam_appid.txt"))
	_ = os.RemoveAll(filepath.Join(gameDir, "steam_settings"))
	a.RefreshInspection(appid)
	if restored == 0 {
		return "没有找到可还原的运行时层", nil
	}
	return fmt.Sprintf("已移除运行时层，还原 %d 个组件", restored), nil
}

// RuntimeInfo exposes the layer state to the UI.
func (a *App) RuntimeInfo(appid int) map[string]any {
	status := a.RuntimeStatus(appid)
	report := a.InspectGame(appid)
	return map[string]any{
		"status":  status,
		"verdict": report.Verdict,
		"flags":   report.Flags,
		"license": emulatorLicenseNote,
	}
}

var _ = strings.TrimSpace
var _ = json.Marshal
// InstallRuntimeLoader drops the experimental steamclient + loader into the game folder.
// This covers games (e.g. GameMaker titles) that call interfaces the steam_api shim lacks.
func (a *App) InstallRuntimeLoader(appid int) (string, error) {
	report := a.InspectGame(appid)
	arch := peArch(report.Exe)
	if arch == "" {
		arch = "x32"
	}
	dir, err := a.ensureEmulatorArchive()
	if err != nil {
		return "", err
	}
	clientDir := filepath.Join(dir, "steamclient_experimental")
	if _, err := os.Stat(clientDir); err != nil {
		return "", fmt.Errorf("运行时层缺少 steamclient_experimental 目录")
	}
	gameDir := a.InstallPathFor(appid)
	loaderName := "steamclient_loader_x32.exe"
	if arch == "x64" {
		loaderName = "steamclient_loader_x64.exe"
	}
	files := []string{"steamclient.dll", "steamclient64.dll", loaderName}
		linked := 0
	for _, name := range files {
		source := filepath.Join(clientDir, name)
		if _, err := os.Stat(source); err != nil {
			continue
		}
		ok, err := linkOrCopy(source, filepath.Join(gameDir, name))
		if err != nil {
			return "", err
		}
		if ok {
			linked++
		}
	}
	exeName := filepath.Base(report.Exe)
	ini := fmt.Sprintf("[SteamClient]\nExe=%s\nExeRunDir=\nExeCommandLine=\nAppId=%d\nSteamClientDll=steamclient.dll\nSteamClient64Dll=steamclient64.dll\n", exeName, appid)
	if err := os.WriteFile(filepath.Join(gameDir, "ColdClientLoader.ini"), []byte(ini), 0o644); err != nil {
		return "", err
	}
	_ = os.WriteFile(filepath.Join(gameDir, "steam_appid.txt"), []byte(strconv.Itoa(appid)), 0o644)
	_ = os.MkdirAll(filepath.Join(gameDir, "steam_settings"), 0o755)
	_ = os.WriteFile(filepath.Join(gameDir, "steam_settings", "configs.appid"), []byte(strconv.Itoa(appid)), 0o644)
	a.RefreshInspection(appid)
	return fmt.Sprintf("已启用运行时层（loader/%s，%d 个文件以硬链接方式共享）", arch, linked), nil
}

// RemoveRuntimeLoader deletes the loader files installed by InstallRuntimeLoader.
func (a *App) RemoveRuntimeLoader(appid int) (string, error) {
	gameDir := a.InstallPathFor(appid)
	files := []string{"steamclient.dll", "steamclient64.dll", "GameOverlayRenderer.dll", "GameOverlayRenderer64.dll", "steamclient_loader_x32.exe", "steamclient_loader_x64.exe", "ColdClientLoader.ini"}
	removed := 0
	for _, name := range files {
		if err := os.Remove(filepath.Join(gameDir, name)); err == nil {
			removed++
		}
	}
	_ = os.RemoveAll(filepath.Join(gameDir, "steam_settings"))
	_ = os.Remove(filepath.Join(gameDir, "steam_appid.txt"))
	a.RefreshInspection(appid)
	if removed == 0 {
		return "没有找到可移除的加载器文件", nil
	}
	return fmt.Sprintf("已移除运行时层（%d 个文件）", removed), nil
}
// RuntimeCacheInfo reports the shared emulator cache footprint.
func (a *App) RuntimeCacheInfo() map[string]any {
	dir := a.runtimeDir()
	var total int64
	files := 0
	_ = filepath.Walk(dir, func(p string, info os.FileInfo, err error) error {
		if err != nil || info == nil || info.IsDir() {
			return nil
		}
		total += info.Size()
		files++
		return nil
	})
	return map[string]any{"path": dir, "bytes": total, "files": files}
}

// ClearRuntimeCache removes the shared cache; hard links in game folders survive.
func (a *App) ClearRuntimeCache() (string, error) {
	info := a.RuntimeCacheInfo()
	dir, _ := info["path"].(string)
	if err := os.RemoveAll(dir); err != nil {
		return "", err
	}
	return fmt.Sprintf("已清理运行时缓存（释放 %.1f MB）；已启用运行时层的游戏不受影响", float64(info["bytes"].(int64))/(1<<20)), nil
}
