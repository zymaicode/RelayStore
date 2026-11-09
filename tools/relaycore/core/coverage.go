package core

import (
	"encoding/json"
	"fmt"
	"os"
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
	for _, info := range depots {
		row := DepotCoverage{DepotID: info.DepotID, GID: info.GID, Size: info.Size}
		_, row.HasKey = keys[info.DepotID]
		row.IndexGIDs = idx.GIDCount(info.DepotID)
		row.ManifestStatus = mirror.HeadStatus(info.DepotID, info.GID)
		ok := row.HasKey && (row.ManifestStatus == 200 || row.IndexGIDs > 0)
		if ok {
			report.DownloadableDepots++
			report.SizeBytes += info.Size
		} else {
			if !row.HasKey {
				report.Missing = append(report.Missing, fmt.Sprintf("%d:no-key", info.DepotID))
			} else {
				report.Missing = append(report.Missing, fmt.Sprintf("%d:no-manifest", info.DepotID))
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
