# recall-memory-hermes v0.3.0 Design

**Requirements:** [`requirements.md`](requirements.md)
**Implementation tracker:** [`tasks.md`](tasks.md)

## 1. Design goals

v0.3.0 makes the provider deterministic at five boundaries: install, configuration, write admission, CRUD mirroring, and release. It does not change Recall's tiered-storage architecture or schema.

## 2. Current-state evidence

Verified on 2026-07-31:

- Remote baseline: `Jnocode/recall-memory-hermes@3a9947c`.
- PyPI latest: `0.2.0`; remote `v0.2.1` exists but its workflow failed because source metadata still said `0.2.0`.
- Baseline clean-vendored test invocation: 4 setup errors because pytest imports root `__init__.py` and no Hermes `agent` package exists in the isolated venv.
- Hermes current lifecycle calls `provider.is_available()` and then `provider.initialize(..., hermes_home=...)`; it does not inject provider config into the constructor.
- Hermes already exposes `tools.lazy_deps.install_specs()`, but generic user-memory-provider loading does not consume manifest `pip_dependencies`.
- `recall-sqlite==0.2.0` reads embedding constants at import time and `is_loaded()` hardcodes loopback; the plugin must configure module globals before use and perform its own endpoint health check.

## 3. Source and packaging architecture

```text
src/recall_memory_hermes/
├── __init__.py          # canonical provider implementation
└── memory_policy.py     # canonical policy/ranking helpers

scripts/sync_sources.py  # copies canonical files to root; --check for CI
├── → /__init__.py
└── → /memory_policy.py

plugin.yaml              # Git-plugin manifest + future pip_dependencies
pyproject.toml           # wheel metadata + test/build config
tests/                   # package, direct-plugin, policy, CRUD, release tests
```

The root files remain because Hermes Git installs load a plugin directory directly. They are generated artifacts checked into Git so a clone is immediately loadable. `plugin.yaml` declares `kind: exclusive`, so the generic `PluginManager` records but does not execute this provider with `PluginContext`; `plugins.memory.load_memory_provider()` discovers the user directory and calls `register()` with its dedicated collector context. CI rejects root/src drift and separately exercises import, collector registration, and exclusive routing.

Generated build products (`dist`, `build`, egg-info) are removed from version control and ignored.

## 4. Runtime architecture

```text
Hermes config.yaml
  memory.provider = recall-memory-hermes
  memory.recall-memory-hermes = {...}
             │
             ▼
register(ctx)
  ├─ load_config() safely
  ├─ extract provider subsection
  └─ RecallMemoryProvider(config)
             │
             ▼
is_available()  [pure: no network/install/DB write]
             │
             ▼
initialize(session_id, hermes_home, agent_context, ...)
  ├─ resolve profile-scoped DB path
  ├─ ensure dependencies through safe lazy-deps API
  ├─ configure recall.embed module constants
  ├─ open/create SQLiteStore
  ├─ record primary/non-primary write policy
  └─ probe configured /v1/models endpoint (warning-only)
```

### 4.1 Configuration precedence

1. Explicit constructor config (tests/advanced use).
2. `memory.recall-memory-hermes` loaded by `register()`.
3. Stable defaults:
   - `db_path`: `<active HERMES_HOME>/recall.db`
   - `embed_url`: `http://127.0.0.1:11434`
   - `embed_model`: `nomic-embed-text`
   - `candidate_multiplier`: `8`

URLs are normalized by stripping trailing `/` and a supplied `/v1/embeddings` suffix before deriving endpoint URLs. Inline URL credentials are rejected rather than persisted or logged.

### 4.2 Dependency state machine

```text
import recall succeeds ───────────────► READY
        │ fails
        ▼
can import tools.lazy_deps.install_specs?
        │ no ──► ERROR with exact manual command
        ▼ yes
install_specs(PINNED_SPECS)
        │ failed/rejected/sealed target missing
        └──────► ERROR with installer reason
        │ success
        ▼
invalidate_caches + retry import
        │ fails ──► ERROR (installation did not expose package)
        └──────► READY
```

Pinned specs:

- `recall-sqlite==0.2.0`
- `httpx>=0.27,<1`

No arbitrary user string reaches the installer.

### 4.3 Embedding configuration

After dependencies are available and before importing write/retrieval functions, the provider updates these `recall.embed` module values:

- `EMBED_BASE_URL`
- `EMBED_MODEL`
- `EMBED_PORT`
- `EMBED_URL`

The plugin's health probe uses `<embed_url>/v1/models`, not Recall's hardcoded loopback `is_loaded()`. Health failure does not delete data and does not claim DB failure. Updating the live endpoint/model clears Recall 0.2.0's text-only embedding cache under a process lock so vectors from a prior model are not reused.

## 5. Memory policy

### 5.1 Admission

Admission is fail-closed:

```text
empty → reject
system/delegation/background/compaction wrapper → reject
non-primary context → reject at provider boundary
explicit durable marker → admit
otherwise → reject
```

Broad topical words such as bare “規劃”, “架構”, “目標”, “優先”, `goal`, and `architecture` are not sufficient on their own. Explicit retention/correction/decision forms remain admitted.

### 5.2 Semantic card schema

Turn card:

```text
[PROJECT:<namespace>][TYPE:decision]
[USER]
<bounded user evidence>
[ASSISTANT]
<bounded assistant evidence>
```

Built-in mirror card:

```text
[PROJECT:<namespace>][TYPE:builtin-memory|builtin-user]
<bounded committed entry>
```

This is an application-level schema; the underlying SQLite schema is unchanged.

### 5.3 Project inference and ranking

`infer_project()` uses ordered, case-insensitive markers. Specific project markers precede generic Hermes/content markers.

`rank_project_candidates(candidates, project, k)`:

1. Preserve input order for exact namespace candidates.
2. Preserve input order for general candidates.
3. Return exact candidates first.
4. Fill remaining slots with general candidates.
5. Drop unrelated projects.
6. Treat untagged legacy content as general-only.

Both prefetch and explicit recall reject empty queries before retrieval, otherwise request a bounded pool of `max(k * candidate_multiplier, 40)` semantic candidates and apply this function.

## 6. Mirror CRUD algorithm

`on_memory_write(action, target, content, metadata)` runs only in the primary context.

Hermes session-switch callbacks update the cached fallback session ID. New cards use a deterministic SHA-256-derived identity over session ID and typed content; concurrent SQLite `INSERT OR REPLACE` operations therefore converge on one row even if both instances pass the compatibility scan.

- **add:** build typed card; scan semantic built-in mirrors for exact target/body/session; add only if absent.
- **replace:** require `metadata.old_text`; validate the replacement, ensure the new typed mirror exists, then delete exact old typed mirror(s). This add-before-delete order preserves the old mirror if a new write fails and leaves a retryable duplicate if old deletion fails.
- **remove:** require `metadata.old_text` (fallback to non-empty content only for backward compatibility); delete exact typed mirror(s); never add.
- **unknown action/target:** warn and no-op.

Deletion parses card metadata and compares the bounded body exactly. It cannot delete `[TYPE:decision]` cards.

The v0.3 implementation may scan a bounded set of semantic rows because built-in writes are low frequency. A future index can replace this without changing semantics.

## 7. Error handling and observability

| Failure | Behavior |
|---|---|
| Dependency missing + install disabled | Initialization fails with recovery command |
| Embedding endpoint unavailable | Warning; FTS/keyword paths remain available where Recall supports them |
| DB open/create fails | Initialization fails with path and exception type, no contents |
| Prefetch fails | Log traceback; inject empty string |
| Sync write fails | Log traceback; session response is not failed |
| Mirror destructive action lacks old text | Warning and no-op |
| Unknown tool | Stable error response |

No credentials, memory bodies, private absolute paths, or environment values appear in release artifacts/log fixtures.

## 8. Setup and persistence

The provider implements:

- `get_config_schema()` for `db_path`, `embed_url`, `embed_model`, and candidate multiplier.
- `save_config(values, hermes_home)` using Hermes config helpers to write `memory.recall-memory-hermes`.
- `register(ctx)` using the same config subsection.

This keeps setup and runtime on one source of truth.

## 9. Migration and rollback

### Migration

- No schema migration runs automatically.
- Existing DB opens in place with `recall-sqlite==0.2.0`.
- Existing semantic/episodic rows remain readable.
- Optional episodic compaction remains explicit archive-first + `--apply`.

### Rollback

1. Disable the provider or pin/install plugin v0.2.0.
2. Restore the previous plugin directory or reinstall from the prior tag.
3. Recall DB requires no rollback because v0.3 does not alter schema.
4. If an operator explicitly ran a cleanup script, restore its archive/DB backup separately.

Configured absolute Recall DB paths are returned by `backup_paths()` without initialization. Cleanup apply reopens SQLite after deletion and verifies every archived episodic ID is gone; partial failure raises while preserving both archive and pre-delete backup.

## 10. Verification strategy

### Unit tests

- Wrapper rejection and explicit durable admission.
- Namespace golden matrix and exact/general ranking.
- URL normalization and embedding-module configuration.
- Config load/save and profile-scoped DB path.
- Dependency already-present, lazy-install success, and fail-closed errors.
- Add/replace/remove/idempotence/non-primary suppression.

### Integration tests

- Load canonical wheel package without Hermes installed by injecting only the documented `MemoryProvider` test double.
- Load root Git plugin through a synthetic package namespace; this Git surface is the supported Hermes discovery/install path.
- Temp SQLite DB with mocked embedding vectors.
- Build wheel/sdist and install the wheel into a clean venv as a Python library artifact. The wheel is not claimed to register itself with Hermes plugin discovery.

### Release gates

- Source sync check.
- Version/tag check.
- Pytest on Windows/Linux and Python 3.11/3.12.
- Build and `twine check`.
- Independent cold diff review.
- GitHub Actions green, then GitHub/PyPI read-back.

## 11. Upstream follow-up

After v0.3.0 is released, a separate Hermes PR should connect memory-provider manifest `pip_dependencies` to the existing safe lazy dependency API. Discovery/listing must remain side-effect free; installation should occur only for the selected active provider. This follow-up is intentionally not coupled to the plugin release.
