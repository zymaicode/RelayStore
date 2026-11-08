package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"relaycore/core"
)

// GameMeta is the store-facing identity of an app, cached on disk.
type GameMeta struct {
	Name  string `json:"name"`
	Image string `json:"image"`
	Type  string `json:"type"`
	TS    int64  `json:"ts"`
}

func metaCachePath() string {
	return filepath.Join(loadSettings().DataDir, "meta.json")
}

func loadMetaCache() map[string]GameMeta {
	out := map[string]GameMeta{}
	data, err := os.ReadFile(metaCachePath())
	if err != nil {
		return out
	}
	_ = json.Unmarshal(data, &out)
	return out
}

func saveMetaCache(cache map[string]GameMeta) {
	path := metaCachePath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return
	}
	if data, err := json.Marshal(cache); err == nil {
		_ = os.WriteFile(path, data, 0o644)
	}
}

// fetchFromSteamcmdNet: api.steamcmd.net mirrors appinfo and stays reachable in CN.
func fetchFromSteamcmdNet(appid int) (GameMeta, error) {
	body, err := httpGetOnce(fmt.Sprintf("https://api.steamcmd.net/v1/info/%d", appid))
	if err != nil {
		return GameMeta{}, err
	}
	var payload struct {
		Status string `json:"status"`
		Data   map[string]struct {
			Common struct {
				Name string `json:"name"`
				Type string `json:"type"`
			} `json:"common"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return GameMeta{}, err
	}
	entry, ok := payload.Data[strconv.Itoa(appid)]
	if !ok || entry.Common.Name == "" {
		return GameMeta{}, fmt.Errorf("appinfo 无数据")
	}
	return GameMeta{Name: entry.Common.Name, Type: entry.Common.Type, TS: time.Now().Unix()}, nil
}

// fetchFromStore: optional, also yields a header image when the store is reachable.
func fetchFromStore(appid int) (GameMeta, error) {
	body, err := httpGetOnce(fmt.Sprintf("https://store.steampowered.com/api/appdetails?appids=%d&l=schinese", appid))
	if err != nil {
		return GameMeta{}, err
	}
	var payload map[string]struct {
		Success bool `json:"success"`
		Data    struct {
			Name        string `json:"name"`
			HeaderImage string `json:"header_image"`
			Type        string `json:"type"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return GameMeta{}, err
	}
	entry, ok := payload[strconv.Itoa(appid)]
	if !ok || !entry.Success || entry.Data.Name == "" {
		return GameMeta{}, fmt.Errorf("appdetails 无数据")
	}
	return GameMeta{Name: entry.Data.Name, Image: entry.Data.HeaderImage, Type: entry.Data.Type, TS: time.Now().Unix()}, nil
}

func (a *App) fetchMeta(appid int) (GameMeta, bool) {
	if meta, err := fetchFromSteamcmdNet(appid); err == nil {
		return meta, true
	}
	if meta, err := fetchFromStore(appid); err == nil {
		return meta, true
	}
	if name, err := core.AppName(appid, a.appinfoDir()); err == nil && name != "" {
		return GameMeta{Name: name, TS: time.Now().Unix()}, true
	}
	return GameMeta{}, false
}

// GameMetas returns cached (or freshly fetched) identity data for the given appids.
func (a *App) GameMetas(appids []int) map[int]GameMeta {
	cache := loadMetaCache()
	out := map[int]GameMeta{}
	var mu sync.Mutex
	var wg sync.WaitGroup
	changed := false
	for _, id := range appids {
		key := strconv.Itoa(id)
		if entry, ok := cache[key]; ok && entry.Name != "" {
			out[id] = entry
			continue
		}
		wg.Add(1)
		go func(id int, key string) {
			defer wg.Done()
			meta, ok := a.fetchMeta(id)
			if !ok {
				return
			}
			mu.Lock()
			cache[key] = meta
			out[id] = meta
			changed = true
			mu.Unlock()
		}(id, key)
	}
	wg.Wait()
	if changed {
		saveMetaCache(cache)
	}
	return out
}
