import struct, zlib, sys
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

src = Path(sys.argv[1]); dst = Path(sys.argv[2]); replacement = Path(sys.argv[3])
entry_name = "\u6536\u6b3e\u7801.jpg"
archive = CArchiveReader(str(src))
pkg_start = archive._start_offset
entry_pos, entry_len, _, _, _ = archive.toc[entry_name]
payload = replacement.read_bytes()
compressed = zlib.compress(payload, 9)
raw = src.read_bytes()
cookie_fmt = "!8sIIII64s"
cookie_len = struct.calcsize(cookie_fmt)
cookie_abs = len(raw) - cookie_len
magic, archive_len, toc_offset, toc_length, pyvers, pylib = struct.unpack(cookie_fmt, raw[cookie_abs:])
toc_abs = pkg_start + toc_offset
toc = bytearray(raw[toc_abs:toc_abs + toc_length])
delta = len(compressed) - entry_len
pos = 0
while pos < toc_length:
    size = struct.unpack("!I", toc[pos:pos + 4])[0]
    pos_value = struct.unpack("!I", toc[pos + 4:pos + 8])[0]
    if pos_value == entry_pos:
        struct.pack_into("!I", toc, pos + 8, len(compressed))
    elif pos_value > entry_pos:
        struct.pack_into("!I", toc, pos + 4, pos_value + delta)
    pos += size
new_cookie = struct.pack(cookie_fmt, magic, archive_len + delta, toc_offset + delta, toc_length, pyvers, pylib)
out = raw[:pkg_start + entry_pos] + compressed + raw[pkg_start + entry_pos + entry_len:toc_abs] + toc + raw[toc_abs + toc_length:cookie_abs] + new_cookie
dst.write_bytes(out)
print(dst, len(out), 'delta', delta)
