# steamcore (Go client prototype)

Self-contained Go implementation of the Steam download pipeline: appinfo → manifest → chunk →
decrypt → assemble → verify. Built to test whether a single ~15 MB binary can replace the
Python core + sidecar pair.

## Build
```powershell
$env:GOROOT="D:\Go"; $env:GOPATH="D:\GoPath"; $env:GOCACHE="D:\GoCache"; $env:Path="D:\Go\bin;"+$env:Path
cd tools\steamcore
go build -o steamcore.exe .
```

Binary size: **10.4 MB** static, no runtime dependency.

## Commands

```powershell
steamcore decode   -in chunk.bin -key <64hex> [-sha1 <40hex>] [-iter N]
steamcore manifest -in m.bin -json
steamcore restore  -manifest m.bin -depot 1276160 -key <64hex> -out DIR [-workers 8] [-files N]
steamcore coverage -appid 480 [-keys ...] [-index ...] [-cache ...] [-out report.json]
steamcore restore-app -appid 480 -out DIR [-state s.json] [-depot-workers 2] [-workers 8]
```

## Modules

| File | Responsibility |
|---|---|
| `manifest.go` | sectioned container + hand-written protobuf (wire 0/1/2/5) |
| `chunk.go` | AES-256-CBC (ECB-derived IV), VZip/VZstd/zip, depot key parsing |
| `vdf.go` | Valve KeyValues text parser |
| `appinfo.go` | steamcmd output → depot list, with JSON cache |
| `keys_index.go` | key corpus loader, manifest index (v1/v2) |
| `mirror.go` | manifest mirrors (raw/jsDelivr/githack) + index-based gid fallback |
| `coverage.go` | downloadable? key + mirror 200 or index fallback |
| `restore.go` | concurrent chunk fetch (CDN host fallback + retries), per-chunk/per-file sha1 |
| `apprestore.go` | per-app orchestration, parallel depots, resume state |

## Verified (2026-11-06)

| Check | Result |
|---|---|
| chunk decode | sha1 matches Python (`391d06c9...`) |
| manifest parse | 21 files / 405 chunks / 412,115,023 B — identical to Python |
| restore one file | 3,455,847 B, sha256 identical to the Python restore |
| coverage 480 | `downloadable=true`, depot 481, key ok, manifest 200 |
| restore-app 480 | `ok=true`, 8 files, 1,906,055 B, 3.9 s — **all 8 files byte-identical to Python** |
| decode speed | 0.62 ms/chunk (1,613 MB/s) vs Python 38.98 ms (25.7 MB/s) |

## Known gaps

- appinfo still shells out to `steamcmd` (same as the Python core); no CM protocol client
- no hubcap fallback (manifest mirrors + index only)
- no GUI yet (Wails would be the natural choice)
