package main

import (
	_ "embed"
	"encoding/json"
	"path/filepath"
	"strconv"
	"strings"
)

//go:embed catalogdata.json
var catalogJSON []byte

type CatalogGame struct {
	AppID int    `json:"appid"`
	Name  string `json:"name"`
}

type catalogFile struct {
	Updated string        `json:"updated"`
	Games   []CatalogGame `json:"games"`
}

func loadCatalog() catalogFile {
	var file catalogFile
	_ = json.Unmarshal(catalogJSON, &file)
	// de-duplicate by appid, preserving order
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
	return file
}

// StoreSource describes one game source shown under the store entry.
type StoreSource struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Available bool   `json:"available"`
	Note      string `json:"note"`
}

// StoreSources lists the sources; only the built-in one works offline today.
func (a *App) StoreSources() []StoreSource {
	file := loadCatalog()
	return []StoreSource{
		{ID: "builtin", Name: "云驿榜单", Available: true, Note: "内置 " + strconv.Itoa(len(file.Games)) + " 条热门"},
		{ID: "steam", Name: "Steam 商店", Available: false, Note: "当前网络不可达，待接入"},
		{ID: "steamspy", Name: "SteamSpy 热度", Available: false, Note: "接口超时，待接入"},
	}
}

// StoreCatalog returns the built-in popularity list.
func (a *App) StoreCatalog() map[string]any {
	file := loadCatalog()
	return map[string]any{"updated": file.Updated, "games": file.Games}
}

// StoreSearch filters the catalog by name or appid; digits are treated as an appid.
func (a *App) StoreSearch(query string) []CatalogGame {
	q := strings.TrimSpace(strings.ToLower(query))
	file := loadCatalog()
	if q == "" {
		return file.Games
	}
	if id, err := strconv.Atoi(q); err == nil {
		for _, game := range file.Games {
			if game.AppID == id {
				return []CatalogGame{game}
			}
		}
		return []CatalogGame{{AppID: id, Name: ""}}
	}
	out := make([]CatalogGame, 0, 32)
	for _, game := range file.Games {
		if strings.Contains(strings.ToLower(game.Name), q) {
			out = append(out, game)
		}
	}
	return out
}

// SafeFolderName turns a game name into a folder name usable on Windows.
func SafeFolderName(name string) string {
	replacer := strings.NewReplacer("\\", "_", "/", "_", ":", "_", "*", "_", "?", "_",
		"\"", "_", "<", "_", ">", "_", "|", "_")
	cleaned := strings.TrimSpace(replacer.Replace(name))
	cleaned = strings.TrimRight(cleaned, ". ")
	if cleaned == "" || len(cleaned) > 80 {
		if len(cleaned) > 80 {
			return cleaned[:80]
		}
		return ""
	}
	return cleaned
}

// InstallPathFor builds <gameDir>\<game name> (falls back to the appid).
func (a *App) InstallPathFor(appid int) string {
	name := ""
	if meta, ok := loadMetaCache()[strconv.Itoa(appid)]; ok {
		name = meta.Name
	}
	if name == "" {
		// also accept a bundled catalog name
		for _, game := range loadCatalog().Games {
			if game.AppID == appid {
				name = game.Name
				break
			}
		}
	}
	folder := SafeFolderName(name)
	if folder == "" {
		folder = strconv.Itoa(appid)
	}
	return filepath.Join(a.settings.GameDir, folder)
}
