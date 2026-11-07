package core

import (
	"archive/zip"
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"

	"github.com/klauspost/compress/zstd"
	"github.com/ulikunitz/xz/lzma"
)

func unpad(data []byte) []byte {
	if len(data) == 0 {
		return data
	}
	n := int(data[len(data)-1])
	if n <= 0 || n > aes.BlockSize || n > len(data) {
		return data
	}
	return data[:len(data)-n]
}

// decryptChunk: IV = AES-ECB-decrypt(key, cipher[:16]); body = AES-CBC(key, IV, cipher[16:])
func DecryptChunk(cipherText, key []byte) ([]byte, error) {
	if len(cipherText) < aes.BlockSize*2 {
		return nil, fmt.Errorf("chunk too small: %d", len(cipherText))
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	iv := make([]byte, aes.BlockSize)
	block.Decrypt(iv, cipherText[:aes.BlockSize])
	body := cipherText[aes.BlockSize:]
	if len(body)%aes.BlockSize != 0 {
		return nil, fmt.Errorf("body not block aligned: %d", len(body))
	}
	out := make([]byte, len(body))
	cipher.NewCBCDecrypter(block, iv).CryptBlocks(out, body)
	return unpad(out), nil
}

func decodeVZip(payload []byte) ([]byte, error) {
	const header, propsLen, footer = 7, 5, 10
	if len(payload) < header+propsLen+footer {
		return nil, fmt.Errorf("vzip too short")
	}
	props := payload[header : header+propsLen]
	stream := payload[header+propsLen : len(payload)-footer]
	size := uint64(binary.LittleEndian.Uint32(payload[len(payload)-footer+4 : len(payload)-footer+8]))
	if size == 0 || size > 1<<31 {
		return nil, fmt.Errorf("vzip bad size %d", size)
	}
	classic := make([]byte, 0, propsLen+8+len(stream))
	classic = append(classic, props...)
	var sz [8]byte
	binary.LittleEndian.PutUint64(sz[:], size)
	classic = append(classic, sz[:]...)
	classic = append(classic, stream...)
	reader, err := lzma.ReaderConfig{DictCap: 1 << 27}.NewReader(bytes.NewReader(classic))
	if err != nil {
		return nil, err
	}
	return io.ReadAll(reader)
}

var zstdDecoder, _ = zstd.NewReader(nil, zstd.WithDecoderConcurrency(1))

func decodeVZstd(payload []byte) ([]byte, error) {
	const header, footer = 8, 15
	if len(payload) < header+footer {
		return nil, fmt.Errorf("vzstd too short")
	}
	return zstdDecoder.DecodeAll(payload[header:len(payload)-footer], nil)
}

func decodeZip(payload []byte) ([]byte, error) {
	reader, err := zip.NewReader(bytes.NewReader(payload), int64(len(payload)))
	if err != nil {
		return nil, err
	}
	if len(reader.File) == 0 {
		return nil, fmt.Errorf("empty zip")
	}
	file, err := reader.File[0].Open()
	if err != nil {
		return nil, err
	}
	defer file.Close()
	return io.ReadAll(file)
}

func HexKey(text string) ([]byte, error) {
	key, err := hex.DecodeString(text)
	if err != nil || len(key) != 32 {
		return nil, fmt.Errorf("bad depot key")
	}
	return key, nil
}

func Decompress(plain []byte) (string, []byte, error) {
	switch {
	case bytes.HasPrefix(plain, []byte("VZa")):
		out, err := decodeVZip(plain)
		return "vzip", out, err
	case bytes.HasPrefix(plain, []byte("VSZa")):
		out, err := decodeVZstd(plain)
		return "vzstd", out, err
	case bytes.HasPrefix(plain, []byte("PK\x03\x04")):
		out, err := decodeZip(plain)
		return "zip", out, err
	default:
		return "raw", plain, nil
	}
}
