# recall-memory-hermes v0.3.0 Requirements

**Status:** Approved for implementation
**Owner:** Jun / Jnocode
**Target:** `recall-memory-hermes` v0.3.0
**Last updated:** 2026-07-31

## 1. Problem statement

Hermes has two independent memory layers: always-injected built-in files (`MEMORY.md` / `USER.md`) and the external Recall SQLite semantic store. The v0.2.x plugin conflates their operational status, does not reliably consume provider configuration, can become unavailable after a Hermes environment rebuild removes `recall-sqlite`, mirrors replace/remove operations as new rows, admits orchestration wrappers, and can starve exact project memories behind general results. The repository also permits root/package source drift and tag/package version drift.

Recall's Hot/Warm/Cold tiers are working-set tiers, not a single prompt-capacity pool. v0.3.0 MUST NOT describe ordinary tiering or a finite Hot working set as “Recall full”.

## 2. Personas and goals

- **Hermes user:** install once, configure the embedding endpoint, and retain semantic memory across updates and sessions.
- **Operator:** diagnose dependency, embedding, DB, retrieval, and built-in prompt-layer health separately.
- **Contributor:** change one canonical source tree, run deterministic tests, and publish only version-consistent artifacts.
- **Upstream maintainer:** receive a provider that follows the current `MemoryProvider` lifecycle without private Hermes patches.

## 3. Functional requirements

### R1 — Layer separation and truthful status

1. WHEN status or documentation describes memory capacity, THE SYSTEM SHALL distinguish built-in prompt files from the Recall database.
2. THE SYSTEM SHALL describe Hot and Warm values as tier working sets, not hard total capacity.
3. WHEN Recall cannot initialize, THE SYSTEM SHALL report the dependency, configuration, embedding, or DB error that was observed; it SHALL NOT report “full” without measured capacity evidence.

### R2 — Dependency resilience

1. WHEN `recall-sqlite` is importable, THE PROVIDER SHALL initialize without invoking an installer.
2. WHEN `recall-sqlite` is absent and Hermes lazy installs are allowed, THE PROVIDER SHALL use `tools.lazy_deps.install_specs()` with allowlisted, pinned specifications and retry the import.
3. WHEN lazy installation is disabled, sealed without a durable target, rejected as unsafe, or otherwise fails, THE PROVIDER SHALL fail closed with an actionable error and manual recovery command.
4. `is_available()` SHALL perform no network request, package installation, or DB mutation.
5. `plugin.yaml` SHALL declare `pip_dependencies` for future generic Hermes support.

### R3 — Configuration correctness

1. WHEN Hermes loads the plugin through `register(ctx)`, THE PROVIDER SHALL consume `memory.recall-memory-hermes` from the active Hermes config.
2. Explicit constructor configuration SHALL override defaults.
3. An empty `db_path` SHALL resolve to `<active HERMES_HOME>/recall.db` during `initialize()`, not at module import time.
4. `embed_url` and `embed_model` SHALL configure the actual `recall.embed` module used for writes and retrieval before the first embedding call.
5. The provider SHALL accept an OpenAI-compatible base URL with or without a trailing slash and derive `/v1/embeddings` and `/v1/models` consistently.
6. `hermes memory setup recall-memory-hermes` SHALL expose and persist non-secret provider settings.
7. Embedding URLs containing inline username/password credentials SHALL be rejected without echoing the secret.
8. WHEN the live embedding endpoint or model changes, THE PROVIDER SHALL invalidate Recall's text-only embedding cache before reuse.

### R4 — Durable-memory admission policy

1. WHEN a user explicitly requests durable retention or states a durable correction/preference/decision, THE PROVIDER SHALL admit a bounded semantic card.
2. WHEN a turn is ordinary conversation without durable intent, THE PROVIDER SHALL not persist it.
3. WHEN content is a delegation completion, background-process notification, compaction wrapper, context-compaction handoff, or tool-output wrapper, THE PROVIDER SHALL reject it even if it contains generic marker words.
4. Non-primary agent contexts SHALL not write semantic turns or built-in mirrors.
5. Semantic cards SHALL retain bounded user and assistant evidence plus explicit `[PROJECT:*]` and `[TYPE:*]` metadata.
6. WHEN Hermes switches sessions without reinitializing the provider, fallback provenance SHALL use the new session ID.

### R5 — Project namespace isolation and ranking

1. THE PROVIDER SHALL infer stable namespaces for general, Hermes memory, Code Gaps, Podcast, Spirits Calling, job search, trading, VSkin, ComfyUI, and social publishing topics.
2. WHEN querying a project namespace, THE PROVIDER SHALL rank exact-project cards before general cards while preserving retrieval order within each bucket.
3. General cards SHALL only fill remaining result slots; cards from unrelated projects SHALL not leak into results.
4. Legacy untagged cards SHALL only match general queries.
5. Prefetch and explicit recall SHALL use the same ranking policy and a bounded candidate pool larger than the final `k`.
6. Empty or whitespace-only queries SHALL return no memory and SHALL NOT invoke retrieval.

### R6 — Built-in mirror CRUD semantics

1. `add` SHALL create at most one exact built-in mirror card for the target/content/session combination.
2. `replace` SHALL leave the replacement present exactly once and remove matching old built-in mirror card(s); if the replacement write fails, the old mirror SHALL remain intact.
3. `remove` SHALL remove matching built-in mirror card(s) and SHALL NOT add an empty or tombstone memory.
4. Mirror deletion SHALL be restricted to `[TYPE:builtin-memory]` or `[TYPE:builtin-user]`; it SHALL not delete independently captured decisions that merely contain similar text.
5. Missing `old_text` on a destructive action SHALL fail closed with a warning rather than deleting broadly.
6. The in-process memory count SHALL stay consistent after add/delete operations.
7. Exact target/content/session writes SHALL use a deterministic identity so concurrent provider instances converge on one SQLite row.

### R7 — Data safety, migration, and rollback

1. v0.3.0 SHALL require no automatic Recall schema migration.
2. Existing Recall DB files SHALL remain backward compatible with `recall-sqlite==0.2.0`.
3. Any optional cleanup tool SHALL default to dry-run, produce an archive/read-back, and require an explicit apply flag.
4. Release documentation SHALL include plugin rollback and DB rollback procedures.
5. Tests and examples SHALL use temporary DBs; repository and release artifacts SHALL contain no user DB, credentials, absolute private paths, or fixed private model workaround.
6. A configured absolute DB path SHALL be declared through `backup_paths()` without provider initialization or network access.
7. Cleanup apply SHALL reopen the DB and fail nonzero unless every archived episodic ID was deleted; archive and backup SHALL remain available on partial failure.

### R8 — Packaging and release integrity

1. `src/recall_memory_hermes/` SHALL be the canonical source.
2. Root plugin files required by Hermes Git installs SHALL be generated from canonical source and checked for byte parity in CI.
3. `pyproject.toml`, `plugin.yaml`, Git tag, wheel metadata, and GitHub release SHALL agree on `0.3.0`.
4. Generated `dist/`, `build/`, egg-info, caches, venvs, and DBs SHALL not be tracked.
5. Pull requests SHALL run tests on Windows and Linux using supported Python versions.
6. Tag publishing SHALL validate source parity, tests, tag/version consistency, wheel/sdist build, and `twine check` before trusted publishing.
7. The failed historical `v0.2.1` tag SHALL not be rewritten or reused.
8. The supported Hermes plugin installation surface SHALL be the Git repository. The PyPI wheel SHALL be described and tested as an importable Python library artifact, not as a Hermes-discoverable plugin installer.

### R9 — Observability and failure behavior

1. Initialization logs SHALL include DB path and row count but no memory contents or credentials.
2. Embedding health failure SHALL degrade retrieval to non-vector paths where supported and emit the actual configured endpoint/model in a redaction-safe warning.
3. Prefetch failures SHALL return no injected context and log a traceback; tool calls SHALL return an actionable error.
4. README SHALL not promise unverified fixed latency or unimplemented Honcho fallback.

## 4. Non-functional requirements

- **Security:** no shell execution for dependency specs; use Hermes allowlist enforcement.
- **Performance:** default final recall count remains five; candidate expansion is bounded.
- **Compatibility:** Python 3.10+ package metadata; CI covers 3.11 and 3.12 where wheels exist.
- **Determinism:** policy/ranking/CRUD/config/version tests use mocks or temp DBs and require no live embedding server.
- **Maintainability:** public helpers have docstrings; root/src drift is mechanically detected.

## 5. Acceptance gates

A v0.3.0 release is allowed only when all are true:

- Unit and integration tests pass in a clean project venv.
- Missing-dependency success and failure paths are tested.
- Constructor, Hermes config, active `HERMES_HOME`, and embedding-module configuration are tested.
- Add/replace/remove/idempotence and non-primary write suppression are tested.
- Golden namespace queries pass for every required namespace.
- Root/src parity, Git root-plugin load, tag/version consistency, clean wheel library install/import, wheel metadata, and `twine check` pass.
- Independent fresh-context reviewer returns no security concern or logic error.
- GitHub Actions for the release commit pass.
- GitHub release, tag, and PyPI artifact are read back after publication.

## 6. Out of scope

- Changing Recall Hot/Warm/Cold capacity algorithms.
- Changing the `recall-sqlite` database schema.
- Bundling Recall into Hermes core.
- Implementing Honcho fallback.
- Automatically deleting legacy or episodic memories during plugin startup.
- Publishing the separate Hermes upstream `pip_dependencies` integration PR as part of this repository release.
