import struct
from pathlib import Path

data = (Path(__file__).resolve().parent.parent / "web-app" / "programs" / "display2.mpy").read_bytes()
print("total size:", len(data))
print("first 80 bytes hex:", data[:80].hex(" "))
off = 0
i = 0
while off < len(data):
    sz = struct.unpack_from("<I", data, off)[0]
    if sz == 0 or sz > len(data):
        break
    name_end = data.index(b"\0", off + 4)
    name = data[off + 4:name_end].decode("utf-8", "replace")
    print(f'entry {i}: size={sz} name="{name}" name_len={name_end - (off + 4)}')
    mpy_off = name_end + 1
    print(f'  mpy header: {data[mpy_off:mpy_off+8].hex(" ")}')
    off = mpy_off + sz
    i += 1
    if i > 10:
        break
