package core

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
)

const (
	sectionPayload  = 0x71F617D0
	sectionMetadata = 0x1F4812BE
	sectionEnd      = 0x32C415AB
)

type Chunk struct {
	SHA          string
	CRC          uint32
	Offset       uint64
	CbOriginal   uint32
	CbCompressed uint32
}

type FileEntry struct {
	Names      []string
	Size       uint64
	ShaContent string
	LinkTarget string
	Chunks     []Chunk
}

type Manifest struct {
	Files    []FileEntry
	Metadata map[string]uint64
}

func (m *Manifest) TotalBytes() uint64 {
	var sum uint64
	for _, f := range m.Files {
		sum += f.Size
	}
	return sum
}

func (m *Manifest) UniqueChunks() int {
	seen := map[string]bool{}
	for _, f := range m.Files {
		for _, c := range f.Chunks {
			seen[c.SHA] = true
		}
	}
	return len(seen)
}

func readVarint(data []byte, pos int) (uint64, int, error) {
	var result uint64
	var shift uint
	for {
		if pos >= len(data) {
			return 0, pos, errors.New("varint out of range")
		}
		b := data[pos]
		pos++
		result |= uint64(b&0x7F) << shift
		if b < 0x80 {
			return result, pos, nil
		}
		shift += 7
		if shift > 63 {
			return 0, pos, errors.New("varint too long")
		}
	}
}

func hexString(b []byte) string {
	const digits = "0123456789abcdef"
	out := make([]byte, len(b)*2)
	for i, v := range b {
		out[i*2] = digits[v>>4]
		out[i*2+1] = digits[v&0x0F]
	}
	return string(out)
}

// field describes one protobuf field: wire 0 varint, 1 fixed64, 2 bytes, 5 fixed32.
type field struct {
	Number int
	Wire   int
	Varint uint64
	Bytes  []byte
	Fixed  uint32
}

func fields(data []byte) ([]field, error) {
	var out []field
	pos := 0
	for pos < len(data) {
		key, next, err := readVarint(data, pos)
		if err != nil {
			return nil, err
		}
		pos = next
		f := field{Number: int(key >> 3), Wire: int(key & 7)}
		switch f.Wire {
		case 0:
			v, next, err := readVarint(data, pos)
			if err != nil {
				return nil, err
			}
			pos = next
			f.Varint = v
		case 1:
			if pos+8 > len(data) {
				return nil, errors.New("fixed64 out of range")
			}
			pos += 8
		case 2:
			length, next, err := readVarint(data, pos)
			if err != nil {
				return nil, err
			}
			pos = next
			if pos+int(length) > len(data) {
				return nil, errors.New("bytes out of range")
			}
			f.Bytes = data[pos : pos+int(length)]
			pos += int(length)
		case 5:
			if pos+4 > len(data) {
				return nil, errors.New("fixed32 out of range")
			}
			f.Fixed = binary.LittleEndian.Uint32(data[pos : pos+4])
			pos += 4
		default:
			return nil, fmt.Errorf("unsupported wire type %d", f.Wire)
		}
		out = append(out, f)
	}
	return out, nil
}

func parseChunk(data []byte) (Chunk, error) {
	var c Chunk
	items, err := fields(data)
	if err != nil {
		return c, err
	}
	for _, f := range items {
		switch {
		case f.Number == 1 && f.Wire == 2:
			c.SHA = hexString(f.Bytes)
		case f.Number == 2 && f.Wire == 5:
			c.CRC = f.Fixed
		case f.Number == 3 && f.Wire == 0:
			c.Offset = f.Varint
		case f.Number == 4 && f.Wire == 0:
			c.CbOriginal = uint32(f.Varint)
		case f.Number == 5 && f.Wire == 0:
			c.CbCompressed = uint32(f.Varint)
		}
	}
	if c.SHA == "" {
		return c, errors.New("chunk without sha")
	}
	return c, nil
}

func parseFileMapping(data []byte) (FileEntry, error) {
	var entry FileEntry
	items, err := fields(data)
	if err != nil {
		return entry, err
	}
	for _, f := range items {
		switch {
		case f.Number == 1 && f.Wire == 2:
			entry.Names = append(entry.Names, string(f.Bytes))
		case f.Number == 2 && f.Wire == 0:
			entry.Size = f.Varint
		case f.Number == 5 && f.Wire == 2:
			entry.ShaContent = hexString(f.Bytes)
		case f.Number == 6 && f.Wire == 2:
			chunk, err := parseChunk(f.Bytes)
			if err != nil {
				return entry, err
			}
			entry.Chunks = append(entry.Chunks, chunk)
		case f.Number == 7 && f.Wire == 2:
			entry.LinkTarget = string(f.Bytes)
		}
	}
	return entry, nil
}

func parsePayload(data []byte) ([]FileEntry, error) {
	items, err := fields(data)
	if err != nil {
		return nil, err
	}
	var files []FileEntry
	for _, f := range items {
		if f.Number == 1 && f.Wire == 2 {
			entry, err := parseFileMapping(f.Bytes)
			if err != nil {
				return nil, err
			}
			files = append(files, entry)
		}
	}
	return files, nil
}

func parseMetadata(data []byte) (map[string]uint64, error) {
	meta := map[string]uint64{}
	items, err := fields(data)
	if err != nil {
		return meta, err
	}
	names := map[int]string{1: "depot_id", 2: "gid_manifest", 3: "creation_time", 8: "unique_chunks"}
	for _, f := range items {
		if f.Wire == 0 {
			if name, ok := names[f.Number]; ok {
				meta[name] = f.Varint
			}
		}
	}
	return meta, nil
}

func ParseManifest(data []byte) (*Manifest, error) {
	m := &Manifest{}
	pos := 0
	for pos+4 <= len(data) {
		magic := binary.LittleEndian.Uint32(data[pos : pos+4])
		pos += 4
		if magic == sectionEnd {
			return m, nil
		}
		if pos+4 > len(data) {
			return nil, errors.New("truncated section length")
		}
		length := int(int32(binary.LittleEndian.Uint32(data[pos : pos+4])))
		pos += 4
		if length < 0 || pos+length > len(data) {
			return nil, errors.New("truncated section body")
		}
		blob := data[pos : pos+length]
		pos += length
		switch magic {
		case sectionPayload:
			files, err := parsePayload(blob)
			if err != nil {
				return nil, err
			}
			m.Files = files
		case sectionMetadata:
			meta, err := parseMetadata(blob)
			if err != nil {
				return nil, err
			}
			m.Metadata = meta
		}
	}
	return nil, errors.New("missing end-of-manifest marker")
}

func LoadManifest(path string) (*Manifest, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return ParseManifest(data)
}
