from __future__ import annotations

import re
from pathlib import Path
import tomllib

import cleanroomx


ROOT = Path(__file__).resolve().parents[1]
PEP440_DEVELOPMENT_VERSION = re.compile(
    r"^[0-9]+(?:\\.[0-9]+){2}\\.dev[0-9]+$"
)


def test_release3_development_package_identity_is_distinct_and_aligned() -> None:
    metadata = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = metadata["project"]["version"]

    assert declared == cleanroomx.__version__
    assert declared != "0.102.1"
    assert PEP440_DEVELOPMENT_VERSION.fullmatch(declared)
