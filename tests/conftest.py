import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from samples.build_sample import build as build_sample  # noqa: E402

PROFILE = str(ROOT / "config" / "hecvat_profile.yaml")


@pytest.fixture(scope="session")
def profile_path() -> str:
    return PROFILE


@pytest.fixture(scope="session")
def sample_hecvat(tmp_path_factory) -> str:
    out = tmp_path_factory.mktemp("hecvat") / "sample.xlsx"
    return build_sample(str(out))
