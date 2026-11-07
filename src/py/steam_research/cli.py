"""Command line interface (M1-T07): query / import-acf / doctor / report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .catalog import Catalog
from .parsers import AcfParseError, parse_acf_file
from .reports.coverage import collect, render_markdown
from .secrets import DEFAULT_ENV_FILE, resolve_secret
from .sources import HubcapClient, HubcapError, hubcap_stats, is_valid_key

DEFAULT_DB = Path("src/data/catalog.db")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_query(args: argparse.Namespace) -> int:
    catalog = Catalog(args.db)
    try:
        record = catalog.query(args.appid)
        if record is None:
            _emit({"appid": args.appid, "found": False, "offline": True})
            return 3
        _emit(
            {
                "found": True,
                "offline": True,
                "appid": record.appid,
                "name": record.name,
                "depots": list(record.depots),
                "manifests": [ref.as_dict() for ref in record.manifests],
                "history": len(catalog.history(record.appid)),
            }
        )
        return 0
    finally:
        catalog.close()


def cmd_import_acf(args: argparse.Namespace) -> int:
    catalog = Catalog(args.db)
    imported = []
    try:
        for raw_path in args.paths:
            state = parse_acf_file(raw_path)
            catalog.upsert(state.to_app_record())
            imported.append(
                {
                    "file": Path(raw_path).name,
                    "appid": state.appid,
                    "depots": len(state.depots),
                }
            )
        _emit({"imported": imported, "stats": catalog.stats()})
        return 0
    finally:
        catalog.close()


def cmd_doctor(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    catalog = Catalog(db_path)
    try:
        stats = catalog.stats()
        sources = catalog.sources()
    finally:
        catalog.close()
    _emit(
        {
            "version": __version__,
            "cwd": str(Path.cwd()),
            "db": str(db_path),
            "db_exists": db_path.exists() and db_path.stat().st_size > 0,
            "stats": stats,
            "sources": sources,
        }
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    roots: list[tuple[str, str]] = []
    for pair in args.repo:
        if "=" not in pair:
            raise ValueError("--repo expects NAME=PATH, got " + repr(pair))
        name, path = pair.split("=", 1)
        roots.append((name, path))
    rows = collect(roots)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = out_dir / ("report-coverage-" + stamp + ".md")
    target.write_text(render_markdown(rows), encoding="utf-8")
    _emit({"report": str(target), "repos": len(rows)})
    return 0


def _mask_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return key[:8] + "..." + key[-4:]


def cmd_hubcap_check(args: argparse.Namespace) -> int:
    key = (args.key or resolve_secret(args.key_env, env_file=args.env_file) or "").strip()
    if not key:
        _emit(
            {
                "key_ok": False,
                "reason": "no key found: pass --key, set $" + args.key_env + ", or write it to " + args.env_file,
            }
        )
        return 2
    if not is_valid_key(key):
        _emit(
            {
                "key_ok": False,
                "reason": "bad format: expected smm_ followed by 96 lowercase hex chars",
                "key": _mask_key(key),
            }
        )
        return 2

    payload: dict = {"key_ok": True, "key": _mask_key(key), "env_file": args.env_file}
    if not args.skip_stats:
        try:
            stats = hubcap_stats(key)
        except HubcapError as exc:
            payload["error"] = str(exc)
            _emit(payload)
            return 5
        payload["stats"] = {name: value for name, value in stats.items() if name != "raw"}
        if not stats["can_make_requests"]:
            payload["reason"] = "daily limit reached: " + str(stats["daily_usage"]) + "/" + str(stats["daily_limit"])
            _emit(payload)
            return 4

    fetched = []
    for spec in args.fetch or []:
        if ":" not in spec:
            raise ValueError("--fetch expects DEPOT:GID, got " + repr(spec))
        depot_text, gid = spec.split(":", 1)
        client = HubcapClient(key, cache_dir=args.cache_dir)
        try:
            target = client.fetch_manifest(int(depot_text), gid)
        except HubcapError as exc:
            payload["error"] = str(exc)
            _emit(payload)
            return 5
        fetched.append(
            {
                "depot": int(depot_text),
                "gid": gid,
                "path": str(target),
                "bytes": target.stat().st_size if target.exists() else None,
            }
        )
    if fetched:
        payload["fetched"] = fetched
    _emit(payload)
    return 0

def cmd_directlink(args: argparse.Namespace) -> int:
    from .directlink import DirectLink, DirectLinkError

    if args.key:
        key = bytes.fromhex(args.key.replace("0x", ""))
    else:
        import json
        from pathlib import Path as _Path

        payload = json.loads(_Path(args.key_file).read_text(encoding="utf-8-sig"))
        hex_key = payload.get(str(args.depot))
        if not hex_key:
            raise ValueError("depot " + str(args.depot) + " not found in " + args.key_file)
        key = bytes.fromhex(hex_key)

    link = DirectLink(repo=args.repo, branch=args.branch, cdn=args.cdn)
    if getattr(args, "restore", False):
        from .restore import restore_depot

        report = restore_depot(
            args.depot,
            args.gid,
            key,
            args.out_dir,
            link=link,
            workers=getattr(args, "workers", 6),
        )
        payload_out = report.as_dict()
        _emit(payload_out)
        if args.out:
            from pathlib import Path as _PathOutR

            _PathOutR(args.out).write_text(
                json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return 0 if report.ok else 3

    manifest = link.get_manifest(args.depot, args.gid)
    result = link.verify_first_chunk(args.depot, manifest, key)
    payload_out = result.as_dict()
    payload_out["gid"] = args.gid
    payload_out["manifest_bytes"] = result.manifest_bytes or 0
    _emit(payload_out)
    if args.out:
        from pathlib import Path as _PathOut

        _PathOut(args.out).write_text(json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result.sha_ok else 3

def cmd_appinfo(args: argparse.Namespace) -> int:
    from .sources.appinfo import AppInfoError, app_info_raw, depots_from_app_info, parse_app_info

    raw = app_info_raw(args.appid, steamcmd=args.steamcmd)
    info = parse_app_info(raw, args.appid)
    depots = depots_from_app_info(info)
    payload = {
        "appid": args.appid,
        "name": (info.get("common") or {}).get("name"),
        "depots": [depot.as_dict() for depot in depots],
    }
    _emit(payload)
    if args.out:
        from pathlib import Path as _PathOutA

        _PathOutA(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if depots else 3


def cmd_sidecar(args: argparse.Namespace) -> int:
    import time as _time

    from .sidecar import SidecarService, serve

    service = SidecarService(
        keys_path=args.keys,
        index_path=args.index,
        appinfo_cache=args.appinfo_cache,
    )
    server, _thread, port, token = serve(
        service,
        host=args.host,
        port=args.port,
        token=args.token or "",
        port_file=args.port_file,
    )
    _emit({"host": args.host, "port": port, "token": token})
    try:
        while True:
            _time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def cmd_cdn_probe(args: argparse.Namespace) -> int:
    from .sources.cdn import CdnClient, CdnError

    client = CdnClient()
    path = client.manifest_path(args.depot, args.gid, args.version)
    if args.chunk:
        path = client.chunk_path(args.depot, args.chunk)
    results = []
    for host in client.hosts:
        headers = {"User-Agent": "Valve/Steam HTTP Client 1.0"}
        if args.token:
            headers["Authorization"] = "Bearer " + args.token
        try:
            status, payload = client._fetch(host + path, headers)  # noqa: SLF001 - diagnostics
        except Exception as exc:  # noqa: BLE001
            status, payload = type(exc).__name__, b""
        results.append({"host": host, "status": status, "bytes": len(payload)})
    _emit({"path": path, "token": bool(args.token), "hosts": results})
    return 0 if any(item["status"] == 200 for item in results) else 3


def cmd_pan_verify(args: argparse.Namespace) -> int:
    import urllib.request
    from pathlib import Path as _PathPV

    from .pan_verify import verify_batch
    from .sources.xunlei_share import _get, captcha_token, list_share, new_device_id, parse_share_url, walk_share

    share_id, pwd = parse_share_url(args.url)
    pwd = args.pwd or pwd
    device_id = new_device_id()
    token = captcha_token(device_id)
    root_listing = list_share(share_id, pwd, device_id=device_id)
    entries = walk_share(share_id, pwd)

    body = [e for e in entries if args.body_prefix in e.name and "MOD合集" not in e.name]
    if not body:
        _emit({"error": "no body files matched prefix " + args.body_prefix})
        return 3
    body.sort(key=lambda item: item.name)
    start = (args.batch - 1) * args.batch_size
    selected = body[start:start + args.batch_size]
    if not selected:
        _emit({"note": "no files in this batch", "batch": args.batch, "files_total": len(body)})
        return 0

    def resolve(entry) -> str:
        params = {
            "share_id": share_id,
            "file_id": entry.file_id,
            "pass_code": pwd,
            "pass_code_token": root_listing.pass_code_token,
            "folder_id": "",
            "space": "",
            "scene": "NORMAL",
        }
        payload = _get(params, device_id, token, "/share/file_info", 25, None)
        info = payload.get("file_info") or {}
        return str(info.get("web_content_link") or "")

    blocked = []
    links = {}
    for entry in selected:
        url = resolve(entry)
        if url:
            links[entry.name] = url
        else:
            blocked.append(entry.name)
    if blocked:
        _emit({"blocked": blocked, "reason": "share files need login (transfer to own cloud)", "hint": "provide XUNLEI_COOKIE / XUNLEI_AUTHORIZATION"})
        return 4

    def download(name, target):
        request = urllib.request.Request(links[name], headers={"User-Agent": "steam-research/0.1"})
        with urllib.request.urlopen(request, timeout=args.timeout) as response, target.open("wb") as handle:
            while True:
                block = response.read(4 * 1024 * 1024)
                if not block:
                    break
                handle.write(block)

    report = verify_batch(
        "batch-" + str(args.batch).zfill(3),
        [(e.name, e.size) for e in selected],
        _PathPV(args.root),
        download,
        delete=not args.no_delete,
        log_path=args.log,
    )
    payload = report.as_dict()
    _emit(payload)
    return 0 if not report.errors else 3


def cmd_pan_list(args: argparse.Namespace) -> int:
    from .sources.xunlei_share import parse_share_url, walk_share

    share_id, pass_code = parse_share_url(args.url)
    pass_code = args.pwd or pass_code
    entries = walk_share(share_id, pass_code, max_depth=args.max_depth)
    payload = {
        "share_id": share_id,
        "files": [entry.as_dict() for entry in entries],
        "files_total": len(entries),
        "bytes_total": sum(entry.size for entry in entries),
    }
    if args.out:
        from pathlib import Path as _PathPan

        _PathPan(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "share_id": share_id,
        "files_total": payload["files_total"],
        "bytes_total": payload["bytes_total"],
        "largest": sorted(
            ({"name": e.name, "size": e.size} for e in entries), key=lambda item: -item["size"]
        )[:5],
    }
    _emit(summary)
    return 0 if entries else 3


def cmd_coverage(args: argparse.Namespace) -> int:
    from .coverage import check_coverage
    from .keys import Keyring
    from .sources.manifest_index import ManifestIndex

    ring = Keyring()
    for path in args.key_file or []:
        ring.merge(Keyring.from_json_files([path]))
    index = ManifestIndex.load(args.manifest_index) if args.manifest_index else None
    steamtools_probe = None
    if args.steamtools:
        from .sources.steamtools import probe as st_probe

        steamtools_probe = st_probe
    hubcap = None
    if args.hubcap_key:
        from .sources.hubcap import HubcapClient

        hubcap = HubcapClient(args.hubcap_key, cache_dir=args.hubcap_cache)
    def run(appid: int) -> dict:
        report = check_coverage(
            appid,
            keys=ring if args.key_file else None,
            index=index,
            steamcmd=args.steamcmd,
            steamtools_probe=steamtools_probe,
            hubcap=hubcap,
            appinfo_cache=args.appinfo_cache,
        )
        return report.as_dict()

    if args.appids_file:
        from pathlib import Path as _PathBatch

        appids = [
            int(line.strip())
            for line in _PathBatch(args.appids_file).read_text(encoding="utf-8").splitlines()
            if line.strip().isdigit()
        ]
        rows = [run(appid) for appid in appids]
        payload = {
            "appids": appids,
            "downloadable": [row["appid"] for row in rows if row["downloadable"]],
            "blocked": [row["appid"] for row in rows if not row["downloadable"]],
            "rows": rows,
        }
        _emit({"appids": len(appids), "downloadable": len(payload["downloadable"]), "blocked": len(payload["blocked"])})
        if args.out:
            from pathlib import Path as _PathBatchOut

            _PathBatchOut(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0 if not payload["blocked"] else 3

    payload = run(args.appid)
    _emit(payload)
    if args.out:
        from pathlib import Path as _PathOutC

        _PathOutC(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if payload["downloadable"] else 3


def cmd_index_build(args: argparse.Namespace) -> int:
    from .sources.manifest_index import ManifestIndex

    index = ManifestIndex.from_filelist(args.filelist)
    target = index.save(args.out)
    _emit({"out": str(target), "depots": len(index), "manifests": sum(len(v) for v in index.gids.values())})
    return 0


DEFAULT_KEY_CORPORA = (
    "https://raw.githubusercontent.com/dc190/ManifestHub/main/depotkeys.json",
    "https://raw.githubusercontent.com/ooiiuur/ManifestHubSharing/main/depotkeys.json",
)


def cmd_keys_sync(args: argparse.Namespace) -> int:
    from pathlib import Path as _PathSync

    from .keys import Keyring
    from .sources.steamtools import fetch_text, probe

    previous = Keyring()
    out_path = _PathSync(args.out)
    if out_path.is_file():
        previous = Keyring.from_json_files([out_path])

    ring = Keyring()
    ring.merge(previous)
    for path in args.key_file or []:
        ring.merge(Keyring.from_json_files([path]))
    urls = list(args.corpus_url or []) or ([] if args.no_default_corpora else list(DEFAULT_KEY_CORPORA))
    for url in urls:
        try:
            text = fetch_text(url)
            ring.merge(Keyring.from_json_text(text, source=url.rsplit("/", 1)[-1]))
        except Exception as exc:  # noqa: BLE001 - a dead corpus must not stop the sync
            _emit({"warning": "corpus failed: " + type(exc).__name__, "url": url})
    for appid in args.steamtools_app or []:
        try:
            info = probe(appid)
            if not info.key_url:
                _emit({"warning": "steamtools has no key for " + str(appid), "message": info.message})
                continue
            ring.merge(Keyring.from_vdf_text(fetch_text(info.key_url), source="steamtools-" + str(appid)))
        except Exception as exc:  # noqa: BLE001
            _emit({"warning": "steamtools failed for " + str(appid), "error": type(exc).__name__})
    target = ring.save_json(out_path)
    new_depots = sorted(set(ring.keys) - set(previous.keys))
    _emit(
        {
            "out": str(target),
            "keys": len(ring),
            "new_keys": len(new_depots),
            "new_depots": new_depots[:50],
            "invalid_skipped": ring.invalid,
            "sources": ring.sources,
        }
    )
    return 0


def cmd_keys_merge(args: argparse.Namespace) -> int:
    from .keys import Keyring

    ring = Keyring()
    for path in args.key_file:
        ring.merge(Keyring.from_json_files([path]))
    target = ring.save_json(args.out)
    _emit(
        {
            "out": str(target),
            "keys": len(ring),
            "invalid_skipped": ring.invalid,
            "sources": ring.sources,
        }
    )
    return 0


def cmd_restore_app(args: argparse.Namespace) -> int:
    from pathlib import Path as _Path

    from .keys import Keyring
    from .pipeline import restore_app

    key_paths = list(args.key_file or [])
    ring = Keyring()
    for path in key_paths:
        ring = _merge_keyrings(ring, Keyring.from_json_files([path]))
    if args.config_vdf:
        ring = _merge_keyrings(ring, Keyring.from_config_vdf(args.config_vdf))

    only = set(args.only_depot or [])
    if args.retry_from:
        previous = json.loads(_Path(args.retry_from).read_text(encoding="utf-8"))
        pending = {
            int(depot["depot_id"])
            for depot in previous.get("depots", [])
            if depot.get("status") not in ("ok", "skipped")
        }
        only = (only & pending) if only else pending
        if not only:
            _emit({"appid": args.appid, "note": "nothing to retry", "depots": 0})
            return 0

    index = None
    if args.manifest_index:
        from .sources.manifest_index import ManifestIndex

        index = ManifestIndex.load(args.manifest_index)

    hubcap = None
    if args.hubcap_key:
        from .sources.hubcap import HubcapClient

        hubcap = HubcapClient(args.hubcap_key, cache_dir=args.hubcap_cache)

    report = restore_app(
        args.appid,
        args.out_dir,
        keys=ring,
        steamcmd=args.steamcmd,
        workers=args.workers,
        only=only or None,
        max_depot_bytes=args.max_depot_bytes,
        index=index,
        hubcap=hubcap,
        state_path=args.state,
        depot_workers=args.depot_workers,
    )
    payload = report.as_dict()
    _emit(payload)
    if args.out:
        _Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report.ok else 3


def _merge_keyrings(base, extra):
    base.keys.update(extra.keys)
    for source in extra.sources:
        if source not in base.sources:
            base.sources.append(source)
    return base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam_research",
        description="Steam manifest research toolkit (offline first).",
    )
    sub = parser.add_subparsers(dest="command")

    query = sub.add_parser("query", help="look up one appid in the local catalog")
    query.add_argument("appid", type=int)
    query.add_argument("--db", default=str(DEFAULT_DB))
    query.add_argument("--offline", action="store_true", help="accepted for symmetry; query is always local")
    query.set_defaults(handler=cmd_query)

    importer = sub.add_parser("import-acf", help="parse appmanifest_*.acf files into the catalog")
    importer.add_argument("paths", nargs="+")
    importer.add_argument("--db", default=str(DEFAULT_DB))
    importer.set_defaults(handler=cmd_import_acf)

    doctor = sub.add_parser("doctor", help="print catalog health as JSON")
    doctor.add_argument("--db", default=str(DEFAULT_DB))
    doctor.set_defaults(handler=cmd_doctor)

    check = sub.add_parser("hubcap-check", help="validate a Morrenus/hubcap key and show its quota")
    check.add_argument("--key", default=None, help="key value (prefer --key-env or .env)")
    check.add_argument("--key-env", default="HUBBCAP_API_KEY")
    check.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    check.add_argument("--skip-stats", action="store_true", help="only check the key format")
    check.add_argument("--fetch", action="append", default=[], metavar="DEPOT:GID", help="also download one manifest")
    check.add_argument("--cache-dir", default="src/data/cache/manifests")
    check.set_defaults(handler=cmd_hubcap_check)

    info_parser = sub.add_parser("appinfo", help="public depot list for any appid via steamcmd (no ownership needed)")
    info_parser.add_argument("appid", type=int)
    info_parser.add_argument("--steamcmd", default="tools/bin/steamcmd.exe")
    info_parser.add_argument("--out", default=None)
    info_parser.set_defaults(handler=cmd_appinfo)

    restore_parser = sub.add_parser("restore-app", help="restore every depot of an app from public mirrors")
    restore_parser.add_argument("appid", type=int)
    restore_parser.add_argument("--out-dir", required=True)
    restore_parser.add_argument("--key-file", action="append", default=[], metavar="JSON")
    restore_parser.add_argument("--config-vdf", default=None)
    restore_parser.add_argument("--steamcmd", default="tools/bin/steamcmd.exe")
    restore_parser.add_argument("--workers", type=int, default=6)
    restore_parser.add_argument("--only-depot", type=int, action="append", default=[])
    restore_parser.add_argument("--max-depot-bytes", type=int, default=None)
    restore_parser.add_argument("--out", default=None)
    restore_parser.add_argument("--retry-from", default=None, metavar="REPORT.json", help="only retry depots that were not ok/skipped")
    restore_parser.add_argument("--manifest-index", default=None, metavar="INDEX.json", help="depot->gids index; enables any-build fallback")
    restore_parser.add_argument("--hubcap-key", default=None)
    restore_parser.add_argument("--hubcap-cache", default=None)
    restore_parser.add_argument("--state", default=None, metavar="STATE.json", help="resume file: depots already ok are skipped")
    restore_parser.add_argument("--depot-workers", type=int, default=1, help="restore N depots in parallel")

    sidecar_parser = sub.add_parser("sidecar", help="run the local HTTP+JSON-RPC sidecar for the GUI")
    sidecar_parser.add_argument("--host", default="127.0.0.1")
    sidecar_parser.add_argument("--port", type=int, default=0)
    sidecar_parser.add_argument("--token", default=None)
    sidecar_parser.add_argument("--port-file", default=None)
    sidecar_parser.add_argument("--keys", default="src/data/keys/merged.json")
    sidecar_parser.add_argument("--index", default="tests/reports/mirror-index.json")
    sidecar_parser.add_argument("--appinfo-cache", default="src/data/appinfo")
    sidecar_parser.set_defaults(handler=cmd_sidecar)

    cdn_parser = sub.add_parser("cdn-probe", help="probe Steam CDN hosts for a manifest/chunk path")
    cdn_parser.add_argument("--depot", type=int, required=True)
    cdn_parser.add_argument("--gid", default=None)
    cdn_parser.add_argument("--chunk", default=None)
    cdn_parser.add_argument("--version", type=int, default=5)
    cdn_parser.add_argument("--token", default=None)
    cdn_parser.set_defaults(handler=cmd_cdn_probe)

    pan_parser = sub.add_parser("pan-list", help="list a Xunlei share tree without logging in (metadata only)")
    pan_parser.add_argument("url")
    pan_parser.add_argument("--pwd", default=None)
    pan_parser.add_argument("--max-depth", type=int, default=6)
    pan_parser.add_argument("--out", default=None)
    pan_parser.set_defaults(handler=cmd_pan_list)

    verify_parser = sub.add_parser("pan-verify", help="download one batch, hash it, then permanently delete it")
    verify_parser.add_argument("url")
    verify_parser.add_argument("--pwd", default=None)
    verify_parser.add_argument("--batch", type=int, default=1)
    verify_parser.add_argument("--batch-size", type=int, default=1)
    verify_parser.add_argument("--body-prefix", default="PBZ.part")
    verify_parser.add_argument("--root", default="src/data/panverify")
    verify_parser.add_argument("--log", default="tests/reports/pan-verify-log.jsonl")
    verify_parser.add_argument("--timeout", type=float, default=300.0)
    verify_parser.add_argument("--no-delete", action="store_true")
    verify_parser.set_defaults(handler=cmd_pan_verify)

    coverage_parser = sub.add_parser("coverage", help="read-only: can this appid be restored? (no content download)")
    coverage_parser.add_argument("appid", type=int)
    coverage_parser.add_argument("--key-file", action="append", default=[], metavar="JSON")
    coverage_parser.add_argument("--manifest-index", default=None, metavar="INDEX.json")
    coverage_parser.add_argument("--steamcmd", default="tools/bin/steamcmd.exe")
    coverage_parser.add_argument("--appinfo-cache", default=None, metavar="DIR")
    coverage_parser.add_argument("--out", default=None)
    coverage_parser.add_argument("--steamtools", action="store_true", help="also ask steamtools.games whether it is in their DB")
    coverage_parser.add_argument("--hubcap-key", default=None, help="hubcapmanifest API key; fetched manifests count as available")
    coverage_parser.add_argument("--hubcap-cache", default=None)
    coverage_parser.add_argument("--appids-file", default=None, metavar="LIST.txt", help="batch scan: one appid per line")
    coverage_parser.set_defaults(handler=cmd_coverage)

    index_parser = sub.add_parser("index-build", help="build depot->gids index from a mirror file list")
    index_parser.add_argument("--filelist", required=True)
    index_parser.add_argument("--out", required=True)
    index_parser.set_defaults(handler=cmd_index_build)

    sync_parser = sub.add_parser("keys-sync", help="pull public key corpora (+ steamtools key.vdf) into one JSON")
    sync_parser.add_argument("--out", required=True)
    sync_parser.add_argument("--key-file", action="append", default=[], metavar="JSON")
    sync_parser.add_argument("--corpus-url", action="append", default=[], metavar="URL")
    sync_parser.add_argument("--no-default-corpora", action="store_true")
    sync_parser.add_argument("--steamtools-app", type=int, action="append", default=[])
    sync_parser.set_defaults(handler=cmd_keys_sync)

    merge_parser = sub.add_parser("keys-merge", help="merge depot key corpora into one deduped JSON")
    merge_parser.add_argument("--key-file", action="append", required=True, metavar="JSON")
    merge_parser.add_argument("--out", required=True)
    merge_parser.set_defaults(handler=cmd_keys_merge)
    restore_parser.set_defaults(handler=cmd_restore_app)

    direct = sub.add_parser("directlink", help="manifest + one chunk from public mirrors (unowned apps)")
    direct.add_argument("--depot", type=int, required=True)
    direct.add_argument("--gid", required=True)
    direct.add_argument("--key", default=None, help="32-byte depot key as hex")
    direct.add_argument("--key-file", default=None, help="JSON map depot_id -> hex key")
    direct.add_argument("--repo", default="qwe213312/k25FCdfEOoEJ42S6")
    direct.add_argument("--branch", default="main")
    direct.add_argument("--cdn", default="https://steampipe.akamaized.net")
    direct.add_argument("--out", default=None)
    direct.add_argument("--restore", action="store_true", help="download and rebuild every file of the depot")
    direct.add_argument("--out-dir", default=None, help="target directory for --restore")
    direct.add_argument("--workers", type=int, default=6)
    direct.set_defaults(handler=cmd_directlink)

    report = sub.add_parser("report", help="write a ManifestHub coverage report")
    report.add_argument("--repo", action="append", default=[], metavar="NAME=PATH")
    report.add_argument("--out", default="tests/reports")
    report.set_defaults(handler=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args)
    except (AcfParseError, FileNotFoundError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
