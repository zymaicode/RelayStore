package main

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

const onlineCatalogURL = "https://raw.githubusercontent.com/zymaicode/RelayStore/main/updates/store-catalog.json"

var onlineMu sync.Mutex

func onlineCachePath() string {
	return filepath.Join(loadSettings().DataDir, "catalog-online.json")
}

func readCatalogFile(path string) (catalogFile, error) {
	var file catalogFile
	data, err := os.ReadFile(path)
	if err != nil {
		return file, err
	}
	if err := json.Unmarshal(data, &file); err != nil {
		return file, err
	}
	seen := map[int]bool{}
	unique := make([]CatalogGame, 0, len(file.Games))
	for _, game := range file.Games {
		if game.AppID == 0 || seen[game.AppID] {
			continue
		}
		seen[game.AppID] = true
		unique = append(unique, game)
	}
	file.Games = unique
	return file, nil
}

// loadOnlineCatalog fetches the repo-hosted catalog, caching it for offline reuse.
func loadOnlineCatalog() (catalogFile, error) {
	onlineMu.Lock()
	defer onlineMu.Unlock()

	cache := onlineCachePath()
	if info, err := os.Stat(cache); err == nil && time.Since(info.ModTime()) < 6*time.Hour {
		if file, err := readCatalogFile(cache); err == nil && len(file.Games) > 0 {
			return file, nil
		}
	}
	body, err := httpGetOnce(onlineCatalogURL)
	if err != nil {
		if file, cachedErr := readCatalogFile(cache); cachedErr == nil && len(file.Games) > 0 {
			return file, nil
		}
		return catalogFile{}, err
	}
	if err := os.MkdirAll(filepath.Dir(cache), 0o755); err == nil {
		_ = os.WriteFile(cache, body, 0o644)
	}
	file, err := readCatalogFile(cache)
	if err != nil {
		var direct catalogFile
		if jsonErr := json.Unmarshal(body, &direct); jsonErr != nil {
			return catalogFile{}, jsonErr
		}
		return direct, nil
	}
	return file, nil
}

// lookupAppid resolves a single appid through api.steamcmd.net (reachable in CN).
func lookupAppid(appid int) (CatalogGame, error) {
	meta, err := fetchFromSteamcmdNet(appid)
	if err != nil {
		return CatalogGame{AppID: appid}, err
	}
	return CatalogGame{AppID: appid, Name: meta.Name}, nil
}

// StoreList returns games for the given source and query.
func (a *App) StoreList(source, query string) map[string]any {
	q := strings.TrimSpace(query)
	switch source {
	case "online":
		file, err := loadOnlineCatalog()
		if err != nil {
			return map[string]any{"source": source, "updated": "", "games": []CatalogGame{}, "error": "在线榜单不可用：" + err.Error()}
		}
		return map[string]any{"source": source, "updated": file.Updated, "games": filterCatalog(file.Games, q)}
	case "appid":
		id, err := strconv.Atoi(q)
		if err != nil || id <= 0 {
			return map[string]any{"source": source, "games": []CatalogGame{}, "hint": "请输入数字 AppID，例如 570"}
		}
		game, err := lookupAppid(id)
		if err != nil {
			return map[string]any{"source": source, "games": []CatalogGame{{AppID: id}}, "hint": "名称解析失败：" + err.Error()}
		}
		return map[string]any{"source": source, "games": []CatalogGame{game}}
	default:
		file := loadCatalog()
		return map[string]any{"source": "builtin", "updated": file.Updated, "games": filterCatalog(file.Games, q)}
	}
}

func filterCatalog(games []CatalogGame, query string) []CatalogGame {
	if query == "" {
		return games
	}
	lower := strings.ToLower(query)
	if id, err := strconv.Atoi(query); err == nil {
		for _, game := range games {
			if game.AppID == id {
				return []CatalogGame{game}
			}
		}
		return []CatalogGame{{AppID: id}}
	}
	out := make([]CatalogGame, 0, 32)
	for _, game := range games {
		if strings.Contains(strings.ToLower(game.Name), lower) {
			out = append(out, game)
		}
	}
	return out
}

func describeFmt(err error) string { return fmt.Sprintf("%v", err) }
