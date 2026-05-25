import asyncio, tempfile, struct
from pathlib import Path
from pybricksdev.compile import compile_multi_file

async def go():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.py"
        p.write_text('print("hej fra hub")\n')
        b = await compile_multi_file(str(p), 6)
        out = Path("web-app") / "programs" / "display2.mpy"
        out.write_bytes(b)
        print("Built test, size=", len(b))
        off = 0
        i = 0
        while off < len(b) and i < 5:
            sz = struct.unpack_from("<I", b, off)[0]
            name_end = b.index(0, off + 4)
            name = b[off + 4 : name_end].decode()
            body_off = name_end + 1
            print(f"  @{off}: size={sz} name={name!r} bodyhdr={b[body_off:body_off+12].hex()}")
            off = body_off + sz
            i += 1

asyncio.run(go())
