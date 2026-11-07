
import pathlib
root = pathlib.Path(r"E:\vibe coding\steam")

def sub(path, pairs):
    p = root / path
    if not p.exists():
        print("MISSING", path); return
    s = p.read_text(encoding="utf-8")
    orig = s
    for a, b in pairs:
        s = s.replace(a, b)
    if s != orig:
        p.write_text(s, encoding="utf-8")
        print("updated", path)
    else:
        print("nochange", path)

sub("tools/relaycore/go.mod", [("module steamcore", "module relaycore")])
sub("tools/relaycore/main.go", [('"steamcore/core"', '"relaycore/core"')])
sub("app/relaystore/go.mod", [
    ("module steamclient", "module relaystore"),
    ("steamcore v0.0.0", "relaycore v0.0.0"),
    ("replace steamcore => ../../tools/steamcore", "replace relaycore => ../../tools/relaycore"),
])
sub("app/relaystore/app.go", [
    ('"steamcore/core"', '"relaycore/core"'),
    ('filepath.Join(base, "steamstore")', 'filepath.Join(base, "relaystore")'),
    ('"steamstore/1.0"', '"relaystore/1.0"'),
])
sub("app/relaystore/wails.json", [
    ('"name": "steamclient"', '"name": "relaystore"'),
    ('"outputfilename": "steamclient"', '"outputfilename": "relaystore"'),
])
sub("app/relaystore/main.go", [('Title:  "Steam 客户端"', 'Title:  "云驿"')])
sub("app/relaystore/frontend/dist/index.html", [
    ("<title>Steam 客户端</title>", "<title>云驿</title>"),
    ("<h1>Steam 客户端</h1>", "<h1>云驿</h1>"),
])
sub("app/relaystore/frontend/dist/main.js", [('"Steam 客户端"', '"云驿"')])
sub(".github/workflows/ci.yml", [
    ("Set-Location app/steamclient", "Set-Location app/relaystore"),
    ("cd tools/steamcore", "cd tools/relaycore"),
    ("-o steamclient.exe", "-o relaystore.exe"),
    ("Test-Path steamclient.exe", "Test-Path relaystore.exe"),
    ("Get-Item steamclient.exe", "Get-Item relaystore.exe"),
    ("path: app/steamclient/steamclient.exe", "path: app/relaystore/relaystore.exe"),
    ("name: steamclient-windows", "name: relaystore-windows"),
    ("steamstore-", "relaystore-"),
    ("dist/steamclient.exe", "dist/relaystore.exe"),
    ("source snapshot + windows build", "relaystore source snapshot + windows build"),
])
sub(".gitignore", [
    ("app/steamclient/", "app/relaystore/"),
    ("tools/steamcore/", "tools/relaycore/"),
])
print("done")
