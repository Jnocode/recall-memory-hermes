# Recall Memory Hermes Plugin — Official Specification (SPEC.md)

> Version: 0.3.0 Ready
> Implementation Reference: `memory_policy.py`, `__init__.py`
> Conformance: kiro-spec-distillation & memory-architecture-v2

---

## 1. 插件架構與定位 (Architecture & Positioning)

`recall-memory-hermes` 是專為 Hermes / OpenClaw 生態系打造的語意記憶提供者（Memory Provider Plugin），底層掛載 `recall-sqlite` 單一權威資料庫。其核心任務為：在模型上下文、執行過程與長期記憶之間建立嚴格的過濾閘門，確保只有高價值持久決策能夠沉澱，並杜絕執行日誌污染向量空間。

---

## 2. 四大防護鐵律 (Four Core Defensive Invariants)

### 2.1 雜訊過濾網：`_BLOCKED_WRAPPERS` 阻擋機制
嚴格杜絕自動化工作流中的編程封裝、子代理交代、中繼日誌與工具輸出沉澱入庫。

- **攔截清單 (Blocked Markers)**：
  ```python
  _BLOCKED_WRAPPERS = (
      "[delegation complete",
      "[background process",
      "[context compaction",
      "[out-of-band user message",
      "[tool result",
      "[tool output",
      "<tool_result",
      "<tool_output",
      "subagent result",
      "delegation result",
      "reference only]",
  )
  ```
- **判定邏輯**：任何包含上述標記之 turn，`is_blocked_wrapper()` 立即返回 `True`，全面拒絕准入。
- **持久化觸發詞 (Durable Markers)**：
  僅當對話明確包含 `_DURABLE_MARKERS`（例如：「記住」、「重大決定」、「我的偏好」、「從現在起」、「禁止：」、「remember this」、「decision:」）時，才符合寫入資格 (`should_store_turn`)。

---

### 2.2 `[PROJECT:*][TYPE:*]` 專案命名空間語意隔離
為避免多專案並行開發時記憶混雜，所有入庫記憶卡片均由 `memory_policy.py` 強制規範化為標準雙標籤格式：

- **卡片結構規範**：
  ```text
  [PROJECT:{project}][TYPE:{type}]
  [USER]
  {bounded_user_content}
  [ASSISTANT]
  {bounded_assistant_content}
  ```
- **長度確定性截斷 (Deterministic Bounds)**：
  - User 內容長度上限：`MAX_USER_CHARS = 1200`
  - Assistant 內容長度上限：`MAX_ASSISTANT_CHARS = 1600`
  - 內建鏡像上限：`MAX_BUILTIN_CHARS = 2400`
- **專案推斷引擎 (`infer_project`)**：
  根據文字內容精準識別已知專案 slug（如 `hermes-memory`、`podcast`、`codegaps`、`spirits-calling`、`job-search`、`trading`、`vskin`、`comfyui`、`social-publishing`），未知內容歸入 `general`。
- **檢索權重隔離**：
  查詢時，`rank_project_candidates()` 保證「專案完全命中卡片」優先於「`general` 通用回退卡片」返回，嚴格過濾其他不相干專案記憶。

---

### 2.3 先增後刪（Add-before-Delete）安全 CRUD 鏡像
在同步修改既有內建記憶（`USER.md` / `MEMORY.md` 鏡像）時，嚴格恪守 Add-before-Delete 原則：

1. **先執行寫入 (Add/Upsert)**：先行將新版記憶卡片寫入 SQLite。若寫入中途失敗或崩潰，舊版卡片依然完整留存，不致發生資料空白。
2. **後執行刪除 (Delete Old)**：新卡片成功落盤後，再刪除具有相同主題之舊鏡像卡片。
3. **容錯恢復**：若刪除失敗，僅會殘留可被後續去重清理的暫態舊卡片，具備冪等重試安全性。

---

### 2.4 直通本地 LLM/Embedding 後端與快取隔離
記憶向量化完全依託本地私有算力，杜絕 API 憑證洩漏與外網依賴：

- **服務端點拓撲**：
  - 預設端點：`http://127.0.0.1:11434` (Ollama) 或相容之 `http://127.0.0.1:1234` (LM Studio)。
  - 標準嵌入模型：`nomic-embed-text`（輸出 768 維度，與 Core ANN 嚴格對齊）。
- **Base URL 正規化**：
  自動清洗尾綴 `/v1/embeddings` 或 `/v1/models`，保持統一底層連線。
- **快取與並發隔離**：
  嵌入配置受執行緒重入鎖 `_EMBED_CONFIG_LOCK` 保護，支援請求重試與快取防抖，確保高並發檢索不擊穿本地推論引擎。
