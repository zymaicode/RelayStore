import sys, time, json
sys.path.insert(0, r"E:\vibe coding\steam\src\py")
from steam_research.depot import decode_chunk
key = bytes.fromhex(json.load(open(r"E:\vibe coding\steam\src\data\keys\merged.json", encoding="utf-8"))["1276160"])
cipher = open(r"E:\vibe coding\steam\tests\reports\sample-chunk.bin", "rb").read()
# warm up (openssl subprocess path + zstd)
plain = decode_chunk(cipher, key)
import hashlib
print("plain", len(plain), "sha1", hashlib.sha1(plain).hexdigest())
n = 10
t0 = time.perf_counter()
for _ in range(n):
    decode_chunk(cipher, key)
dt = time.perf_counter() - t0
print("python: %.2f ms/op, %.1f MB/s" % (dt/n*1000, len(plain)*n/1048576/dt))