package core

import (
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// MirrorRepos are the manifest mirrors used by the Python core, in preference order.
var MirrorRepos = []string{
	"qwe213312/k25FCdfEOoEJ42S6",
	"ooiiuur/ManifestHubSharing",
	"dc190/ManifestHub",
}

var mirrorTemplates = []string{
	"https://raw.githubusercontent.com/%s/main/%s",
	"https://cdn.jsdelivr.net/gh/%s@main/%s",
	"https://raw.githack.com/%s/main/%s",
}

type Mirror struct {
	Client *http.Client
	Repos  []string
}

func NewMirror() *Mirror {
	return &Mirror{Client: &http.Client{Timeout: 60 * time.Second}, Repos: MirrorRepos}
}

func (m *Mirror) url(repo, name string) string {
	return fmt.Sprintf(mirrorTemplates[0], repo, name)
}

func (m *Mirror) get(url string) ([]byte, int, error) {
	response, err := m.Client.Get(url)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, response.StatusCode, err
	}
	return body, response.StatusCode, nil
}

// headCache memoises depot+gid -> status for the process lifetime.
var headCache = struct {
	sync.Mutex
	m map[string]int
}{m: map[string]int{}}

// HeadStatus probes every repo and URL template until one answers 200.
func (m *Mirror) HeadStatus(depot int, gid string) int {
	key := fmt.Sprintf("%d_%s", depot, gid)
	headCache.Lock()
	if cached, ok := headCache.m[key]; ok {
		headCache.Unlock()
		return cached
	}
	headCache.Unlock()

	name := key + ".manifest"
	result := 404
	for _, repo := range m.Repos {
		for _, template := range mirrorTemplates {
			url := fmt.Sprintf(template, repo, name)
			request, err := http.NewRequest(http.MethodHead, url, nil)
			if err != nil {
				continue
			}
			response, err := m.Client.Do(request)
			if err != nil {
				continue
			}
			response.Body.Close()
			if response.StatusCode == 200 {
				result = 200
				headCache.Lock()
				headCache.m[key] = result
				headCache.Unlock()
				return result
			}
		}
	}
	headCache.Lock()
	headCache.m[key] = result
	headCache.Unlock()
	return result
}

// Fetch downloads a manifest, probing every candidate/repo/template combination in parallel
// so a dead host cannot stall the whole restore.
func (m *Mirror) Fetch(depot int, gid string, idx *Index) (*Manifest, string, string, error) {
	candidates := idx.Candidates(depot, gid)
	if len(candidates) == 0 {
		candidates = []string{gid}
	}
	type combo struct {
		url  string
		gid  string
	}
	var combos []combo
	for _, candidate := range candidates {
		name := fmt.Sprintf("%d_%s.manifest", depot, candidate)
		repos := idx.ReposFor(depot, candidate)
		ordered := append([]string{}, repos...)
		for _, repo := range m.Repos {
			if !contains(ordered, repo) {
				ordered = append(ordered, repo)
			}
		}
		for _, repo := range ordered {
			for _, template := range mirrorTemplates {
				combos = append(combos, combo{url: fmt.Sprintf(template, repo, name), gid: candidate})
			}
		}
	}

	type hit struct {
		body []byte
		url  string
		gid  string
	}
	results := make(chan hit, 1)
	probeClient := &http.Client{Timeout: 20 * time.Second}
	var wg sync.WaitGroup
	sem := make(chan struct{}, 12)
	done := make(chan struct{})
	var once sync.Once
	for _, c := range combos {
		wg.Add(1)
		go func(c combo) {
			defer wg.Done()
			select {
			case <-done:
				return
			default:
			}
			sem <- struct{}{}
			defer func() { <-sem }()
			response, err := probeClient.Get(c.url)
			if err != nil {
				return
			}
			defer response.Body.Close()
			if response.StatusCode != 200 {
				return
			}
			body, err := io.ReadAll(response.Body)
			if err != nil || len(body) == 0 {
				return
			}
			once.Do(func() {
				close(done)
				results <- hit{body: body, url: c.url, gid: c.gid}
			})
		}(c)
	}
	go func() { wg.Wait(); close(results) }()

	for h := range results {
		manifest, err := ParseManifest(h.body)
		if err != nil {
			continue
		}
		return manifest, h.url, h.gid, nil
	}
	return nil, "", "", fmt.Errorf("no mirror served depot %d gid %s (%d sources tried)", depot, gid, len(combos))
}


func (i *Index) ReposFor(depot int, gid string) []string {
	if i == nil {
		return nil
	}
	bucket, ok := i.Depots[depot]
	if !ok {
		return nil
	}
	return bucket[gid]
}

func contains(values []string, needle string) bool {
	for _, value := range values {
		if strings.EqualFold(value, needle) {
			return true
		}
	}
	return false
}