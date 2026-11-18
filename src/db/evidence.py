"""Validation helpers for locally captured, hash-checked evidence artifacts."""
import hashlib
from pathlib import Path
from typing import Mapping, Any


def has_valid_artifact(evidence: Mapping[str, Any]) -> bool:
    """Require a readable local artifact whose bytes match the stored SHA-256."""
    expected_hash = evidence.get("file_hash_sha256")
    if not expected_hash:
        return False
    artifact_content = evidence.get("artifact_content")
    if artifact_content is not None:
        content = bytes(artifact_content)
    else:
        file_path = evidence.get("file_path")
        if not file_path:
            return False
        path = Path(file_path)
        if not path.is_file():
            return False
        content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    return digest.casefold() == str(expected_hash).casefold()
