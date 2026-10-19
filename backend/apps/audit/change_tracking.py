"""Content-minimized, deterministic descriptors of human text edits.

Audit metadata must not outlive a deleted meeting with copies of its transcript.
The HMAC prevents trivial offline guessing of short phrases from a leaked audit DB.
"""

import hashlib
import hmac
import json

from django.conf import settings

_MISSING = object()


def fingerprint(value):
    if value is _MISSING:
        return None
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def describe_changes(before, after, path=""):
    """Return every changed leaf's stable path and HMAC, never the leaf content."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}.{key}" if path else str(key)
            result.extend(
                describe_changes(before.get(key, _MISSING), after.get(key, _MISSING), child)
            )
        return result
    if isinstance(before, list) and isinstance(after, list):
        result = []
        for index in range(max(len(before), len(after))):
            old = before[index] if index < len(before) else _MISSING
            new = after[index] if index < len(after) else _MISSING
            result.extend(describe_changes(old, new, f"{path}[{index}]"))
        return result
    if before == after:
        return []
    return [{"path": path, "before": fingerprint(before), "after": fingerprint(after)}]
