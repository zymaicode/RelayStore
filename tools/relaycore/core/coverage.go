package core

import (
	"encoding/json"
	"fmt"
	"os"
	"sync"
)

type DepotCoverage struct {
	DepotID        int    `json:"depot_id"`
	GID            string `json:"gid"`
	HasKey         bool   `json:"has_key"`
	ManifestStatus int    `json:"manifest_status"`
	IndexGIDs      int    `json:"index_gids"`
	Size           int64  `json:"size"`
}

type CoverageReport struct {
	AppID              int             `json:"appid"`
	Downloadable       bool            `json:"downloadable"`
	DepotsTotal        int             `json:"depots_total"`
	DownloadableDepots int             `json:"downloadable_depots"`
	SizeBytes          int64           `json:"size_bytes"`
	Missing            []string        `json:"missing"`
	Depots             []DepotCoverage `json:"depots"`
}

// CheckCoverage mirrors the Python coverage rule: key + (mirror 200 or index fallback).
func CheckCoverage(appid int, keys map[int]string, idx *Index, cacheDir string, mirror *Mirror) (*CoverageReport, error) {
	depots, err := PublicDepots(appid, cacheDir)
	if err != nil {
		return nil, err
	}
	depots = WindowsDepots(depots)
	if mirror == nil {
		mirror = NewMirror()
	}
	report := &CoverageReport{AppID: appid}
	rows := make([]DepotCoverage, len(depots))
	var wg sync.WaitGroup
	sem := make(chan struct{}, 6)
	for i, info := range depots {
		wg.Add(1)
		go func(i int, info DepotInfo) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			row := DepotCoverage{DepotID: info.DepotID, GID: info.GID, Size: info.Size}
			_, row.HasKey = keys[info.DepotID]
			row.IndexGIDs = idx.GIDCount(info.DepotID)
			row.ManifestStatus = mirror.HeadStatus(info.DepotID, info.GID)
			if row.ManifestStatus != 200 && len(idx.Candidates(info.DepotID, info.GID)) > 0 {
				// the index only tells us a gid exists; verify something is actually served
				for _, candidate := range idx.Candidates(info.DepotID, info.GID) {
					if mirror.HeadStatus(info.DepotID, candidate) == 200 {
						row.ManifestStatus = 200
						break
					}
				}
			}
			rows[i] = row
		}(i, info)
	}
	wg.Wait()
	for _, row := range rows {
		ok := row.HasKey && row.ManifestStatus == 200
		if ok {
			report.DownloadableDepots++
			report.SizeBytes += row.Size
		} else {
			if !row.HasKey {
				report.Missing = append(report.Missing, fmt.Sprintf("%d:no-key", row.DepotID))
			} else {
				report.Missing = append(report.Missing, fmt.Sprintf("%d:no-manifest", row.DepotID))
			}
		}
		report.Depots = append(report.Depots, row)
	}
	report.DepotsTotal = len(report.Depots)
	report.Downloadable = report.DepotsTotal > 0 && report.DownloadableDepots == report.DepotsTotal
	return report, nil
}

func WriteJSON(path string, payload any) error {
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}