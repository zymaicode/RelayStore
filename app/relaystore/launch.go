package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
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
	return report
}

// LaunchGame starts the game executable with the install folder as working directory.
func (a *App) LaunchGame(appid int) string {
	report := a.InspectGame(appid)
	if report.Exe == "" {
		return report.Detail
	}
	cmd := exec.Command(report.Exe)
	cmd.Dir = filepath.Dir(report.Exe)
	cmd.Env = append(os.Environ(), "SteamAppId="+strconv.Itoa(appid), "SteamGameId="+strconv.Itoa(appid))
	if err := cmd.Start(); err != nil {
		return err.Error()
	}
	go func() { _ = cmd.Wait() }()
	return ""
}