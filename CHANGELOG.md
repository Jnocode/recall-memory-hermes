# Changelog

All notable changes are documented here. Versions follow semantic versioning while the project is pre-1.0.

## [0.3.0] - 2026-07-31

### Added

- Safe dependency self-healing through Hermes `tools.lazy_deps.install_specs()`.
- Manifest `pip_dependencies` for `recall-sqlite==0.2.0` and `httpx>=0.27,<1`.
- Active Hermes profile configuration loading and `hermes memory setup` schema persistence.
- Project namespaces for Hermes memory, Code Gaps, Podcast, Spirits Calling, job search, trading, VSkin, ComfyUI, and social publishing.
- Exact-project-first retrieval with bounded general fallback.
- Typed built-in mirror cards and idempotent add/replace/remove behavior.
- Primary-context-only write policy.
- Kiro requirements, design, and task specifications.
- Windows/Linux CI, source-parity checks, release metadata checks, and clean package gates.

### Changed

- Default embedding endpoint is the OpenAI-compatible Ollama base `http://127.0.0.1:11434` using `nomic-embed-text`.
- Provider configuration now updates the actual `recall.embed` module before embedding calls.
- Durable admission rejects delegation, background, compaction, and tool wrappers before evaluating explicit intent markers.
- Root Git-plugin sources are generated from canonical `src/recall_memory_hermes/` sources.
- Generated distributions and egg-info are no longer stored in Git.
- Added compatibility aliases for Hermes 0.19.0 and current 0.19.x provider interfaces.
- Git repository installs are the supported Hermes plugin surface; the PyPI wheel is explicitly a Python library artifact, not a plugin discovery bridge.

### Fixed

- `is_available()` no longer creates or mutates the Recall database.
- Active-profile `hermes_home` now determines the default DB path at initialization time.
- Replace/remove built-in operations no longer create duplicate or empty semantic memories.
- Unrelated project memories no longer leak into namespace-filtered recall.
- Legacy untagged cards are general-only.
- Publishing cannot proceed when tag, source, manifest, or package versions disagree.
- Session-switch writes now use the current session provenance, and configured absolute DBs are declared to Hermes backup.
- Embedding route changes clear Recall's text-only cache; credential-bearing URLs and empty queries fail closed.
- Deterministic memory IDs make concurrent provider instances converge on one SQLite row.
- Cleanup apply now rejects missing DB paths and verifies all archived episodic IDs were deleted.
- The retired `v0.2.1` tag is denied explicitly by the release checker.

### Compatibility and migration

- No Recall SQLite schema migration is performed.
- Existing databases remain compatible with `recall-sqlite==0.2.0`.
- Ordinary Hot/Warm/Cold movement is tier management, not a capacity failure.
- The historical failed `v0.2.1` tag is retained and is not reused.

## [0.2.0] - 2026-07-24

- Added curated semantic writes, project tags, and archive-first episodic compaction utilities.

## [0.1.0] - 2026-07-20

- Initial public Hermes Recall memory-provider plugin.
