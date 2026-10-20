"""Переносит фото с серверов VK (userapi.com / vkuserphoto.ru) в репозиторий.

Исходники лежат в img/vk-src/<id>.jpg, где <id> — идентификатор фото из ссылки VK
(часть пути после /ig2/ без .jpg). Скрипт сжимает их в img/vk/, заменяет ссылки
во всех HTML-файлах и удаляет img/vk-src. Ссылки, для которых исходника нет,
остаются как есть.
"""
import hashlib
import io
import pathlib
import re
import shutil
import sys

from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "img" / "vk-src"
OUT_DIR = ROOT / "img" / "vk"
MAX_WIDTH = 1600
QUALITY = 82

URL_RE = re.compile(r"https://sun9-\d+\.(?:userapi\.com|vkuserphoto\.ru)[^\"'\s)>`]+")


def photo_id(url: str) -> str:
    return url.split("?")[0].rsplit("/", 1)[-1].removesuffix(".jpg")


def optimize(path: pathlib.Path) -> bytes:
    img = ImageOps.exif_transpose(Image.open(path))
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def main() -> int:
    if not SRC_DIR.exists():
        print("Папки img/vk-src нет — нечего переносить")
        return 0
    sources = {p.stem: p for p in SRC_DIR.glob("*.jpg")}
    print(f"Исходников: {len(sources)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    local = {}
    for pid, path in sources.items():
        name = hashlib.sha1(pid.encode()).hexdigest()[:12] + ".jpg"
        data = optimize(path)
        (OUT_DIR / name).write_bytes(data)
        local[pid] = f"/img/vk/{name}"
        print(f"  {pid[:16]}…  {path.stat().st_size // 1024} КБ -> {len(data) // 1024} КБ")

    replaced, left = 0, set()

    def sub(m):
        nonlocal replaced
        pid = photo_id(m.group(0))
        if pid in local:
            replaced += 1
            return local[pid]
        left.add(pid)
        return m.group(0)

    for p in ROOT.rglob("*.html"):
        if ".git" in p.parts:
            continue
        text = p.read_text(encoding="utf-8")
        new = URL_RE.sub(sub, text)
        if new != text:
            p.write_text(new, encoding="utf-8")

    shutil.rmtree(SRC_DIR)
    print(f"Заменено ссылок: {replaced}. Осталось на VK фото: {len(left)}")
    for pid in sorted(left):
        print("  осталось на VK:", pid[:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
