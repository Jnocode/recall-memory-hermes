from pathlib import Path
import subprocess

import tomllib
import pytest
import yaml

from scripts.check_release import check


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_v030_and_manifest_declares_dependencies():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "0.3.0"
    assert manifest["version"] == "0.3.0"
    assert manifest["pip_dependencies"] == ["recall-sqlite==0.2.0", "httpx>=0.27,<1"]


def test_generated_build_artifacts_are_not_tracked():
    if not (ROOT / ".git").exists():
        pytest.skip("Git tracking assertion only applies to a repository checkout")
    tracked = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8"
    ).splitlines()
    forbidden = [
        path for path in tracked
        if path.startswith("dist/")
        or path.endswith(".db")
        or any(part.endswith(".egg-info") for part in Path(path).parts)
    ]
    assert forbidden == []


def test_release_checker_accepts_v030_tag():
    assert check("v0.3.0") == []


def test_release_checker_explicitly_rejects_retired_v021_tag():
    errors = check("v0.2.1")
    assert any("retired tag" in error for error in errors)
