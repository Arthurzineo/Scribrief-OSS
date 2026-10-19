"""Runtime secret files used by the isolated beta deployment."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.runtime_secrets import read_secret


def test_reads_secret_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("  value-from-file\n", encoding="utf-8")
    monkeypatch.delenv("EXAMPLE_SECRET", raising=False)
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(secret_file))

    assert read_secret("EXAMPLE_SECRET") == "value-from-file"


def test_rejects_ambiguous_secret_sources(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-value", encoding="utf-8")
    monkeypatch.setenv("EXAMPLE_SECRET", "environment-value")
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(secret_file))

    with pytest.raises(ImproperlyConfigured, match="both"):
        read_secret("EXAMPLE_SECRET")


def test_missing_secret_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("EXAMPLE_SECRET", raising=False)
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(tmp_path / "missing"))

    with pytest.raises(ImproperlyConfigured, match="cannot be read"):
        read_secret("EXAMPLE_SECRET")


def test_legacy_environment_value_still_works(monkeypatch):
    monkeypatch.setenv("EXAMPLE_SECRET", "existing-value")
    monkeypatch.delenv("EXAMPLE_SECRET_FILE", raising=False)

    assert read_secret("EXAMPLE_SECRET") == "existing-value"
