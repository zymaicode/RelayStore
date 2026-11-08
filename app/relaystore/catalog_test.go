package main

import "testing"

func TestCatalogLoads(t *testing.T) {
	file := loadCatalog()
	if len(file.Games) < 10 {
		t.Fatalf("catalog too small: %d (updated=%q)", len(file.Games), file.Updated)
	}
	if file.Updated == "" {
		t.Fatal("updated field missing")
	}
}
