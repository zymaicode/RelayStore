package main

import (
	"crypto/sha256"
	"encoding/hex"
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

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

const latestReleaseAPI = "https://api.github.com/repos/zymaicode/RelayStore/releases/latest"

// raw metadata endpoint: fast and reachable even when release downloads are throttled.
const latestRawURL = "https://raw.githubusercontent.com/zymaicode/RelayStore/main/updates/latest.json"

type updateAsset struct {
	Name   string `json:"name"`
	SHA256 string `json:"sha256"`
}

type updateMeta struct {
	Version   string      `json:"version"`
	Portable  updateAsset `json:"portable"`
	Installer updateAsset `json:"installer"`
	Source    string      `json:"source"`
}

type releaseAsset struct {
	Name string `json:"name"`
	URL  string `json:"browser_download_url"`
}

type releaseInfo struct {
	Tag    string         `json:"tag_name"`
	HTML   string         `json:"html_url"`
	Assets []releaseAsset `json:"assets"`
}

type UpdateStatus struct {
	Current       string `json:"current"`
	Latest        string `json:"latest"`
	HasUpdate     bool   `json:"hasUpdate"`
	Portable      bool   `json:"portable"`
	InstallerURL  string `json:"installerUrl"`
	InstallerName string `json:"installerName"`
	InstallerSHA  string `json:"installerSha256"`
	PortableURL   string `json:"portableUrl"`
	ReleaseURL    string `json:"releaseUrl"`
	Error         string `json:"error,omitempty"`
}

func httpGet(url string) ([]byte, error) {
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		body, err := httpGetOnce(url)
		if err == nil {
			return body, nil
		}
		lastErr = err
		time.Sleep(time.Duration(attempt+1) * 2 * time.Second)
	}
	return nil, lastErr
}

func httpGetOnce(url string) ([]byte, error) {
	client := &http.Client{Timeout: 180 * time.Second}
	request, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", "relaystore-updater")
	request.Header.Set("Accept", "application/vnd.github+json")
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("HTTP %d", response.StatusCode)
	}
	return body, nil
}

// metadataURL honours RELAYSTORE_UPDATE_URL so tests and mirrors can override it.
func metadataURL() string {
	if custom := os.Getenv("RELAYSTORE_UPDATE_URL"); custom != "" {
		return custom
	}
	return latestRawURL
}

// fetchUpdateMeta reads the release, then the latest.json asset inside it.
func fetchUpdateMeta() (updateMeta, releaseInfo, error) {
	var meta updateMeta
	// try the raw endpoint first (fast, no redirect to a throttled object host)
	if raw, err := httpGet(metadataURL()); err == nil {
		if err := json.Unmarshal(raw, &meta); err == nil && meta.Version != "" {
			release := releaseInfo{Tag: meta.Version, HTML: "https://github.com/zymaicode/RelayStore/releases/tag/" + meta.Version}
			release.Assets = append(release.Assets,
				releaseAsset{Name: meta.Portable.Name, URL: "https://github.com/zymaicode/RelayStore/releases/download/" + meta.Version + "/" + meta.Portable.Name},
				releaseAsset{Name: meta.Installer.Name, URL: "https://github.com/zymaicode/RelayStore/releases/download/" + meta.Version + "/" + meta.Installer.Name},
			)
			return meta, release, nil
		}
	}
	body, err := httpGet(latestReleaseAPI)
	if err != nil {
		return meta, releaseInfo{}, err
	}
	var release releaseInfo
	if err := json.Unmarshal(body, &release); err != nil {
		return meta, release, err
	}
	for _, asset := range release.Assets {
		if asset.Name != "latest.json" {
			continue
		}
		raw, err := httpGet(asset.URL)
		if err != nil {
			return meta, release, err
		}
		if err := json.Unmarshal(raw, &meta); err != nil {
			return meta, release, err
		}
		return meta, release, nil
	}
	return meta, release, fmt.Errorf("release 里没有 latest.json")
}

func normalizeVersion(v string) string {
	return strings.TrimPrefix(strings.TrimSpace(v), "v")
}

// isNewer compares dotted versions numerically, ignoring pre-release suffixes.
func isNewer(current, latest string) bool {
	cur := strings.Split(normalizeVersion(current), ".")
	lat := strings.Split(normalizeVersion(latest), ".")
	for i := 0; i < len(lat) && i < len(cur); i++ {
		a, errA := strconv.Atoi(strings.TrimFunc(cur[i], func(r rune) bool { return r < '0' || r > '9' }))
		b, errB := strconv.Atoi(strings.TrimFunc(lat[i], func(r rune) bool { return r < '0' || r > '9' }))
		if errA != nil || errB != nil {
			return latest != current
		}
		if b != a {
			return b > a
		}
	}
	return len(lat) > len(cur)
}

// CheckUpdate asks GitHub for the newest release and compares versions.
func (a *App) CheckUpdate() UpdateStatus {
	status := UpdateStatus{Current: a.version, Portable: isPortable()}
	meta, release, err := fetchUpdateMeta()
	if err != nil {
		status.Error = err.Error()
		return status
	}
	status.Latest = meta.Version
	status.ReleaseURL = release.HTML
	status.InstallerName = meta.Installer.Name
	status.InstallerSHA = meta.Installer.SHA256
	status.HasUpdate = isNewer(a.version, meta.Version)
	for _, asset := range release.Assets {
		if asset.Name == meta.Installer.Name {
			status.InstallerURL = asset.URL
		}
		if asset.Name == meta.Portable.Name {
			status.PortableURL = asset.URL
		}
	}
	return status
}

// OpenReleasePage opens the release page in the default browser (portable flow).
func (a *App) OpenReleasePage(url string) {
	if url == "" {
		url = "https://github.com/zymaicode/RelayStore/releases/latest"
	}
	runtime.BrowserOpenURL(a.ctx, url)
}

func sha256File(path string) (string, error) {
	handle, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer handle.Close()
	hasher := sha256.New()
	if _, err := io.Copy(hasher, handle); err != nil {
		return "", err
	}
	return hex.EncodeToString(hasher.Sum(nil)), nil
}

// DownloadInstaller fetches the installer, verifies its sha256 and returns the path.
func (a *App) DownloadInstaller(url, name, wantSHA string) (string, error) {
	if url == "" {
		return "", fmt.Errorf("安装包地址为空")
	}
	dir := filepath.Join(a.settings.DataDir, "updates")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	target := filepath.Join(dir, name)
	runtime.EventsEmit(a.ctx, "update:progress", map[string]any{"stage": "download", "percent": 5.0})

	client := &http.Client{Timeout: 600 * time.Second}
	request, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	request.Header.Set("User-Agent", "relaystore-updater")
	response, err := client.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return "", fmt.Errorf("下载失败：HTTP %d", response.StatusCode)
	}
	out, err := os.Create(target)
	if err != nil {
		return "", err
	}
	total := response.ContentLength
	written := int64(0)
	buf := make([]byte, 1<<20)
	for {
		n, readErr := response.Body.Read(buf)
		if n > 0 {
			if _, err := out.Write(buf[:n]); err != nil {
				out.Close()
				return "", err
			}
			written += int64(n)
			if total > 0 {
				percent := 5 + 85*float64(written)/float64(total)
				runtime.EventsEmit(a.ctx, "update:progress", map[string]any{"stage": "download", "percent": percent, "bytes": written, "total": total})
			}
		}
		if readErr != nil {
			break
		}
	}
	out.Close()

	runtime.EventsEmit(a.ctx, "update:progress", map[string]any{"stage": "verify", "percent": 92.0})
	got, err := sha256File(target)
	if err != nil {
		return "", err
	}
	if wantSHA != "" && !strings.EqualFold(got, wantSHA) {
		_ = os.Remove(target)
		return "", fmt.Errorf("校验失败：期望 %s…，实际 %s…", wantSHA[:12], got[:12])
	}
	runtime.EventsEmit(a.ctx, "update:progress", map[string]any{"stage": "verified", "percent": 100.0, "path": target})
	return target, nil
}

// RunInstaller launches the verified installer silently and exits the app.
func (a *App) RunInstaller(path string) error {
	if _, err := os.Stat(path); err != nil {
		return err
	}
	cmd := exec.Command(path, "/S")
	if err := cmd.Start(); err != nil {
		return err
	}
	runtime.EventsEmit(a.ctx, "update:done", map[string]any{"path": path})
	go func() {
		time.Sleep(2 * time.Second)
		runtime.Quit(a.ctx)
	}()
	return nil
}
