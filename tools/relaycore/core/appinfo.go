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

func steamcmdPath() string {
	if custom := os.Getenv("STEAMCMD"); custom != "" {
		return custom
	}
	for _, candidate := range []string{"tools/bin/steamcmd.exe", "tools\\bin\\steamcmd.exe"} {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
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
