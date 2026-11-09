package core

import "testing"

func TestManifestArchHint(t *testing.T) {
	entry := func(names ...string) FileEntry { return FileEntry{Names: names} }
	cases := []struct {
		name  string
		files []FileEntry
		want  string
	}{
		{"windows64", []FileEntry{entry("a/x86_64/b.dll"), entry("a/x86_64/c.dll")}, "x64"},
		{"windows32", []FileEntry{entry("a/Plugins/x86/b.dll"), entry("a/Plugins/x86/c.dll")}, "x32"},
		{"mixed", []FileEntry{entry("a/x86_64/b.dll"), entry("a/x86/c.dll")}, ""},
		{"plain", []FileEntry{entry("data/assets.bin")}, ""},
	}
	for _, c := range cases {
		if got := manifestArchHint(&Manifest{Files: c.files}); got != c.want {
			t.Fatalf("%s: got %q want %q", c.name, got, c.want)
		}
	}
}
