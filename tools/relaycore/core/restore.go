package core

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const defaultHost = "https://steampipe.akamaized.net"

var cdnHosts = []string{
	"https://steampipe.akamaized.net",
	"https://st.dl.eccdnx.com",
	"https://cdn.steamcontent.com",
}

const steamUserAgent = "Valve/Steam HTTP Client 1.0"

type Restorer struct {
	Depot   int
	Key     []byte
	OutDir  string
	Workers int
	Host    string
}

type RestoreStats struct {
	FilesOK     int
	FilesFailed int
	Bytes       uint64
	Chunks      int
	Errors      []string
}

func (r *Restorer) chunkURL(sha string) string {
	return fmt.Sprintf("%s/depot/%d/chunk/%s", r.Host, r.Depot, sha)
}

func (r *Restorer) fetchChunk(client *http.Client, sha string, cacheDir string) (string, error) {
	plainPath := filepath.Join(cacheDir, sha)
	if info, err := os.Stat(plainPath); err == nil && info.Size() > 0 {
		return plainPath, nil
	}
	hosts := []string{r.Host}
	for _, candidate := range cdnHosts {
		if candidate != r.Host {
			hosts = append(hosts, candidate)
		}
	}
	var cipherText []byte
	var lastErr error
	for _, host := range hosts {
		for attempt := 0; attempt < 3; attempt++ {
			request, err := http.NewRequest(http.MethodGet, fmt.Sprintf("%s/depot/%d/chunk/%s", host, r.Depot, sha), nil)
			if err != nil {
				lastErr = err
				break
			}
			request.Header.Set("User-Agent", steamUserAgent)
			response, err := client.Do(request)
			if err != nil {
				lastErr = err
				time.Sleep(300 * time.Millisecond)
				continue
			}
			body, readErr := io.ReadAll(response.Body)
			response.Body.Close()
			if response.StatusCode != 200 || readErr != nil {
				lastErr = fmt.Errorf("%s: HTTP %d", host, response.StatusCode)
				time.Sleep(300 * time.Millisecond)
				continue
			}
			cipherText = body
			break
		}
		if cipherText != nil {
			break
		}
	}
	if cipherText == nil {
		if lastErr == nil {
			lastErr = fmt.Errorf("no host served chunk %s", sha)
		}
		return "", lastErr
	}
	plain, err := DecryptChunk(cipherText, r.Key)
	if err != nil {
		return "", err
	}
	decoded, err := DecodeAuto(plain)
	if err != nil {
		return "", err
	}
	sum := sha1.Sum(decoded)
	if hex.EncodeToString(sum[:]) != strings.ToLower(sha) {
		return "", fmt.Errorf("chunk %s: sha1 mismatch", sha)
	}
	if err := os.WriteFile(plainPath, decoded, 0o644); err != nil {
		return "", err
	}
	return plainPath, nil
}

// decodeAuto picks the right decompressor from the payload magic.
func DecodeAuto(plain []byte) ([]byte, error) {
	_, out, err := Decompress(plain)
	return out, err
}

type digestHolder struct {
	value string
}

func hashFile(path string) (string, error) {
	handle, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer handle.Close()
	hasher := sha1.New()
	if _, err := io.Copy(hasher, handle); err != nil {
		return "", err
	}
	return hex.EncodeToString(hasher.Sum(nil)), nil
}

func safeJoin(root, name string) (string, error) {
	clean := filepath.Clean(strings.ReplaceAll(name, "\\", "/"))
	clean = strings.TrimPrefix(clean, "/")
	if strings.Contains(clean, "..") {
		return "", fmt.Errorf("unsafe path: %s", name)
	}
	return filepath.Join(root, filepath.FromSlash(clean)), nil
}

func (r *Restorer) Run(manifest *Manifest, fileLimit int) (*RestoreStats, error) {
	stats := &RestoreStats{}
	cacheDir := filepath.Join(r.OutDir, ".chunks")
	if err := os.MkdirAll(cacheDir, 0o755); err != nil {
		return nil, err
	}

	// zero-chunk entries are directory / link markers: create them, never write files
	var files []FileEntry
	for _, entry := range manifest.Files {
		if len(entry.Chunks) == 0 {
			if target, err := safeJoin(r.OutDir, entry.Names[0]); err == nil {
				_ = os.MkdirAll(target, 0o755)
			}
			continue
		}
		files = append(files, entry)
	}
	if fileLimit > 0 && len(files) > fileLimit {
		files = files[:fileLimit]
	}

	needed := map[string]Chunk{}
	for _, file := range files {
		for _, chunk := range file.Chunks {
			needed[chunk.SHA] = chunk
		}
	}
	stats.Chunks = len(needed)

	tasks := make(chan string)
	var wg sync.WaitGroup
	var failed int32
	client := &http.Client{Timeout: 120 * time.Second}
	var mu sync.Mutex
	for i := 0; i < r.Workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for sha := range tasks {
				if _, err := r.fetchChunk(client, sha, cacheDir); err != nil {
					atomic.AddInt32(&failed, 1)
					mu.Lock()
					stats.Errors = append(stats.Errors, err.Error())
					mu.Unlock()
				}
			}
		}()
	}
	for sha := range needed {
		tasks <- sha
	}
	close(tasks)
	wg.Wait()
	if failed > 0 {
		return stats, fmt.Errorf("%d chunk(s) failed", failed)
	}

	for _, file := range files {
		if len(file.Chunks) == 0 {
			stats.FilesFailed++
			continue
		}
		target, err := safeJoin(r.OutDir, file.Names[0])
		if err != nil {
			stats.FilesFailed++
			stats.Errors = append(stats.Errors, err.Error())
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			stats.FilesFailed++
			continue
		}
		handle, err := os.Create(target)
		if err != nil {
			stats.FilesFailed++
			stats.Errors = append(stats.Errors, err.Error())
			continue
		}
		ok := true
		for _, chunk := range file.Chunks {
			plainPath := filepath.Join(cacheDir, chunk.SHA)
			data, err := os.ReadFile(plainPath)
			if err != nil {
				ok = false
				stats.Errors = append(stats.Errors, err.Error())
				break
			}
			if uint32(len(data)) != chunk.CbOriginal {
				ok = false
				stats.Errors = append(stats.Errors, fmt.Sprintf("chunk %s size %d != %d", chunk.SHA, len(data), chunk.CbOriginal))
				break
			}
			// chunks are placed at their offset: manifests may leave holes that must stay zero-filled
			if _, err := handle.WriteAt(data, int64(chunk.Offset)); err != nil {
				ok = false
				stats.Errors = append(stats.Errors, err.Error())
				break
			}
		}
		if ok {
			if err := handle.Truncate(int64(file.Size)); err != nil {
				ok = false
				stats.Errors = append(stats.Errors, err.Error())
			}
		}
		handle.Close()
		if !ok {
			stats.FilesFailed++
			os.Remove(target)
			continue
		}
		hashed, hashErr := hashFile(target)
		if hashErr != nil {
			stats.FilesFailed++
			stats.Errors = append(stats.Errors, hashErr.Error())
			os.Remove(target)
			continue
		}
		hasher := &digestHolder{value: hashed}
		if !ok {
			stats.FilesFailed++
			os.Remove(target)
			continue
		}
		if hasher.value != strings.ToLower(file.ShaContent) {
			stats.FilesFailed++
			stats.Errors = append(stats.Errors, "file sha1 mismatch: "+file.Names[0])
			os.Remove(target)
			continue
		}
		stats.FilesOK++
		stats.Bytes += file.Size
	}
	return stats, nil
}
