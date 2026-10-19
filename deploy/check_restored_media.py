"""Verify that restored private media files match a backup manifest."""

import hashlib
import json
import sys
from pathlib import Path


def main(manifest_file: Path, media_root: Path) -> None:
    entries = json.loads(manifest_file.read_text(encoding="utf-8"))
    if isinstance(entries, dict):
        entries = [entries]
    count = 0
    for entry in entries:
        relative = entry["path"].replace("\\", "/")
        if not relative.startswith("media/"):
            continue
        path = (media_root / relative.removeprefix("media/")).resolve()
        if not path.is_relative_to(media_root.resolve()) or not path.is_file():
            raise ValueError("Mídia restaurada ausente ou fora do volume")
        digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest().upper()
        if digest != entry["sha256"].upper() or path.stat().st_size != entry["bytes"]:
            raise ValueError("Mídia restaurada não confere com o manifesto")
        count += 1
    print(f"Mídia restaurada e verificada: {count} arquivo(s)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
