from pathlib import Path


def test_root_plugin_sources_match_canonical_package_sources():
    root = Path(__file__).resolve().parents[1]
    pairs = (
        (root / "src" / "recall_memory_hermes" / "__init__.py", root / "__init__.py"),
        (root / "src" / "recall_memory_hermes" / "memory_policy.py", root / "memory_policy.py"),
    )
    mismatches = [target.name for source, target in pairs if source.read_bytes() != target.read_bytes()]
    assert mismatches == [], f"run scripts/sync_sources.py; drifted: {mismatches}"
