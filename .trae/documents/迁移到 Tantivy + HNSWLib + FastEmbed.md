## 目标
- 用 `Tantivy` 替换 Whoosh 文本检索，保持现有搜索接口与结果结构。
- 用 `HNSWLib` 替换 FAISS 向量索引，延续 ID 映射与增量更新逻辑。
- 用 `fastembed` 替换 sentence-transformers 嵌入，优先中文模型（bge-small-zh）。
- 不改变整体框架与 API；完成端到端验证与性能基线测试。

## 涉及文件
- `backend/core/index_manager.py`
- `backend/core/search_engine.py`
- `backend/core/rag_pipeline.py`
- `config.yaml`

## 实施步骤
### 1) Whoosh → Tantivy
- 移除 whoosh 相关导入与 `Schema`
- 建立 `Tantivy` schema：
  - `path`: text, `tokenizer_name='raw'`, `stored=True`
  - `filename`: text, `stored=True`
  - `content`: text, `stored=True`
  - `keywords`: text, `stored=True`
  - `file_type`: text, `stored=True`
  - `size`: integer, `stored=True`
  - `created`, `modified`: 可先存储为整数时间戳（避免日期类型不确定）
- 索引目录：从配置 `index.tantivy_path` 读取（默认 `./data/tantivy_index`），创建 `Index(schema, path=...)`
- 中文分词策略：
  - 预处理：用 `jieba` 将 `filename/content/keywords` 切词并用空格连接
  - 查询：同样对查询做分词再传入 `parse_query(query, ["filename","content","keywords"])`
- 写入：`with index.writer() as writer: writer.add_document({...}); writer.commit()`
- 删除：`writer.delete_term(Term(path_field, file_path))`
- 搜索：保持 `IndexManager.search_text(query, limit)` 接口，返回与当前结构一致的字典列表（含 `path/filename/score/...`）

### 2) FAISS → HNSWLib
- 导入并初始化：`hnswlib.Index(space='cosine', dim=vector_dim)`
- 构建：`init_index(max_elements=初始容量, ef_construction=200, M=16)`；根据文档数动态 `resize_index`
- 增加：`add_items(vectors, ids)`；删除：通过维护 `ids` 映射后重建或使用过滤策略（若删除频繁，走重建路径）
- 搜索：`knn_query(vector, k)` 返回 `(labels, distances)`，把 `cosine` 距离映射为相似度分数
- 持久化：`save_index(path)` / `load_index(path, max_elements=...)`
- 兼容原有 `vector_metadata.json`（保留 `next_id` 与 `path` 的映射）

### 3) sentence-transformers → fastembed
- 初始化：`from fastembed import TextEmbedding`; `TextEmbedding(model_name='bge-small-zh', cache_dir=可选)`
- 生成向量：`list(embedder.embed([text]))[0]`（float 列表 → `np.float32`）
- 统一维度：从模型元数据或配置读取 `vector_dim`
- 配置控制：`embedding.enabled` 开关；禁用时仅文本检索可用

### 4) 配置调整
- `config.yaml` 新增：
  - `index.tantivy_path`, `index.hnsw_path`
  - `embedding.model_name`, `embedding.cache_dir`, `embedding.enabled`
  - `search.text_weight`, `search.vector_weight`, `search.max_results`
- 保留旧键兼容（读取不到时给默认值）

### 5) 索引重建与保存
- `IndexManager.rebuild_index()` 改为清理 `tantivy_path/hnsw_path/metadata`
- `save_indexes()`：`tantivy` 无显式保存（commit 即落盘）；`HNSWLib` 调用 `save_index()`；元数据写入 JSON（含 `next_id`）

### 6) 搜索融合保持
- `SearchEngine._combine_results()` 保持现有融合逻辑与权重归一
- `filename` 额外加分与中文字符 Jaccard 加权逻辑保留

### 7) 端到端验证
- 运行后端 API：关键路由（搜索、预览、重建索引）
- 构建最小数据集：含中文/英文混合文档与长内容
- 测试项：
  - 纯文本检索（中文/英文、文件名关键词）
  - 纯向量检索（相似段落）
  - 混合检索（融合分数排序）
  - 删除/更新文档后的结果一致性
  - 性能基线：构建与查询延迟

## 中文优化
- 加载自定义词典（沿用 `data/custom_dict.txt`）
- 统一分词管线：索引与查询同策略，避免分词不一致
- 允许 `config.search.filename_boost/keyword_boost` 微调

## 回滚策略
- 保留旧索引路径；如验证失败，可切回 Whoosh/FAISS 的实现分支（代码留注解开关或 Git 分支）

## 验收标准
- 所有 API 与前端功能正常；文本/向量/融合检索返回结构与排序符合预期
- 在中文查询下的召回率与相关性不弱于旧实现
- 重建与增量更新稳定；索引持久化与加载可靠
- 性能：构建速度与查询延迟优于旧栈，资源占用降低
