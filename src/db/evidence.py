"""Validation helpers for locally captured, hash-checked evidence artifacts."""
import hashlib
from pathlib import Path
from typing import Mapping, Any


def has_valid_artifact(evidence: Mapping[str, Any]) -> bool:
    """Require a readable local artifact whose bytes match the stored SHA-256."""
    file_path = evidence.get("file_path")
    expected_hash = evidence.get("file_hash_sha256")
    if not file_path or not expected_hash:
        return False
    path = Path(file_path)
    if not path.is_file():
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest.casefold() == str(expected_hash).casefold()
