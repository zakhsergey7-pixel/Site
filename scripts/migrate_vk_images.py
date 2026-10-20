"""Скачивает все изображения с серверов VK (userapi.com / vkuserphoto.ru),
сохраняет их в img/vk/ и заменяет ссылки во всех HTML-файлах сайта на локальные.

Запускается в GitHub Actions (workflow migrate-vk-images.yml).
"""
import hashlib
import io
import pathlib
import re
import sys
import time
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "img" / "vk"
MAX_WIDTH = 1600
QUALITY = 82

URL_RE = re.compile(
    r"https://sun9-\d+\.(?:userapi\.com|vkuserphoto\.ru)[^\"'\s)>`]+"
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  попытка {attempt + 1} не удалась: {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"не удалось скачать {url}")


def optimize(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if img.width > MAX_WIDTH:
        h = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, h), Image.LANCZOS)
    buf = io.BytesIO()
    if has_alpha:
        img.save(buf, "PNG", optimize=True)
    else:
        img.convert("RGB").save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), ("png" if has_alpha else "jpg")


def main() -> int:
    html_files = [p for p in ROOT.rglob("*.html") if ".git" not in p.parts]
    urls = set()
    for p in html_files:
        urls.update(URL_RE.findall(p.read_text(encoding="utf-8")))
    urls = sorted(urls)
    print(f"Найдено ссылок на VK: {len(urls)}")
    if not urls:
        return 0

    # одно и то же фото может встречаться в разных размерах (параметр cs=) —
    # скачиваем его один раз, в самом крупном варианте
    def width(u: str) -> int:
        m = re.search(r"[?&]cs=(\d+)x", u)
        return int(m.group(1)) if m else 0

    groups = {}
    for u in urls:
        groups.setdefault(u.split("?")[0], []).append(u)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {}
    failed = []
    for i, (base, variants) in enumerate(sorted(groups.items()), 1):
        best = max(variants, key=width)
        name = hashlib.sha1(base.encode()).hexdigest()[:12]
        print(f"[{i}/{len(groups)}] {base[:90]}")
        try:
            raw = fetch(best)
            data, ext = optimize(raw)
        except Exception as e:  # noqa: BLE001
            print(f"  ОШИБКА: {e}")
            failed.extend(variants)
            continue
        target = OUT_DIR / f"{name}.{ext}"
        target.write_bytes(data)
        print(f"  {len(raw)//1024} КБ -> {len(data)//1024} КБ  {target.name}")
        for u in variants:
            mapping[u] = f"/img/vk/{target.name}"

    changed = 0
    for p in html_files:
        text = p.read_text(encoding="utf-8")
        new = URL_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Обновлено HTML-файлов: {changed}, перенесено изображений: {len(mapping)}, ошибок: {len(failed)}")
    for u in failed:
        print("  не удалось:", u)
    return 1 if failed and not mapping else 0


if __name__ == "__main__":
    sys.exit(main())
