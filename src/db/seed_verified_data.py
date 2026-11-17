"""Deprecated compatibility shim for the former synthetic baseline seeder.

This module intentionally does not create prices, branches, promotions, evidence,
or benchmarks. Project research must enter through captured sources and review.
"""
from pathlib import Path
from typing import Optional, Union

from src.db.init_db import initialize_database


def seed_verified_benchmarks(
    db_path: Optional[Union[str, Path]] = None,
    reset: bool = False,
) -> int:
    """Initialize reference tables only; never seed prices or reset a database."""
    if reset:
        raise ValueError("Destructive reset is disabled; use an explicit reviewed migration instead.")
    initialize_database(db_path=db_path, reset=False)
    return 0
