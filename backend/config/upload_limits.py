"""Global upload ceiling independent of an operator's per-installation setting."""

HARD_MAX_UPLOAD_BYTES = 5 * 1024**3


def configured_upload_bytes(raw_megabytes: str) -> int:
    megabytes = int(raw_megabytes)
    if megabytes < 1:
        raise ValueError("MAX_UPLOAD_MB must be positive")
    return min(megabytes * 1024**2, HARD_MAX_UPLOAD_BYTES)
