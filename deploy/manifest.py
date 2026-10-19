"""Portable SHA-256 manifest for beta backup bundles."""

import hashlib
import json
import sys
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def create(root: Path) -> None:
    items = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            items.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            })
    (root / "manifest.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Manifesto criado: {len(items)} arquivo(s)")


def verify(root: Path) -> None:
    items = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(items, list):
        items = [items]
    for item in items:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Arquivo ausente ou caminho fora do backup")
        if digest(path) != item["sha256"].upper() or path.stat().st_size != item["bytes"]:
            raise ValueError("Integridade do backup falhou")
    for name in (
        "database.dump", "beta.env", "secrets/django_secret",
        "secrets/database_password", "secrets/redis_password", "secrets/sector_key",
    ):
        if not (root / name).is_file():
            raise ValueError(f"Backup incompleto: {name}")
    print(f"Manifesto verificado: {len(items)} arquivo(s)")


if __name__ == "__main__":
    action, directory = sys.argv[1:3]
    if action == "create":
        create(Path(directory))
    elif action == "verify":
        verify(Path(directory))
    else:
        raise SystemExit("Use create ou verify")
