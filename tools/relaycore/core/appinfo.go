package core

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

type DepotInfo struct {
	DepotID int    `json:"depot_id"`
	GID     string `json:"gid"`
	Size    int64  `json:"size"`
	Name    string `json:"name,omitempty"`
	OS      string `json:"os,omitempty"`
}

// IsWindowsDepot reports whether a depot applies to Windows (empty oslist means all platforms).
func (d DepotInfo) IsWindowsDepot() bool {
	os := strings.ToLower(strings.TrimSpace(d.OS))
	if os == "" {
		return true
	}
	return strings.Contains(os, "windows")
}

// WindowsDepots keeps only the depots a Windows install needs.
func WindowsDepots(list []DepotInfo) []DepotInfo {
	out := make([]DepotInfo, 0, len(list))
	for _, depot := range list {
		if depot.IsWindowsDepot() {
			out = append(out, depot)
		}
	}
	return out
}

// extractAppBlock cuts the `"<appid>" { ... }` block out of steamcmd output.
func extractAppBlock(raw string, appid int) (string, error) {
	marker := "\"" + strconv.Itoa(appid) + "\""
	index := strings.Index(raw, marker)
	if index < 0 {
		return "", fmt.Errorf("appid %d not found in steamcmd output", appid)
	}
	depth, started, end := 0, false, index
	for pos := index; pos < len(raw); pos++ {
		switch raw[pos] {
		case '{':
			depth++
			started = true
		case '}':
			depth--
			if started && depth == 0 {
				end = pos + 1
				pos = len(raw)
			}
		}
	}
	if !started || depth != 0 {
		return "", fmt.Errorf("unbalanced block for appid %d", appid)
	}
	return raw[index:end], nil
}

func depotsFromAppInfo(root *Node) []DepotInfo {
	depotsNode := root.Child("depots")
	if depotsNode == nil {
		return nil
	}
	var out []DepotInfo
	for _, depot := range depotsNode.Children {
		id := atoiSafe(depot.Key)
		if id <= 0 {
			continue
		}
		info := DepotInfo{DepotID: id, Name: depot.Value}
		if config := depot.Child("config"); config != nil {
			if osNode := config.Child("oslist"); osNode != nil {
				info.OS = osNode.Value
			}
		}
		if public := depot.Path("manifests", "public"); public != nil {
			if gid := public.Child("gid"); gid != nil {
				info.GID = gid.Value
			}
			if size := public.Child("size"); size != nil {
				info.Size = atoi64Safe(size.Value)
			}
		}
		if info.GID == "" {
			continue
		}
		out = append(out, info)
	}
	return out
}

func parseAppInfo(raw string, appid int) ([]DepotInfo, error) {
	block, err := extractAppBlock(raw, appid)
	if err != nil {
		return nil, err
	}
	root, err := ParseVDF(block)
	if err != nil {
		return nil, err
	}
	// the block is `"<appid>" { ... }`: descend into the single child
	var app *Node
	for _, child := range root.Children {
		if child.Key == strconv.Itoa(appid) {
			app = child
			break
		}
	}
	if app == nil && len(root.Children) == 1 {
		app = root.Children[0]
	}
	if app == nil {
		return nil, fmt.Errorf("app block %d missing", appid)
	}
	return depotsFromAppInfo(app), nil
}

// ParseAppName extracts common.name from a steamcmd app_info_print dump.
func ParseAppName(raw string, appid int) (string, error) {
	block, err := extractAppBlock(raw, appid)
	if err != nil {
		return "", err
	}
	root, err := ParseVDF(block)
	if err != nil {
		return "", err
	}
	var app *Node
	for _, child := range root.Children {
		if child.Key == strconv.Itoa(appid) {
			app = child
			break
		}
	}
	if app == nil && len(root.Children) == 1 {
		app = root.Children[0]
	}
	if app == nil {
		return "", fmt.Errorf("app block %d missing", appid)
	}
	if common := app.Child("common"); common != nil {
		if name := common.Child("name"); name != nil {
			return name.Value, nil
		}
	}
	return "", fmt.Errorf("no common.name for appid %d", appid)
}

// AppName returns the display name, caching it next to the appinfo depot cache.
func AppName(appid int, cacheDir string) (string, error) {
	cacheFile := ""
	if cacheDir != "" {
		cacheFile = filepath.Join(cacheDir, strconv.Itoa(appid)+".name")
		if data, err := os.ReadFile(cacheFile); err == nil && len(data) > 0 {
			return strings.TrimSpace(string(data)), nil
		}
	}
	cmd := exec.Command(steamcmdPath(), "+login", "anonymous", "+app_info_print", strconv.Itoa(appid), "+quit")
	output, err := cmd.CombinedOutput()
	if err != nil && len(output) == 0 {
		return "", err
	}
	name, err := ParseAppName(string(output), appid)
	if err != nil {
		return "", err
	}
	if cacheFile != "" {
		_ = os.MkdirAll(cacheDir, 0o755)
		_ = os.WriteFile(cacheFile, []byte(name), 0o644)
	}
	return name, nil
}

func steamcmdPath() string {
	if custom := os.Getenv("STEAMCMD"); custom != "" {
		return custom
	}
	relative := filepath.Join("tools", "bin", "steamcmd.exe")
	if _, err := os.Stat(relative); err == nil {
		return relative
	}
	// walk up from the working directory and the executable so a portable copy works
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
			candidate := filepath.Join(dir, relative)
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
	return "steamcmd"
}

// PublicDepots returns the public depot list, using an on-disk cache when available.
func PublicDepots(appid int, cacheDir string) ([]DepotInfo, error) {
	var cacheFile string
	if cacheDir != "" {
		cacheFile = filepath.Join(cacheDir, strconv.Itoa(appid)+".json")
		if data, err := os.ReadFile(cacheFile); err == nil {
			var cached []DepotInfo
			if json.Unmarshal(data, &cached) == nil && len(cached) > 0 {
				return cached, nil
			}
		}
	}

	cmd := exec.Command(steamcmdPath(), "+login", "anonymous", "+app_info_print", strconv.Itoa(appid), "+quit")
	output, err := cmd.CombinedOutput()
	if err != nil && len(output) == 0 {
		return nil, err
	}
	depots, err := parseAppInfo(string(output), appid)
	if err != nil {
		return nil, err
	}
	if cacheFile != "" {
		if err := os.MkdirAll(cacheDir, 0o755); err == nil {
			if data, err := json.MarshalIndent(depots, "", " "); err == nil {
				_ = os.WriteFile(cacheFile, data, 0o644)
			}
		}
	}
	return depots, nil
}
