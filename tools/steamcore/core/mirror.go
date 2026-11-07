package core

import (
	"fmt"
	"io"
	"net/http"
	"strings"
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

// HeadStatus reports the first template status for a repo (used by coverage).
func (m *Mirror) HeadStatus(depot int, gid string) int {
	name := fmt.Sprintf("%d_%s.manifest", depot, gid)
	for _, repo := range m.Repos {
		request, err := http.NewRequest(http.MethodHead, m.url(repo, name), nil)
		if err != nil {
			continue
		}
		response, err := m.Client.Do(request)
		if err != nil {
			continue
		}
		response.Body.Close()
		if response.StatusCode == 200 {
			return 200
		}
		if response.StatusCode != 404 {
			return response.StatusCode
		}
	}
	return 404
}

// Fetch downloads a manifest, trying index-known repos first and then the gid fallbacks.
func (m *Mirror) Fetch(depot int, gid string, idx *Index) (*Manifest, string, string, error) {
	candidates := idx.Candidates(depot, gid)
	var lastErr error
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
				url := fmt.Sprintf(template, repo, name)
				body, status, err := m.get(url)
				if err != nil || status != 200 || len(body) == 0 {
					lastErr = fmt.Errorf("%s -> %v/%d", url, err, status)
					continue
				}
				manifest, err := ParseManifest(body)
				if err != nil {
					lastErr = err
					continue
				}
				return manifest, url, candidate, nil
			}
		}
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no mirror served depot %d gid %s", depot, gid)
	}
	return nil, "", "", lastErr
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
