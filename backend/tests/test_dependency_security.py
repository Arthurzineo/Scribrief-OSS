"""Guard the known TLS trust-store remediation in every dependency artifact."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_CERTIFI = (2026, 10, 19)


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_certifi_floor_and_resolved_artifacts_are_patched():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "certifi>=2026.10.19" in project["project"]["dependencies"]

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(package for package in lock["package"] if package["name"] == "certifi")
    assert _version_tuple(locked["version"]) >= MIN_CERTIFI

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"(?m)^certifi==([0-9.]+)\s*\\", requirements)
    assert match is not None
    assert _version_tuple(match.group(1)) >= MIN_CERTIFI
    via_comment = requirements.find("\n    # via", match.end())
    assert via_comment > match.end()
    assert "--hash=sha256:" in requirements[match.start() : via_comment]
