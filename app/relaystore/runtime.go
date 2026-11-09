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
	DLL       string `json:"dll"`
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

func (a *App) gameDLL(appid int, arch string) string {
	dir := a.InstallPathFor(appid)
	if arch == "x32" {
		return filepath.Join(dir, "steam_api.dll")
	}
	return filepath.Join(dir, "steam_api64.dll")
}

// RuntimeStatus reports the emulator state for one game.
func (a *App) RuntimeStatus(appid int) RuntimeStatus {
	report := a.InspectGame(appid)
	arch := peArch(report.Exe)
	if arch == "" {
		arch = "x32"
	}
	status := RuntimeStatus{AppID: appid, Arch: arch, Note: emulatorLicenseNote}
	dll := a.gameDLL(appid, arch)
	status.DLL = dll
	if info, err := os.Stat(dll); err == nil {
		status.Installed = info.Size() > 1<<20
	}
	if _, err := os.Stat(dll + ".orig"); err == nil {
		status.Backup = true
	}
	return status
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
	source := filepath.Join(dir, "experimental", status.Arch, "steam_api.dll")
	if status.Arch == "x64" {
		source = filepath.Join(dir, "experimental", "x64", "steam_api64.dll")
	}
	if _, err := os.Stat(source); err != nil {
		return "", fmt.Errorf("运行时层缺少 %s 版本：%v", status.Arch, err)
	}
	target := a.gameDLL(appid, status.Arch)
	if _, err := os.Stat(target); err == nil {
		if _, err := os.Stat(target + ".orig"); err != nil {
			if err := os.Rename(target, target+".orig"); err != nil {
				return "", fmt.Errorf("备份原 DLL 失败：%v", err)
			}
		}
	}
	in, err := os.Open(source)
	if err != nil {
		return "", err
	}
	defer in.Close()
	out, err := os.Create(target)
	if err != nil {
		return "", err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return "", err
	}
	out.Close()

	gameDir := a.InstallPathFor(appid)
	_ = os.WriteFile(filepath.Join(gameDir, "steam_appid.txt"), []byte(strconv.Itoa(appid)), 0o644)
	settingsDir := filepath.Join(gameDir, "steam_settings")
	_ = os.MkdirAll(settingsDir, 0o755)
	_ = os.WriteFile(filepath.Join(settingsDir, "configs.appid"), []byte(strconv.Itoa(appid)), 0o644)

	a.RefreshInspection(appid)
	return fmt.Sprintf("已为 AppID %d 启用运行时层（%s）", appid, status.Arch), nil
}

// RemoveRuntime restores the original DLL (or deletes the emulator copy).
func (a *App) RemoveRuntime(appid int) (string, error) {
	status := a.RuntimeStatus(appid)
	target := a.gameDLL(appid, status.Arch)
	if _, err := os.Stat(target + ".orig"); err == nil {
		_ = os.Remove(target)
		if err := os.Rename(target+".orig", target); err != nil {
			return "", fmt.Errorf("恢复原 DLL 失败：%v", err)
		}
	} else if err := os.Remove(target); err != nil && !os.IsNotExist(err) {
		return "", err
	}
	gameDir := a.InstallPathFor(appid)
	_ = os.Remove(filepath.Join(gameDir, "steam_appid.txt"))
	_ = os.RemoveAll(filepath.Join(gameDir, "steam_settings"))
	a.RefreshInspection(appid)
	return "已移除运行时层", nil
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