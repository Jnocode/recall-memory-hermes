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

## 交付候選：adapter 0.3.1 ＋ core 0.2.1

本分支尚未發布 PyPI；版本更新不代表已切換任何 Hermes runtime。0.3.1 修正 standing-goal auto-resume、async-delegation 和 important-background wrappers 的准入，並保留 fetched 0.3.0 的功能。恢復本候選請明確安裝 core 0.2.1 wheel；dependency range 允許 legacy 0.2.0，但不能代替配對版本讀回。

### 既有 0.3.0 功能

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

最新版 Hermes setup 會讀取 manifest 的 `pip_dependencies`；provider 初始化也有相同安全自癒作為更新後 fallback。若 `security.allow_lazy_installs=false`，請在 Hermes 使用的 Python 環境手動安裝相容版本範圍（恢復候選仍應安裝保存的精確 wheel）：

```bash
python -m pip install "recall-sqlite>=0.2.0,<0.3" "httpx>=0.27,<1"
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

Adapter 不主動執行 MCP authority migration／episodic cleanup。Legacy core 啟動可補 tier columns，寫入超過 GC 水位可能觸發淘汰；不是「永遠不刪資料」。既有庫先做一致性 backup，在副本驗證可讀再回切。

Episodic cleanup 預設 dry-run，並在 DB 旁的 `recall-archives/` 先輸出 JSONL archive；真正刪除必須加 `--apply`，且會建立 SQLite backup。既有 archive/backup 不會被覆寫：

```bash
python scripts/compact_episodic.py --db /path/to/recall.db
python scripts/compact_episodic.py --db /path/to/recall.db --apply
```

## 保存配對版本與回切 Recall

1. 保留原 Recall DB 和一致性 backup，不上傳 GitHub。運行中用 SQLite backup API；只複製 `.db` 可能漏掉 WAL 的已提交資料。
2. 在新驗證 venv／資料副本建置配對 wheel，先 core 再 adapter：

```bash
python -m pip install build
python -m build --outdir ci-dist
# 在 core checkout 同樣 build，將其 wheel 複製到同一 artifacts 目錄。
python -m pip install /path/to/recall_sqlite-0.2.1-py3-none-any.whl /path/to/recall_memory_hermes-0.3.1-py3-none-any.whl
python -c "from importlib.metadata import version; print(version('recall-sqlite'), version('recall-memory-hermes'))"
```

Wheel 只安裝 Python package；Git plugin discovery 仍需 root `__init__.py`、`memory_policy.py`、`plugin.yaml`。`src/` 為 canonical，`scripts/sync_sources.py --check` 確保 root parity。

3. 實際回切時，在 Hermes 使用的 interpreter／approved lazy dependency target 安裝保存的精確 core wheel。不要用系統 Python 成功代替 Hermes runtime；只做 GitHub 更新時不要執行此步。
4. 確認 Git plugin 是審查過的來源版本後啟用／選定 provider：

```bash
hermes plugins enable recall-memory-hermes
hermes config set memory.provider recall-memory-hermes
hermes memory status
```

在 active profile 的 `memory.recall-memory-hermes.db_path` 指向保留的原庫；`hermes memory setup` 可管理設定，但不要留空後誤開新庫。空值預設初始化時的 `hermes_home/recall.db`；相對路徑以該 home 為根。CLI core 預設是另一個 `recall_p0.db`，查看同一庫必須設定 `RECALL_DB_PATH`。

5. 啟動**新 session／新程序**，再 `hermes memory status`，用 synthetic durable entry 執行寫入→跨 session retrieval 驗證。available 不等於實際召回成功。
6. 保留 Hindsight 或其他 provider 資料。切換設定不會自動同步另一系統期間的新記憶；不要刪除另一套資料。

只停用 plugin 不等於清除 provider selection；只有一個 external provider，可用 `memory.provider` 選擇目標。回復舊 adapter 前仍在資料副本驗證，不假定 schema downgrade 安全。

## Runtime／source 差異與已知限制

- 本候選基於 fetched 0.3.0，不把 legacy deployed plugin 整份覆蓋回去。舊 runtime 900/1800 user/assistant 卡片上限、100 candidates、120-char prefetch／200-char tool 顯示，候選沿用 0.3.0 的 1200/1600（截斷可附省略號）、bounded candidate multiplier、800/1000 顯示。
- 舊 runtime 的 built-in replace 是 delete-old-first；候選沿用 add-before-delete 並以 typed/body exact-match 限制刪除。**仍不是跨 add/delete 原子交易**；中斷可暫留兩筆。舊 untyped mirror 不會自動重寫／清理。
- Project 過濾是 heuristic 內容分類、候選取得後再過濾，不是授權 ACL，也不是 session hard isolation。`session_id` 主要用於來源與冪等 ID。
- Embedding 模組 globals 與 text cache 為進程共用；配置鎖不涵蓋整個 HTTP request，不能宣稱不同 profile 的同進程 embedding 完全隔離。
- 預設 Ollama endpoint 與舊 LM Studio endpoint 不同；回切時顯式保留自己既有的 embed URL/model。向量維度需與 DB 的 768 相符。
- Wrapper markers／durable markers 不是完整秘密偵測；不要把密碼、token 或私密工具輸出當記憶保存。
- [`SPEC.md`](SPEC.md) 是設計／契約文件。Adapter 不提供 OpenClaw runtime integration、MCP scope/CAS/soft delete 或跨裝置同步；這輪不把 mobile/server 雛形當 shipping feature。
- CI push `master`、`preserve/**`、PR／manual dispatch 驗證；tag `v*` 觸發 PyPI publish，未獨立授權不要 push tag。

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