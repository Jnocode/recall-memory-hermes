# recall-memory-hermes v0.3.0 Tasks

**Requirements:** [`requirements.md`](requirements.md)
**Design:** [`design.md`](design.md)

Status legend: `[ ]` pending · `[>]` in progress · `[x]` complete · `[-]` intentionally deferred

## 0. Baseline and specification

- [x] 0.1 Clone `Jnocode/recall-memory-hermes` from `origin/master@3a9947c` into the canonical Workspace project path.
- [x] 0.2 Preserve an immutable baseline archive under `<workspace>/artifacts/recall-memory-hermes-v0.3/backups/`.
- [x] 0.3 Verify PyPI/GitHub versions and inspect the failed `v0.2.1` publish run.
- [x] 0.4 Run the clean baseline tests and record the observed 4 setup errors caused by root plugin collection without Hermes `agent` package.
- [x] 0.5 Write `requirements.md`, `design.md`, and this implementation tracker.

## 1. Repository and test foundation — R8

- [x] 1.1 Add `.gitignore` for venvs, caches, DBs, build output, dist, and egg-info.
- [x] 1.2 Remove tracked generated `dist/` and egg-info artifacts without rewriting history.
- [x] 1.3 Make `src/recall_memory_hermes/` canonical and add `scripts/sync_sources.py` with update/check modes.
- [x] 1.4 Configure pytest and direct-plugin import compatibility so clean tests no longer fail during root collection.
- [x] 1.5 Add dev dependencies and an Apache-2.0 `LICENSE` file.
- [x] 1.6 Add source-parity and direct Git-plugin load tests.

## 2. Write RED tests — R2–R6

- [x] 2.1 Add dependency bootstrap tests: already installed, lazy-install success, rejected/failed install, post-install import failure.
- [x] 2.2 Add configuration tests: constructor, `register()` active config, save_config, profile-scoped DB path.
- [x] 2.3 Add embedding route tests for base URL/model/port and trailing-path normalization.
- [x] 2.4 Expand policy tests for system/delegation/background/compaction rejection and durable intent acceptance.
- [x] 2.5 Add golden namespace and exact-before-general ranking tests.
- [x] 2.6 Add mirror CRUD/idempotence tests and decision-card deletion isolation.
- [x] 2.7 Add non-primary context write-suppression tests.
- [x] 2.8 Run tests and preserve the expected RED result (13 pass / 27 fail) before production implementation.

## 3. Implement runtime reliability — R2, R3, R9

- [x] 3.1 Implement side-effect-free `is_available()`.
- [x] 3.2 Implement safe `_ensure_runtime_dependencies()` using pinned specs and Hermes `install_specs()`.
- [x] 3.3 Resolve DB path from active `hermes_home` during initialization.
- [x] 3.4 Load active provider config in `register()` and implement setup schema/save_config.
- [x] 3.5 Normalize and apply embedding configuration to the actual `recall.embed` module.
- [x] 3.6 Replace hardcoded LM Studio health check with configured `/v1/models` probe.
- [x] 3.7 Emit actionable, redaction-safe failures and warnings.
- [x] 3.8 Add session-switch provenance, external DB backup declaration, embedding cache invalidation, and credential-URL rejection.

## 4. Implement memory quality — R4, R5, R6

- [x] 4.1 Add fail-closed wrapper/system-turn exclusions and narrow durable markers.
- [x] 4.2 Add all required project namespaces with specific-before-generic ordering.
- [x] 4.3 Implement exact-project-first candidate ranking shared by prefetch/tool recall.
- [x] 4.4 Add bounded candidate expansion and unrelated-project exclusion.
- [x] 4.5 Implement typed built-in mirror cards.
- [x] 4.6 Implement add/replace/remove semantics with exact mirror matching and idempotence.
- [x] 4.7 Suppress writes in non-primary contexts and maintain row-count state.
- [x] 4.8 Synchronize canonical source to root and make all RED tests GREEN.
- [x] 4.9 Add empty-query fail-closed behavior and deterministic cross-instance memory identities.

## 5. Data safety and documentation — R1, R7, R9

- [x] 5.1 Document built-in prompt memory vs Recall semantic store as independent layers.
- [x] 5.2 Remove unverified fixed-latency and unimplemented Honcho fallback claims.
- [x] 5.3 Update install/setup/verification instructions for dependency self-heal and explicit durable-memory test.
- [x] 5.4 Document no-schema-migration policy, optional cleanup safety, and rollback steps.
- [x] 5.5 Add `CHANGELOG.md` with v0.3.0 behavior and compatibility notes.
- [x] 5.6 Ensure repository fixtures/artifacts contain no DB, credential, private path, or fixed local workaround.
- [x] 5.7 Make cleanup reject missing DBs and verify every archived ID is absent after apply.

## 6. CI and release gates — R8

- [x] 6.1 Add pull-request CI for Windows/Linux and Python 3.11/3.12.
- [x] 6.2 Add `scripts/check_release.py` to validate tag, pyproject, plugin manifest, and package version.
- [x] 6.3 Harden publish workflow: sync check, tests, tag/version check, build, `twine check`, trusted publish.
- [x] 6.4 Set `pyproject.toml` and `plugin.yaml` to `0.3.0`; do not reuse `v0.2.1`.
- [x] 6.5 Build wheel/sdist and inspect metadata and contents.
- [x] 6.6 Install wheel in a fresh venv as a library artifact and separately load the root Git plugin surface.
- [x] 6.7 Document that Git is the Hermes plugin installation surface and PyPI is not a discovery bridge.
- [x] 6.8 Add retired-tag denylist and separate Git-plugin/wheel-library CI smoke gates.
- [x] 6.9 Verify Hermes memory-loader collector registration and explicit generic-loader exclusion.

## 7. Verification and release

- [x] 7.1 Run full pytest suite with `PYTHONPATH/PYTHONHOME/VIRTUAL_ENV` cleared (69 passed).
- [x] 7.2 Run source parity, AST/syntax, release consistency, build, twine, and clean-install gates.
- [x] 7.3 Run temporary-DB CRUD and namespace golden-query integration harness.
- [x] 7.4 Perform static secret/private-path scan on repository files and release artifacts (0 findings).
- [x] 7.5 Send diff + test evidence to an independent fresh-context reviewer; fix all blocking findings (`APPROVE FOR RELEASE`; no BLOCKER/HIGH/MEDIUM/LOW).
- [ ] 7.6 Commit verified changes on `feat/v0.3.0-reliability` and push branch.
- [ ] 7.7 Open and merge the repository PR only after GitHub Actions pass.
- [ ] 7.8 Tag `v0.3.0`, monitor trusted publishing, and correct failures without rewriting the tag.
- [ ] 7.9 Read back GitHub release, tag commit, PyPI `0.3.0`, wheel metadata, and clean install.
- [ ] 7.10 Record final evidence and remaining Hermes upstream PR as a separate follow-up.
