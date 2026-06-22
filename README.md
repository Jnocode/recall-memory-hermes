# recall-memory-hermes

> Hermes Agent memory provider plugin for recall-memory (SAG-based retrieval).

## Installation

```bash
# Install recall-memory first
pip install recall-memory

# Install the Hermes plugin
hermes plugins install recall-memory-hermes

# Configure as memory provider
hermes memory setup
# → Select "recall" as provider
```

## Configuration

```yaml
# ~/.hermes/config.yaml
memory:
  provider: recall
  recall:
    db_path: "/path/to/recall_p0.db"      # default: auto-detect
    embed_url: "http://127.0.0.1:1234"    # LM Studio embed endpoint
    fallback_honcho: true                  # query Honcho if recall < 3 results
    fallback_honcho_url: "http://localhost:8082"
```

## Architecture

```
Hermes Agent → memory tool
                  ↓
        recall-memory-hermes (plugin)
                  ↓
        ┌─────────────────┬────────────────────┐
        ▼                 ▼                    ▼
    recall (SAG)    Honcho (fallback)    SQLite (cache)
    sqlite-vec       pgvector HNSW        FTS5
    1444 memories    1625 embeddings      local
```

## Development

```bash
# Clone
git clone https://github.com/Jnocode/recall-memory-hermes.git
cd recall-memory-hermes

# Install in dev mode
pip install -e .

# Install as Hermes plugin
hermes plugins install .
```
