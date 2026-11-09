package main

import (
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"relaycore/core"
)

func cmdDecode(args []string) {
	fs := flag.NewFlagSet("decode", flag.ExitOnError)
	in := fs.String("in", "", "encrypted chunk file")
	keyHex := fs.String("key", "", "depot key (64 hex)")
	wantSHA1 := fs.String("sha1", "", "expected sha1 of plaintext")
	iter := fs.Int("iter", 1, "iterations")
	out := fs.String("out", "", "write decoded output here")
	aesOnly := fs.Bool("aes-only", false, "skip decompression")
	fs.Parse(args)
	if *in == "" || *keyHex == "" {
		fmt.Println("usage: steamcore decode -in chunk.bin -key <64hex> [-sha1 ...] [-iter N]")
		os.Exit(2)
	}
	cipherText, err := os.ReadFile(*in)
	check(err)
	key, err := core.HexKey(*keyHex)
	check(err)

	start := time.Now()
	var decoded []byte
	for i := 0; i < *iter; i++ {
		plain, err := core.DecryptChunk(cipherText, key)
		check(err)
		if *aesOnly {
			decoded = plain
		} else {
			decoded, err = core.DecodeAuto(plain)
			check(err)
		}
	}
	elapsed := time.Since(start)
	sum := sha1.Sum(decoded)
	got := hex.EncodeToString(sum[:])
	match := *wantSHA1 == "" || got == *wantSHA1
	fmt.Printf("chunk=%d plain=%d iter=%d perOp=%.2fms throughput=%.1f MB/s sha1=%s match=%v\n",
		len(cipherText), len(decoded), *iter,
		float64(elapsed.Microseconds())/1000.0/float64(*iter),
		float64(len(decoded)*(*iter))/1048576.0/elapsed.Seconds(), got, match)
	if *out != "" {
		check(os.WriteFile(*out, decoded, 0o644))
	}
	if !match {
		os.Exit(3)
	}
}

func cmdManifest(args []string) {
	fs := flag.NewFlagSet("manifest", flag.ExitOnError)
	in := fs.String("in", "", "manifest file")
	asJSON := fs.Bool("json", false, "print JSON")
	fs.Parse(args)
	m, err := core.LoadManifest(*in)
	check(err)
	if *asJSON {
		payload := map[string]any{"files": len(m.Files), "bytes": m.TotalBytes(), "chunks": m.UniqueChunks()}
		encoded, _ := json.MarshalIndent(payload, "", "  ")
		fmt.Println(string(encoded))
		return
	}
	fmt.Printf("files=%d bytes=%d\n", len(m.Files), m.TotalBytes())
	for _, f := range m.Files {
		fmt.Printf("  %-70s %10d %s chunks=%d\n", first(f.Names), f.Size, short(f.ShaContent), len(f.Chunks))
	}
}

func cmdRestore(args []string) {
	fs := flag.NewFlagSet("restore", flag.ExitOnError)
	manifestPath := fs.String("manifest", "", "manifest file")
	depot := fs.Int("depot", 0, "depot id")
	keyHex := fs.String("key", "", "depot key (64 hex)")
	outDir := fs.String("out", "", "output directory")
	workers := fs.Int("workers", 8, "chunk workers")
	filesLimit := fs.Int("files", 0, "only restore the first N files (0 = all)")
	host := fs.String("host", "https://steampipe.akamaized.net", "CDN host")
	fs.Parse(args)
	if *manifestPath == "" || *depot == 0 || *outDir == "" {
		fmt.Println("usage: steamcore restore -manifest m.bin -depot 1276160 -key <64hex> -out DIR [-workers 8] [-files 1]")
		os.Exit(2)
	}
	key, err := core.HexKey(*keyHex)
	check(err)
	m, err := core.LoadManifest(*manifestPath)
	check(err)
	r := &core.Restorer{Depot: *depot, Key: key, OutDir: *outDir, Workers: *workers, Host: *host}
	start := time.Now()
	stats, err := r.Run(m, *filesLimit)
	elapsed := time.Since(start)
	fmt.Printf("files_ok=%d files_failed=%d bytes=%d chunks=%d elapsed=%.1fs\n",
		stats.FilesOK, stats.FilesFailed, stats.Bytes, stats.Chunks, elapsed.Seconds())
	for _, e := range stats.Errors {
		fmt.Println("  error:", e)
	}
	if err != nil {
		os.Exit(1)
	}
}

func cmdCoverage(args []string) {
	fs := flag.NewFlagSet("coverage", flag.ExitOnError)
	appid := fs.Int("appid", 0, "app id")
	keysPath := fs.String("keys", "src/data/keys/merged.json", "depot key corpus")
	indexPath := fs.String("index", "tests/reports/mirror-index.json", "manifest index")
	cacheDir := fs.String("cache", "src/data/appinfo", "appinfo cache dir")
	out := fs.String("out", "", "write JSON report here")
	fs.Parse(args)
	if *appid == 0 {
		fmt.Println("usage: steamcore coverage -appid 480 [-keys ...] [-index ...] [-out report.json]")
		os.Exit(2)
	}
	keys, err := core.LoadKeys(*keysPath)
	if err != nil {
		fmt.Println("keys:", err)
		os.Exit(1)
	}
	idx, _ := core.LoadIndex(*indexPath)
	report, err := core.CheckCoverage(*appid, keys, idx, *cacheDir, nil)
	check(err)
	encoded, _ := json.MarshalIndent(report, "", "  ")
	fmt.Println(string(encoded))
	if *out != "" {
		check(core.WriteJSON(*out, report))
	}
	if !report.Downloadable {
		os.Exit(3)
	}
}

func cmdRestoreApp(args []string) {
	fs := flag.NewFlagSet("restore-app", flag.ExitOnError)
	appid := fs.Int("appid", 0, "app id")
	outDir := fs.String("out", "", "output root")
	keysPath := fs.String("keys", "src/data/keys/merged.json", "depot key corpus")
	indexPath := fs.String("index", "tests/reports/mirror-index.json", "manifest index")
	cacheDir := fs.String("cache", "src/data/appinfo", "appinfo cache dir")
	workers := fs.Int("workers", 8, "chunk workers per depot")
	depotWorkers := fs.Int("depot-workers", 1, "depots in parallel")
	statePath := fs.String("state", "", "resume state file")
	preferArch := fs.String("arch", "", "keep only depots for this arch (x32/x64)")
	fs.Parse(args)
	if *appid == 0 || *outDir == "" {
		fmt.Println("usage: steamcore restore-app -appid 480 -out DIR [-state s.json] [-depot-workers 2]")
		os.Exit(2)
	}
	keys, err := core.LoadKeys(*keysPath)
	check(err)
	idx, _ := core.LoadIndex(*indexPath)
	started := time.Now()
	result, err := core.RestoreApp(*appid, *outDir, keys, idx, *cacheDir, *workers, *depotWorkers, *statePath, *preferArch, func(row core.DepotResult) {
		fmt.Printf("[depot %d] %s files=%d bytes=%d %.1fs %s\n", row.DepotID, row.Status, row.FilesOK, row.Bytes, row.Seconds, row.Error)
	})
	check(err)
	fmt.Printf("appid=%d ok=%v depots=%d files=%d bytes=%d elapsed=%.1fs\n",
		result.AppID, result.OK, len(result.Depots), result.FilesOK, result.Bytes, time.Since(started).Seconds())
	if !result.OK {
		os.Exit(1)
	}
}

func first(names []string) string {
	if len(names) == 0 {
		return ""
	}
	return names[0]
}

func short(s string) string {
	if len(s) <= 12 {
		return s
	}
	return s[:12]
}

func check(err error) {
	if err != nil {
		fmt.Println("error:", err)
		os.Exit(1)
	}
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: steamcore <decode|manifest|restore|coverage|restore-app> [flags]")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "decode":
		cmdDecode(os.Args[2:])
	case "manifest":
		cmdManifest(os.Args[2:])
	case "restore":
		cmdRestore(os.Args[2:])
	case "coverage":
		cmdCoverage(os.Args[2:])
	case "restore-app":
		cmdRestoreApp(os.Args[2:])
	default:
		fmt.Println("unknown command:", os.Args[1])
		os.Exit(2)
	}
}
