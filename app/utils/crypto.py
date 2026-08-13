"""Hashing helpers."""

import hashlib


def sha256(text):
    """Return the SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode()).hexdigest()
