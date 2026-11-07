package core

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
)

// LoadKeys reads a {depot_id: hex_key} JSON map.
func LoadKeys(path string) (map[int]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var raw map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("keys json: %w", err)
	}
	out := make(map[int]string, len(raw))
	for key, value := range raw {
		id, err := strconv.Atoi(key)
		if err != nil || len(value) != 64 {
			continue
		}
		out[id] = value
	}
	return out, nil
}

// Index maps depot -> gid -> repos, supporting both v1 and v2 on-disk formats.
type Index struct {
	Depots map[int]map[string][]string
}

func LoadIndex(path string) (*Index, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(data, &probe); err != nil {
		return nil, err
	}
	idx := &Index{Depots: map[int]map[string][]string{}}
	if depotsRaw, ok := probe["depots"]; ok {
		var depots map[string]map[string][]string
		if err := json.Unmarshal(depotsRaw, &depots); err != nil {
			return nil, err
		}
		for depotKey, bucket := range depots {
			id, err := strconv.Atoi(depotKey)
			if err != nil {
				continue
			}
			idx.Depots[id] = bucket
		}
		return idx, nil
	}
	var v1 map[string][]string
	if err := json.Unmarshal(data, &v1); err != nil {
		return nil, err
	}
	for depotKey, gids := range v1 {
		id, err := strconv.Atoi(depotKey)
		if err != nil {
			continue
		}
		bucket := map[string][]string{}
		for _, gid := range gids {
			bucket[gid] = nil
		}
		idx.Depots[id] = bucket
	}
	return idx, nil
}

func (i *Index) GIDCount(depot int) int {
	if i == nil {
		return 0
	}
	return len(i.Depots[depot])
}

// Candidates lists known gids for a depot with the current gid first, newest next.
func (i *Index) Candidates(depot int, current string) []string {
	if i == nil {
		return []string{current}
	}
	bucket, ok := i.Depots[depot]
	if !ok {
		return []string{current}
	}
	var rest []string
	for gid := range bucket {
		if gid == current {
			continue
		}
		rest = append(rest, gid)
	}
	sort.Slice(rest, func(a, b int) bool {
		na, _ := strconv.ParseUint(rest[a], 10, 64)
		nb, _ := strconv.ParseUint(rest[b], 10, 64)
		return na > nb
	})
	return append([]string{current}, rest...)
}
