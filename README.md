# recall-memory-hermes

> Hermes Agent memory provider plugin for recall-memory (SAG-based retrieval).

## Installation

```bash
# Install the core library
pip install recall-sqlite

# Install the Hermes plugin
hermes plugins install Jnocode/recall-memory-hermes

# Configure as memory provider
hermes config set memory.provider recall-memory-hermes

# Restart gateway to activate
hermes gateway restart
```

## Configuration

```yaml
# ~/.hermes/config.yaml
memory:
  provider: recall-memory-hermes
  recall-memory-hermes:
    db_path: "~/.hermes/recall.db"           # default: auto-detect
    embed_url: "http://127.0.0.1:1234"       # LM Studio embed endpoint
    fallback_honcho: false                    # query Honcho if recall < 3 results
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
