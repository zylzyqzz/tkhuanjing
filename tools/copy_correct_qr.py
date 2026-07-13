from pathlib import Path
import shutil

src = Path("C:\\Users\\Administrator\\Desktop\\\u6781\u901f\u7535\u8111\u6e05\u7406Pro\\\u6536\u6b3e\u7801.jpg")
dst = Path(__file__).resolve().parent / "qr_correct.jpg"
if not src.exists():
    raise FileNotFoundError(src)
shutil.copy2(src, dst)
print(dst, dst.stat().st_size)
