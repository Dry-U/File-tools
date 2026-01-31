# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Running the Application
```bash
python main.py
```
Opens browser automatically at http://127.0.0.1:8000 (auto-selects 8001-8010 if 8000 is occupied).

### Development Commands
```bash
# Install dependencies
uv sync
# or
pip install -e .

# Run all tests
pytest tests/

# Run specific test
pytest tests/test_file_scanner.py -v

# Performance tests
pytest tests/test_performance.py -v
```

### Building Executable (Windows)
```bash
pip install pyinstaller
pyinstaller file-tools.spec
# or use build script if exists:
./build_exe.bat
```

## Architecture Overview

This is a hybrid file retrieval and RAG (Retrieval-Augmented Generation) system with dual-engine search architecture:

### Dual-Engine Search
- **Text Search** (Tantivy - Rust-based): BM25 scoring with fields for exact matching, fuzzy search, and single-character Chinese search
- **Vector Search** (HNSWLib): Semantic similarity via embedding models (fastembed/bge-small-zh or modelscope)
- **Hybrid Scoring** (`backend/core/search_engine.py`): Normalizes and merges both scores with configurable weights (default 60% text, 40% vector), applies boost factors for filename matching (+15-95), keyword highlights (+20), hybrid results (+1.1x)

### Core Flow
```
main.py → FastAPI (api.py)
         ↓
    Startup → [IndexManager, SearchEngine, FileScanner, FileMonitor, RAGPipeline]
         ↓
    FileScanner.scan_and_index() → DocumentParser → IndexManager.add_document()
         ↓
    SearchEngine.search() → [search_text(), search_vector()] → _combine_results()
         ↓
    RAGPipeline.query() → SearchEngine → ModelManager.generate()
```

### Key Patterns

**ConfigLoader**: All components receive `ConfigLoader` instance; access config via `config_loader.get('section', 'key', default)` with type-safe methods `getboolean()`, `getint()`.

**Document Parsing Fallback Chain** (`backend/core/document_parser.py`):
- PDF: PyMuPDF → pdfplumber → pdfminer.six → PyPDF2 → textract
- Word: python-docx → win32com → textract
- Each parser enforces file size limits (10-100MB) to prevent memory issues

**Index Schema Evolution** (`backend/core/index_manager.py:229-248`):
- Schema version tracked in `data/metadata/schema_version.json`
- Auto-rebuild triggered when schema fields change
- Fields: `['path','filename','filename_chars','content','content_raw','content_chars','keywords','file_type','size','created','modified']`

**File Monitor Debouncing** (`backend/core/file_monitor.py`):
- Events buffered with 0.5s timeout using watchdog's Observer pattern
- Delegates to `file_scanner.index_file()` when available, otherwise falls back to minimal document construction

### Important Config Sections
- `file_scanner.scan_paths`: Semicolon-separated directories to index
- `monitor.enabled`: Auto-monitor file changes with watchdog
- `search.text_weight` / `search.vector_weight`: Hybrid search balance
- `embedding.provider`: `fastembed` or `modelscope`
- `ai_model.enabled`: Enable RAG chat
- `ai_model.interface_type`: `wsl` (Windows WSL) or `api` (OpenAI-compatible)

### RAG Pipeline Details (`backend/core/rag_pipeline.py`)
- Multi-stage document collection with VRAM-aware context sizing via `VRAMManager.adjust_context_size()`
- Document preprocessing: paragraph segmentation, keyword enhancement with `[QUERY_TERM]` markers
- Multidimensional relevance scoring: base (20%), keyword overlap (20%), filename match (50%)
- Semantic relevance using embedding model with cosine similarity; falls back to Jaccard
- Session history with timestamp-based expiry
- Thread-based generation timeout (configurable `request_timeout`)

### Global State
`backend/api/api.py` uses module-level globals for core components initialized in `@app.on_event("startup")`:
```python
search_engine = None
file_scanner = None
index_manager = None
rag_pipeline = None
file_monitor = None
```

### Windows-Specific Code
1. **DLL Loading** (`main.py:14-24`, `rag_pipeline.py:8-14`): Torch DLL path added to PATH using `os.add_dll_directory()`
2. **Drive Detection** (`file_monitor.py:65-111`): Uses ctypes to enumerate disk drives (A-Z) when no directories configured
3. **COM Integration** (`document_parser.py:358-381`): Uses win32com for legacy .doc parsing and Excel fallback

### Test Fixtures (`tests/conftest.py`)
- `temp_config`: ConfigLoader with temporary directories
- `mock_scanner`: FileScanner instance
- `mock_indexer`: SmartIndexer instance
- `mock_rag`: RAGPipeline with mocked model
- `generate_test_data`: Creates test directories with N text files

### Data Locations
- Tantivy index: `data/tantivy_index/`
- HNSW vector index: `data/hnsw_index/vector_index.bin`
- Vector metadata: `data/metadata/vector_metadata.json`
- Schema version: `data/metadata/schema_version.json`
- Logs: `data/logs/`
- Cache: `data/cache/`

### API Endpoints
- `GET /` - Main HTML page
- `GET /api/health` - Health check (`{"status": "healthy" | "starting"}`)
- `POST /api/search` - Search with query and optional filters
- `POST /api/chat` - RAG chat with optional session_id
- `POST /api/preview` - Preview file content
- `POST /api/rebuild-index` - Full index rebuild
- `/static/*` - Static files from `frontend/static/`
