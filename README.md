# recall-memory-hermes

[![CI](https://github.com/Jnocode/recall-memory-hermes/actions/workflows/ci.yml/badge.svg)](https://github.com/Jnocode/recall-memory-hermes/actions/workflows/ci.yml)
[![PyPI library package](https://img.shields.io/pypi/v/recall-memory-hermes)](https://pypi.org/project/recall-memory-hermes/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Hermes Agent 的本機 Recall 長期記憶 provider。Hermes plugin 透過 Git repository 安裝；PyPI wheel 是供 Python import／開發整合使用的 library artifact，不是 Hermes plugin installer。Provider 使用 `recall-sqlite` 的 sqlite-vec、FTS5、keyword retrieval 與 Hot/Warm/Cold tiering，並在 plugin 層加入 durable-write admission、project namespace、built-in memory CRUD mirror 與更新後 dependency 自癒。

## 記憶層模型

Hermes 有兩個獨立層，不能把它們混成同一個容量：

| 層 | 功能 | 是否每輪注入 | 容量意義 |
|---|---|---:|---|
| Built-in `MEMORY.md` / `USER.md` | 少量高價值規則與偏好 | 是 | 受 system prompt 預算影響 |
| Recall SQLite | 跨 session 語意檢索 | 否，只注入相關結果 | Hot/Warm/Cold 是 working-set tiers，不是總容量上限 |

因此「Hot tier 已達設定值」不等於 Recall 已滿。Provider 狀態會分別呈現 dependency、embedding endpoint 與 DB 問題，不會把它們統稱為容量故障。

## v0.3.0 重點

- 缺少 `recall-sqlite` 時，透過 Hermes `tools.lazy_deps.install_specs()` 安全自癒。
- `register(ctx)` 會讀取 `memory.recall-memory-hermes` 真實 runtime config。
- `embed_url` / `embed_model` 會套用到實際 `recall.embed` module。
- 普通聊天、delegation/background/compaction/tool wrappers 不寫入 durable store。
- Exact project memory 優先，general 只補位，其他 project 不外洩。
- Built-in `add/replace/remove` mirror 具 idempotence，不產生 tombstone 或空記憶。
- 非 primary agent context 不寫入。
- 同時相容 Hermes 0.19.0 與目前 0.19.x provider method names。

完整變更見 [`CHANGELOG.md`](CHANGELOG.md)，需求與設計見 [`.kiro/specs/v0.3.0-reliability/`](.kiro/specs/v0.3.0-reliability/)。

## 安裝

```bash
hermes plugins install Jnocode/recall-memory-hermes
hermes plugins enable recall-memory-hermes
hermes memory setup
```

Hermes 目前從 plugin 安裝目錄掃描 `plugin.yaml` 與 root adapter，因此正式 plugin 安裝面是上面的 GitHub `owner/repo`。單獨執行 `pip install recall-memory-hermes` 只會安裝 importable Python package，不會讓 `hermes plugins list` 自動發現 provider。

Hermes 0.19.x 會因 `kind: exclusive` 讓 generic `PluginManager` 只記錄、不以一般 `PluginContext` 執行本 provider。真正啟用由 `plugins.memory.load_memory_provider()` 完成：它掃描 `$HERMES_HOME/plugins/recall-memory-hermes`，再以專用 memory-provider collector 呼叫 `register()`。

最新版 Hermes setup 會讀取 manifest 的 `pip_dependencies`；provider 初始化也有相同安全自癒作為更新後 fallback。若 `security.allow_lazy_installs=false`，請在 Hermes 使用的 Python 環境手動安裝固定版本：

```bash
python -m pip install "recall-sqlite==0.2.0" "httpx>=0.27,<1"
```

## Embedding endpoint

預設使用 OpenAI-compatible base URL：

```text
http://127.0.0.1:11434
model: nomic-embed-text
```

Ollama 範例：

```bash
ollama pull nomic-embed-text
```

也可以使用 LM Studio 或其他 OpenAI-compatible endpoint；把 base URL 與 model ID 寫進 Hermes config：

```yaml
memory:
  provider: recall-memory-hermes
  recall-memory-hermes:
    db_path: ""
    embed_url: http://127.0.0.1:11434
    embed_model: nomic-embed-text
    candidate_multiplier: 8
```

空 `db_path` 會在初始化時解析為目前 active Hermes profile 的 `recall.db`，不會在 module import 時綁死預設 profile。

## Durable write policy

一般問答不會自動進長期記憶。建議使用明確 durable intent：

```text
記住：所有 Recall release 都要先完成 clean-install read-back。
重大決定：Spirits Calling 的核心是弱靈魂潛行探索。
偏好改成所有報告都使用繁體中文。
```

下列內容會 fail closed：

- delegation completion
- background process notification
- context compaction wrapper
- tool output wrapper
- 非 primary agent context

## Project namespaces

v0.3.0 內建：

- `hermes-memory`
- `codegaps`
- `podcast`
- `spirits-calling`
- `job-search`
- `trading`
- `vskin`
- `comfyui`
- `social-publishing`
- `general`

檢索時 exact project cards 保持原 retrieval 順序並優先回傳；general cards 只填剩餘名額；legacy untagged cards 只屬於 general。

## 驗證

```bash
hermes memory status
```

然後在 primary session 寫入一條明確記憶：

```text
記住：Recall v0.3 驗收代號是 cedar-17。
```

開新 session 後詢問：

```text
Recall v0.3 的驗收代號是什麼？
```

若 embedding endpoint 不可用，provider 會警告實際設定的 base/model；Recall 仍會使用可用的 FTS/keyword 路徑。實際延遲依 DB、query 與本機 endpoint 而定，本專案不承諾無測試條件的固定數值。

## 資料安全與 cleanup

v0.3.0 **不執行 SQLite schema migration，也不在 startup 自動刪資料**。既有 `recall-sqlite==0.2.0` DB 可直接開啟。

Episodic cleanup 預設 dry-run，並在 DB 旁的 `recall-archives/` 先輸出 JSONL archive；真正刪除必須加 `--apply`，且會建立 SQLite backup。既有 archive/backup 不會被覆寫：

```bash
python scripts/compact_episodic.py --db /path/to/recall.db
python scripts/compact_episodic.py --db /path/to/recall.db --apply
```

## Rollback

1. 停用 provider：`hermes plugins disable recall-memory-hermes`。
2. 重新安裝前一個已知版本，或 checkout 對應 tag。
3. v0.3 沒有 DB schema migration，因此單純 plugin rollback 不需改 DB。
4. 若曾執行 `compact_episodic.py --apply`，使用該次產生的 `.bak` SQLite backup 回復。

## Development

```bash
python -m pip install -e ".[dev]"
python scripts/sync_sources.py --check
python scripts/check_release.py
python -m pytest -q
python -m build
python -m twine check dist/*
```

Canonical source 位於 `src/recall_memory_hermes/`。修改後執行：

```bash
python scripts/sync_sources.py
```

CI 會拒絕 root Git-plugin source 與 canonical package source 不一致的 commit。

## License

Apache-2.0，見 [`LICENSE`](LICENSE)。