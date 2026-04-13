#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false
import json
import logging
import os
import re
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Dict

import jieba
import numpy as np

from backend.core.text_chunker import TextChunker

# 常量定义
MAX_ENCODE_LENGTH = 2000  # 文本编码最大长度限制
MAX_CHUNKS_PER_DOC = 100  # 单个文档最大分块数量限制，防止内存溢出


class BatchModeContext:
    """批量操作上下文管理器，确保批量操作的原子性"""

    def __init__(self, index_manager, commit=True):
        self.index_manager = index_manager
        self.commit = commit
        self._entered = False

    def __enter__(self):
        self.index_manager.start_batch_mode()
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._entered:
            # 无论是否发生异常，都结束批量模式
            # 如果发生异常，不提交更改（回滚）
            should_commit = self.commit and (exc_type is None)
            self.index_manager.end_batch_mode(commit=should_commit)
        return False  # 不捕获异常，让异常继续传播


class IndexManager:
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)

        # Lazy import native modules to prevent SIGILL on incompatible CI runners
        import hnswlib as _hnswlib_mod
        import tantivy as _tantivy_mod

        self._tantivy = _tantivy_mod
        self._hnswlib = _hnswlib_mod

        # 初始化配置
        self._init_config()

        # 初始化嵌入模型（同步初始化，避免索引加载时模型未就绪）
        self.embedding_model = None
        self.vector_dim = 384
        self._embedding_lazy_loading_attempted = False

        # 先初始化嵌入模型，确保 _init_indexes() 时模型已就绪
        self._init_embedding_model()

        # 初始化索引（此时 embedding_model 已就绪）
        self._init_indexes()

        # 批量添加模式支持
        self._batch_mode = False
        self._batch_mode_start_time = None  # 追踪批量模式开始时间，用于超时检测
        self._batch_buffer = []
        self._batch_size = config_loader.getint("index", "batch_size", 100)
        self._batch_commit_interval = config_loader.getint(
            "index", "commit_interval", 30
        )  # 秒
        self._last_commit_time = time.time()
        self._batch_lock = threading.RLock()  # 使用可重入锁，允许在同一线程中多次获取
        self._index_lock = threading.RLock()  # 保护非批量模式的索引操作（可重入）
        self._writer = None
        self._BATCH_MODE_TIMEOUT = 120  # 批量模式超时时间（秒），超过此时间强制结束

        # Vector batch encoding buffer - 跨文档缓冲，批量编码提升 40-60% 速度
        self._vector_buffer = []  # [(text, metadata_dict), ...]
        self._vector_batch_size = config_loader.getint(
            "index", "vector_batch_size", 128
        )  # 从32提升到128，减少编码调用次数

        # 已删除文件路径集合（用于在搜索时过滤已删除的文档，因为HNSW不支持真正删除）
        self._deleted_paths = set()  # {file_path, ...}

        # 内容缓存（LRU），避免同一文件多次 I/O
        self._content_cache = {}  # {path: content}
        self._content_cache_order = []  # 记录访问顺序，用于 LRU 淘汰
        self._content_cache_max_size = 500  # 最大缓存文件数

    def _init_config(self) -> None:
        """初始化配置参数"""
        try:
            data_dir = self.config_loader.get("system", "data_dir", "./data")
            # 确保 data_dir 是字符串类型（防止 mock 对象传入）
            if not isinstance(data_dir, str):
                self.logger.warning(f"data_dir 类型错误: {type(data_dir)}, 使用默认值")
                data_dir = "./data"
            self.tantivy_index_path = self.config_loader.get(
                "index", "tantivy_path", f"{data_dir}/tantivy_index"
            )
            self.hnsw_index_path = self.config_loader.get(
                "index", "hnsw_path", f"{data_dir}/hnsw_index"
            )
            self.metadata_path = self.config_loader.get(
                "index", "metadata_path", f"{data_dir}/metadata"
            )
        except Exception as e:
            self.logger.error(f"配置读取失败: {str(e)}")
            self.tantivy_index_path = "./data/tantivy_index"
            self.hnsw_index_path = "./data/hnsw_index"
            self.metadata_path = "./data/metadata"

        os.makedirs(self.tantivy_index_path, exist_ok=True)
        os.makedirs(self.hnsw_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)

        try:
            custom_dict_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "custom_dict.txt"
            )
            if os.path.exists(custom_dict_path):
                jieba.load_userdict(custom_dict_path)
                self.logger.debug(f"加载自定义词典: {custom_dict_path}")
        except Exception as e:
            self.logger.warning(f"加载自定义词典失败: {str(e)}")

        self.embedding_provider = self.config_loader.get(
            "embedding", "provider", "fastembed"
        ).strip()  # 去除可能的前后空格，避免 YAML 解析问题

        # 分块配置
        self.chunk_enabled = self.config_loader.getboolean(
            "index", "chunk_enabled", True
        )
        self.chunk_strategy = self.config_loader.get(
            "index", "chunk_strategy", "semantic"
        )
        self.chunk_size = self.config_loader.getint("index", "chunk_size", 800)
        self.chunk_overlap = self.config_loader.getint("index", "chunk_overlap", 100)

        # 初始化分块器
        if self.chunk_enabled:
            self.chunker = TextChunker(
                strategy=self.chunk_strategy,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            self.logger.info(
                f"文本分块已启用: 策略={self.chunk_strategy}, 大小={self.chunk_size}"
            )
        else:
            self.chunker = None
            self.logger.info("文本分块已禁用")

    def _init_embedding_model(self) -> None:
        """初始化嵌入模型"""
        import sys

        model_enabled = self.config_loader.get("embedding", "enabled", False)
        self.logger.info(
            f"[INIT] _init_embedding_model called: "
            f"enabled={model_enabled}, provider='{self.embedding_provider}'"
        )
        sys.stdout.flush()

        if not model_enabled:
            self.logger.info("Embedding功能未启用")
            self.embedding_model = None
            self.vector_dim = 384
            return

        try:
            if self.embedding_provider == "modelscope":
                self._init_modelscope_embedding()
            else:
                self._init_fastembed_embedding()
        except ImportError as ie:
            import sys

            if "modelscope" in str(ie).lower():
                self.logger.warning(
                    f"ModelScope 未安装 (pip install modelscope)，语义搜索功能已禁用。"
                    f"如需语义搜索，可安装轻量级 fastembed: pip install fastembed"
                )
            elif "fastembed" in str(ie).lower():
                self.logger.warning(
                    f"FastEmbed 未安装 (pip install fastembed)，"
                    f"语义搜索功能已禁用。当前仅使用文本搜索 (BM25)。"
                    f"如需语义搜索，请安装: pip install fastembed"
                )
            else:
                self.logger.warning(
                    f"嵌入模型依赖未安装 ({str(ie)})，语义搜索已禁用。"
                    f"如需启用，请安装: pip install fastembed"
                )
            sys.stdout.flush()
            self.embedding_model = None
            self.vector_dim = 384
        except Exception as e:
            import sys

            self.logger.error(f"加载Embedding模型时发生未知错误: {str(e)}")
            sys.stdout.flush()
            self.embedding_model = None
            self.vector_dim = 384

    def _init_modelscope_embedding(self) -> None:
        """初始化ModelScope嵌入模型"""
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks

        model_name = self.config_loader.get(
            "embedding", "model_name", "iic/nlp_gte_sentence-embedding_chinese-base"
        ).strip()
        _cache_dir = self.config_loader.get("embedding", "cache_dir", None)
        cache_dir = _cache_dir.strip() if _cache_dir else None

        # 解析为绝对路径，确保无论 CWD 如何都能正确找到缓存
        if cache_dir:
            cache_dir = os.path.abspath(cache_dir)

        # 如果指定了本地路径，使用本地路径
        if cache_dir and os.path.exists(
            os.path.join(cache_dir, model_name.split("/")[-1])
        ):
            model_path = os.path.join(cache_dir, model_name.split("/")[-1])
            self.logger.info(f"使用本地模型路径: {model_path}")
            self.embedding_pipeline = pipeline(
                Tasks.sentence_embedding, model=model_path
            )
        else:
            self.embedding_pipeline = pipeline(
                Tasks.sentence_embedding, model=model_name
            )

        # ModelScope包装器类
        class ModelScopeWrapper:
            def __init__(self, pipeline):
                self.pipeline = pipeline

            def embed(self, texts):
                if isinstance(texts, list):
                    for text in texts:
                        try:
                            res = self.pipeline(input=text)
                        except TypeError:
                            res = self.pipeline(input={"source_sentence": [text]})

                        if "text_embedding" in res:
                            emb = res["text_embedding"]
                            if (
                                isinstance(emb, list)
                                and len(emb) > 0
                                and isinstance(emb[0], list)
                            ):
                                yield emb[0]
                            elif isinstance(emb, np.ndarray):
                                if getattr(emb, "ndim", 0) > 1:
                                    yield emb[0]
                                else:
                                    yield emb
                            else:
                                yield emb
                else:
                    try:
                        res = self.pipeline(input=texts)
                    except TypeError:
                        res = self.pipeline(input={"source_sentence": [texts]})

                    if "text_embedding" in res:
                        emb = res["text_embedding"]
                        if (
                            isinstance(emb, list)
                            and len(emb) > 0
                            and isinstance(emb[0], list)
                        ):
                            yield emb[0]
                        elif isinstance(emb, np.ndarray):
                            if getattr(emb, "ndim", 0) > 1:
                                yield emb[0]
                            else:
                                yield emb
                        else:
                            yield emb

        self.embedding_model = ModelScopeWrapper(self.embedding_pipeline)

        # 测试模型
        vec = next(iter(self.embedding_model.embed(["test"])))
        self.vector_dim = len(vec)
        self.logger.info(f"ModelScope Embedding模型加载成功，维度: {self.vector_dim}")

    def _init_fastembed_embedding(self) -> None:
        """初始化 FastEmbed 嵌入模型（轻量化方案）"""
        import os
        import sys

        # 设置 Hugging Face 国内镜像
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        self.logger.info("正在导入 FastEmbed 库...")
        sys.stdout.flush()

        from fastembed import TextEmbedding

        self.logger.info(f"FastEmbed 导入成功，开始加载模型...")
        sys.stdout.flush()

        model_name = self.config_loader.get(
            "embedding", "model_name", "BAAI/bge-small-zh-v1.5"
        ).strip()
        if not model_name:
            model_name = "BAAI/bge-small-zh-v1.5"

        _cache_dir = self.config_loader.get("embedding", "cache_dir", None)
        cache_dir = _cache_dir.strip() if _cache_dir else None

        # FastEmbed 包装类，适配现有接口
        class FastEmbedWrapper:
            def __init__(self, model):
                self.model = model

            def embed(self, texts):
                """返回嵌入向量生成器"""
                for embedding in self.model.embed(texts):
                    yield (
                        embedding.tolist()
                        if hasattr(embedding, "tolist")
                        else list(embedding)
                    )

        # 尝试创建模型实例
        try:
            self.logger.info(f"使用FastEmbed加载Embedding模型: {model_name}")

            # 检查模型是否存在
            if cache_dir:
                model_path = os.path.join(cache_dir, model_name.replace("/", "_"))
                if not os.path.exists(os.path.join(model_path, "config.json")):
                    self.logger.info(f"模型不存在，FastEmbed 将自动下载到: {cache_dir}")

            self.embedding_model = FastEmbedWrapper(
                TextEmbedding(model_name=model_name, cache_dir=cache_dir)
            )

            # 测试模型是否可以正常工作
            try:
                vec = next(iter(self.embedding_model.embed(["test"])))
                self.vector_dim = len(vec)
                self.logger.info(f"FastEmbed模型加载成功，维度: {self.vector_dim}")
                self._embedding_lazy_loaded = True
            except Exception as e:
                self.vector_dim = 384
                self.logger.warning(
                    f"Embedding模型测试失败，使用默认维度: {self.vector_dim}, "
                    f"错误: {str(e)}"
                )
                self.embedding_model = None
                self._embedding_lazy_loaded = False
        except ImportError as e:
            self.logger.error(
                f"FastEmbed未安装，请运行: uv add fastembed, 错误: {str(e)}"
            )
            self.embedding_model = None
            self.vector_dim = 384
            self._embedding_lazy_loaded = False
        except Exception as e:
            self.logger.error(f"Embedding模型创建失败，将禁用向量索引: {str(e)}")
            self.embedding_model = None
            self.vector_dim = 384
            self._embedding_lazy_loaded = False

    def _ensure_embedding_loaded(self) -> bool:
        """延迟加载Embedding模型（在首次使用时调用）"""
        if self.embedding_model is not None or getattr(
            self, "_embedding_lazy_loaded", False
        ):
            return True

        if not getattr(self, "_embedding_lazy_loading_attempted", False):
            self._embedding_lazy_loading_attempted = True
            self.logger.info("尝试延迟加载Embedding模型...")
            try:
                self._init_fastembed_embedding()
                return self.embedding_model is not None
            except Exception as e:
                self.logger.error(f"延迟加载Embedding模型失败: {e}")
                return False
        return False

    def _init_indexes(self) -> None:
        """初始化所有索引"""
        self._init_tantivy_index()
        self._init_hnsw_index()
        self.index_ready = self.is_index_ready()
        try:
            self._ensure_schema_version()
        except Exception as e:
            self.logger.warning(f"检查索引模式版本失败: {str(e)}")

    def _init_tantivy_index(self):
        schema_builder = self._tantivy.SchemaBuilder()
        self.t_path = schema_builder.add_text_field(
            "path", stored=True, tokenizer_name="raw"
        )
        self.t_filename = schema_builder.add_text_field("filename", stored=True)
        self.t_filename_chars = schema_builder.add_text_field(
            "filename_chars", stored=True
        )
        self.t_content = schema_builder.add_text_field("content", stored=True)
        self.t_content_raw = schema_builder.add_text_field(
            "content_raw", stored=True, tokenizer_name="raw"
        )
        self.t_content_chars = schema_builder.add_text_field(
            "content_chars", stored=True
        )
        self.t_keywords = schema_builder.add_text_field("keywords", stored=True)
        self.t_file_type = schema_builder.add_text_field("file_type", stored=True)
        self.t_size = schema_builder.add_integer_field("size", stored=True)
        self.t_created = schema_builder.add_integer_field("created", stored=True)
        self.t_modified = schema_builder.add_integer_field("modified", stored=True)
        self.schema = schema_builder.build()
        try:
            # 检查索引路径是否存在，如果不存在，则创建
            if not os.path.exists(self.tantivy_index_path):
                os.makedirs(self.tantivy_index_path, exist_ok=True)
                self.tantivy_index = self._tantivy.Index(
                    self.schema, path=self.tantivy_index_path
                )
            else:
                self.tantivy_index = self._tantivy.Index(
                    self.schema, path=self.tantivy_index_path
                )
        except Exception as e:
            self.logger.error(f"初始化Tantivy索引失败: {str(e)}")
            # 如果指定路径失败，尝试在内存中创建新索引，但仍尝试重新创建文件目录
            try:
                os.makedirs(self.tantivy_index_path, exist_ok=True)
                self.tantivy_index = self._tantivy.Index(
                    self.schema, path=self.tantivy_index_path
                )
            except Exception as e2:
                self.logger.error(f"创建索引目录或初始化索引失败: {str(e2)}")
                self.tantivy_index = self._tantivy.Index(self.schema)

    def _init_hnsw_index(self):
        """初始化HNSW向量索引"""
        # 确保向量索引和元数据目录存在
        os.makedirs(self.hnsw_index_path, exist_ok=True)
        os.makedirs(self.metadata_path, exist_ok=True)

        index_file = os.path.join(self.hnsw_index_path, "vector_index.bin")
        metadata_file = os.path.join(self.metadata_path, "vector_metadata.json")

        if os.path.exists(index_file) and os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata_dict = json.load(f)
                    self.vector_metadata = metadata_dict.get("metadata", {})
                    self.next_id = metadata_dict.get(
                        "next_id", len(self.vector_metadata)
                    )

                # 检查向量维度是否匹配
                if self.embedding_model:
                    stored_dim = metadata_dict.get("vector_dim", self.vector_dim)
                    if stored_dim != self.vector_dim:
                        self.logger.error(
                            f"向量维度不匹配: 索引={stored_dim}, "
                            f"模型={self.vector_dim}，重建索引"
                        )
                        self._create_new_hnsw_index()
                        return
                    self.hnsw = self._hnswlib.Index(space="cosine", dim=self.vector_dim)
                    # 预分配 50000 容量，减少 resize 次数
                    max_elements = max(self.next_id + 50000, 50000)
                    self.hnsw.load_index(index_file, max_elements=max_elements)
                    self.logger.info(
                        f"成功加载向量索引，维度: {self.vector_dim}, "
                        f"元素数: {self.next_id}"
                    )
                else:
                    self.logger.warning("向量索引已存在但嵌入模型未启用，跳过加载")
                    self._create_new_hnsw_index()
            except Exception as e:
                self.logger.error(f"加载现有向量索引失败: {str(e)}")
                self._create_new_hnsw_index()
        else:
            self.logger.info(f"向量索引文件不存在，创建新索引: {index_file}")
            self._create_new_hnsw_index()

    def _create_new_hnsw_index(self):
        try:
            self.hnsw = self._hnswlib.Index(space="cosine", dim=self.vector_dim)
            # 从1024提升到50000，减少resize次数，提升性能
            self.hnsw.init_index(max_elements=50000, ef_construction=200, M=16)
            self.hnsw.set_ef(200)
            self.vector_metadata = {}
            self.next_id = 0
        except Exception as e:
            self.logger.error(f"创建HNSW索引失败: {str(e)}")
            self.hnsw = None
            self.vector_metadata = {}
            self.next_id = 0

    def _ensure_schema_version(self):
        """检查并确保索引模式版本兼容

        检测以下情况并触发重建：
        1. Tantivy字段变化
        2. 分块配置变更（从未分块到分块）
        3. 向量元数据格式不兼容
        """
        expected_fields = [
            "path",
            "filename",
            "filename_chars",
            "content",
            "content_raw",
            "content_chars",
            "keywords",
            "file_type",
            "size",
            "created",
            "modified",
        ]
        version_file = os.path.join(self.metadata_path, "schema_version.json")
        current = {}
        try:
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    current = json.load(f)
        except Exception:
            current = {}

        current_fields = current.get("fields", [])
        current_chunk_version = current.get("chunk_version", 0)
        current_chunk_enabled = current.get("chunk_enabled", False)

        # 检查是否需要重建
        needs_rebuild = False
        rebuild_reason = []

        # 1. 字段变化
        if current_fields != expected_fields:
            needs_rebuild = True
            rebuild_reason.append("字段变化")

        # 2. 分块配置变更（从非分块切换到分块模式）
        if self.chunk_enabled and not current_chunk_enabled:
            # 检查是否存在旧版向量数据（非分块格式）
            if self._has_legacy_vector_format():
                needs_rebuild = True
                rebuild_reason.append("启用分块存储")

        # 3. 向量元数据版本不匹配
        if current_chunk_version < 1 and self.chunk_enabled:
            if self._has_legacy_vector_format():
                needs_rebuild = True
                rebuild_reason.append("分块版本升级")

        if needs_rebuild:
            try:
                self.logger.info(
                    f"检测到{', '.join(rebuild_reason)}，重建索引以支持新功能"
                )
                self.rebuild_index()

                # 更新版本文件
                version_data = {
                    "fields": expected_fields,
                    "chunk_version": 1,
                    "chunk_enabled": self.chunk_enabled,
                    "rebuild_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(version_file, "w", encoding="utf-8") as f:
                    json.dump(version_data, f, ensure_ascii=False, indent=2)
                self.logger.info("索引重建完成，版本文件已更新")
            except Exception as e:
                self.logger.error(f"更新索引模式失败: {str(e)}")
        else:
            # 只需更新版本文件中的配置状态
            try:
                version_data = {
                    "fields": expected_fields,
                    "chunk_version": current_chunk_version or 1,
                    "chunk_enabled": self.chunk_enabled,
                    "last_check": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(version_file, "w", encoding="utf-8") as f:
                    json.dump(version_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.debug(f"更新版本文件失败: {e}")

    def _has_legacy_vector_format(self):
        """检查是否存在旧版非分块向量数据

        Returns:
            True if legacy format detected (no 'is_chunk' field in metadata)
        """
        if not self.vector_metadata:
            return False

        # 检查前几条向量元数据
        sample_size = min(10, len(self.vector_metadata))
        for i, (doc_id, metadata) in enumerate(self.vector_metadata.items()):
            if i >= sample_size:
                break
            if isinstance(metadata, dict):
                # 如果存在没有 is_chunk 标记的文档，说明是旧格式
                if "is_chunk" not in metadata:
                    return True
        return False

    def _segment(self, text):
        try:
            tokens = jieba.lcut_for_search(text or "")
            return " ".join([t for t in tokens if t.strip()])
        except Exception as e:
            self.logger.debug(f"分词失败: {str(e)}")
            return text or ""

    def start_batch_mode(self):
        """启动批量添加模式"""
        with self._batch_lock:
            if self._batch_mode:
                return
            self._batch_mode = True
            self._batch_mode_start_time = time.time()
            self._batch_buffer = []
            self._writer = self.tantivy_index.writer()
            self._last_commit_time = time.time()
            # 启动后台定期commit线程
            self._start_commit_thread()
            self.logger.info("启动批量添加模式")

    def _start_commit_thread(self):
        """启动后台定期commit线程，防止锁被长期持有"""
        if getattr(self, "_commit_thread_running", False):
            return

        self._commit_thread_running = True
        self._commit_thread_stop = threading.Event()

        def commit_worker():
            """后台线程：定期commit以释放writer锁"""
            self.logger.info("[COMMIT_THREAD] 后台commit线程已启动")
            commit_count = 0
            while not self._commit_thread_stop.is_set():
                # 等待10秒或直到被唤醒
                result = self._commit_thread_stop.wait(timeout=10)
                if result:  # stop event被设置
                    self.logger.info("[COMMIT_THREAD] 收到停止信号，退出线程")
                    break

                # 检查是否应该commit
                try:
                    with self._batch_lock:
                        if not self._batch_mode:
                            self.logger.info("[COMMIT_THREAD] 批量模式已关闭，退出线程")
                            break
                        if self._writer is None:
                            self.logger.warning(
                                "[COMMIT_THREAD] Writer为None，跳过commit"
                            )
                            continue

                        elapsed = time.time() - self._last_commit_time
                        buffer_size = len(self._batch_buffer)
                        self.logger.info(
                            f"[COMMIT_THREAD] 检查commit: "
                            f"elapsed={elapsed:.1f}s, buffer={buffer_size}"
                        )

                        # 行业最佳实践：基于文档数量 + 时间双重触发
                        # 每5秒 或 缓冲区超过500文档 触发commit
                        memory_pressure = buffer_size > 1000
                        should_commit = (
                            elapsed >= 5 or buffer_size >= 500 or memory_pressure
                        )

                        if should_commit:
                            try:
                                # 处理缓冲区中的文档
                                docs_to_process = list(self._batch_buffer)
                                if docs_to_process:
                                    self.logger.info(
                                        f"[COMMIT_THREAD] 开始提交 "
                                        f"{len(docs_to_process)} 个文档"
                                    )
                                    t_commit_start = time.time()
                                    for doc in docs_to_process:
                                        self._add_doc_to_writer(doc)
                                    elapsed_add = time.time() - t_commit_start
                                    self.logger.info(
                                        f"[COMMIT_THREAD] 添加文档到writer完成，"
                                        f"耗时 {elapsed_add:.3f}s"
                                    )
                                    self._batch_buffer = []

                                t_writer_commit = time.time()
                                elapsed_since = t_writer_commit - elapsed
                                self.logger.info(
                                    f"[COMMIT_THREAD] 开始writer.commit() "
                                    f"(累计 {elapsed_since:.3f}s from last commit)"
                                )
                                self._writer.commit()
                                t_commit_done = time.time()
                                self._last_commit_time = t_commit_done
                                commit_count += 1
                                commit_time = t_commit_done - t_writer_commit
                                self.logger.info(
                                    f"[COMMIT_THREAD] Commit #{commit_count} 完成，"
                                    f"writer.commit()耗时 {commit_time:.3f}s"
                                )
                            except Exception as e:
                                self.logger.error(
                                    f"[COMMIT_THREAD] 后台commit失败: {e}"
                                )
                        else:
                            self.logger.info(
                                f"[COMMIT_THREAD] 跳过commit: "
                                f"elapsed={elapsed:.1f}s < 10s, "
                                f"buffer={buffer_size} < 50"
                            )
                except Exception as e:
                    self.logger.error(f"[COMMIT_THREAD] Commit循环异常: {e}")

            self.logger.info(f"[COMMIT_THREAD] 线程退出，完成 {commit_count} 次commit")
            self._commit_thread_running = False

        self._commit_thread = threading.Thread(
            target=commit_worker, daemon=True, name="TantivyCommitThread"
        )
        self._commit_thread.start()
        self.logger.info("[COMMIT_THREAD] 后台commit线程已启动")

    def commit_batch(self):
        """提交批量添加的文档"""
        with self._batch_lock:
            if not self._batch_mode:
                return False

            try:
                if self._writer:
                    self._writer.commit()
                    self._last_commit_time = time.time()
                    self.logger.info("批量提交完成")
                    return True
            except Exception as e:
                self.logger.error(f"批量提交失败: {e}")
            return False

    def end_batch_mode(self, commit=True):
        """结束批量添加模式"""
        self.logger.info(f"[BATCH] end_batch_mode 开始，commit={commit}")

        # 先停止后台commit线程
        self._stop_commit_thread()

        # 使用单个锁区域避免 TOCTOU 竞态
        with self._batch_lock:
            if not self._batch_mode:
                self.logger.info("[BATCH] 批量模式未激活，直接返回")
                return

            # 检查是否超时
            elapsed = time.time() - (self._batch_mode_start_time or time.time())
            self.logger.info(f"[BATCH] 批量模式已运行 {elapsed:.1f} 秒")
            if elapsed > self._BATCH_MODE_TIMEOUT:
                self.logger.warning(
                    f"[BATCH] 批量模式超时（已运行 {elapsed:.1f} 秒），强制结束"
                )

            try:
                # 先处理缓冲区中剩余的文档
                buffer_size = len(self._batch_buffer)
                self.logger.info(f"[BATCH] 处理剩余 {buffer_size} 个文档")
                if self._batch_buffer:
                    for doc in self._batch_buffer:
                        self._add_doc_to_writer(doc)
                    self._batch_buffer = []

                # 检查向量缓冲区大小
                vector_buffer_size = len(getattr(self, "_vector_buffer", []))
                self.logger.info(f"[BATCH] 向量缓冲区大小: {vector_buffer_size}")

                # 确保 writer 被正确释放
                if self._writer is not None:
                    try:
                        if commit:
                            self.logger.info("[BATCH] 执行最终commit")
                            self._writer.commit()
                            self.logger.info("[BATCH] 执行save_indexes")
                            self.save_indexes()
                        # 释放 writer
                        self._writer = None
                        self.logger.info("[BATCH] Writer已释放")
                    except Exception as e:
                        self.logger.warning(f"[BATCH] 释放 writer 时出错: {e}")
                        self._writer = None

                self._batch_mode = False
                self._batch_mode_start_time = None
                self.logger.info("[BATCH] 批量添加模式已结束")

                # 在锁内刷新向量缓冲区（向量缓冲区刷新是线程安全的）
                if vector_buffer_size > 0:
                    self.logger.info("[BATCH] 刷新向量缓冲区...")
                    try:
                        self._flush_vector_buffer()
                        self.logger.info("[BATCH] 向量缓冲区刷新完成")
                    except Exception as e:
                        self.logger.error(f"[BATCH] 刷新向量缓冲区失败: {e}")

            except Exception as e:
                self.logger.error(f"[BATCH] 结束批量模式时出错: {e}")
                # 即使出错，也要强制重置状态
                self._writer = None
                self._batch_mode = False
                self._batch_mode_start_time = None

    def _force_reset_batch_mode(self):
        """强制重置批量模式状态（用于打破死锁）

        注意：这是紧急修复手段，只在批量模式卡住且无法正常结束 时使用。
        调用此方法会立即终止批量模式，不保证之前缓冲的数据被提交。
        """
        self.logger.warning("[BATCH_FORCE] 强制重置批量模式状态")
        # 停止 commit 线程
        self._stop_commit_thread()
        # 强制重置状态
        self._writer = None
        self._batch_mode = False
        self._batch_mode_start_time = None
        self._batch_buffer = []
        self.logger.warning("[BATCH_FORCE] 批量模式已强制重置")

    def _stop_commit_thread(self):
        """停止后台commit线程"""
        if getattr(self, "_commit_thread_running", False):
            self.logger.info("[COMMIT_THREAD] 正在停止后台commit线程...")
            self._commit_thread_stop.set()
            self._commit_thread_running = False
            # 等待线程真正退出
            if hasattr(self, "_commit_thread") and self._commit_thread.is_alive():
                self._commit_thread.join(timeout=2)
            self.logger.info("[COMMIT_THREAD] 后台commit线程已停止")
        else:
            self.logger.info("[COMMIT_THREAD] 后台commit线程未运行")

    def batch_mode(self, commit=True):
        """
        批量操作上下文管理器

        使用示例:
            with index_manager.batch_mode():
                for doc in documents:
                    index_manager.add_document(doc)

        Args:
            commit: 是否提交更改，如果为False则回滚

        Returns:
            BatchModeContext 上下文管理器
        """
        return BatchModeContext(self, commit=commit)

    def _add_doc_to_writer(self, document):
        """将文档添加到 writer"""
        # 确保 writer 有效
        if self._writer is None:
            self._writer = self.tantivy_index.writer()
            buffer_size = (
                len(self._batch_buffer) if hasattr(self, "_batch_buffer") else 0
            )
            self.logger.info(
                f"[_ADD_DOC_WRITER] 创建新Writer，缓冲区大小={buffer_size}"
            )

        seg_filename = self._segment(document["filename"])
        seg_content = self._segment(document["content"])
        seg_keywords = self._segment(document.get("keywords", ""))
        fname_chars = " ".join([c for c in document["filename"]])
        raw_text = str(document.get("content") or "")
        # 限制 content_chars 长度，避免大文件生成过大的索引条目
        content_chars_source = raw_text[:50000]
        content_chars = " ".join([c for c in content_chars_source])

        tdoc = self._tantivy.Document(
            path=document["path"],
            filename=[seg_filename],
            filename_chars=[fname_chars],
            content=[seg_content],
            content_raw=[raw_text],
            content_chars=[content_chars],
            file_type=[document["file_type"]],
            size=int(document["size"]),
            created=(
                int(time.mktime(document["created"].timetuple()))
                if isinstance(document.get("created"), datetime)
                else int(document["created"])
                if document.get("created") is not None
                else 0
            ),
            modified=(
                int(time.mktime(document["modified"].timetuple()))
                if isinstance(document.get("modified"), datetime)
                else int(document["modified"])
                if document.get("modified") is not None
                else 0
            ),
            keywords=[seg_keywords],
        )
        self._writer.add_document(tdoc)

    def add_document(self, document):
        """添加文档到索引，支持批量模式"""
        if not getattr(self, "tantivy_index", None):
            return False

        try:
            # 批量模式处理：只追加到缓冲区，由后台线程统一提交
            # 注意：刷新在锁外进行，避免三层嵌套锁导致的潜在死锁风险
            if self._batch_mode:
                with self._batch_lock:
                    self._batch_buffer.append(document)
                    # 批量处理向量索引（不再触发刷新，避免嵌套锁）
                    self._add_vector_in_batch_mode(document)
                # 锁外检查是否需要刷新缓冲区
                # 使用 try_lock 避免与其他线程冲突
                try:
                    if len(self._vector_buffer) >= self._vector_batch_size:
                        self._flush_vector_buffer()
                except Exception as flush_err:
                    self.logger.debug(f"后台刷新失败（不影响主流程）: {flush_err}")
                return True

            # 非批量模式：直接提交
            with self._index_lock:
                self._add_doc_to_writer(document)

                # 非批量模式下的向量索引处理
                if self.embedding_model and self.hnsw is not None:
                    if self.chunk_enabled and self.chunker:
                        self._add_document_chunks(document)
                    else:
                        self._add_document_single(document)

                return True

        except Exception as e:
            self.logger.error(f"添加文档失败 {document.get('path', '')}: {e}")
            return False

    def batch_add_documents(self, documents: list) -> int:
        """批量添加文档（行业最佳实践：批量API + 内存预算）

        Args:
            documents: 文档列表，每个文档为字典

        Returns:
            成功添加的文档数量
        """
        if not documents:
            return 0

        if not getattr(self, "tantivy_index", None):
            self.logger.warning("Tantivy索引未初始化，跳过批量添加")
            return 0

        success_count = 0

        try:
            # 批量模式处理
            if self._batch_mode:
                with self._batch_lock:
                    # 批量模式：直接追加到缓冲区
                    self._batch_buffer.extend(documents)
                    buffer_size = len(self._batch_buffer)

                    # 检查是否需要触发commit（基于文档数量）
                    if buffer_size >= 1000:
                        self.logger.info(
                            f"[BATCH_ADD] 缓冲区达到 {buffer_size} 文档，触发后台commit"
                        )

                    # 批量处理向量索引（不再触发刷新，避免嵌套锁）
                    for doc in documents:
                        self._add_vector_in_batch_mode(doc)

                # 锁外检查并刷新向量缓冲区，避免三层嵌套锁
                try:
                    if len(self._vector_buffer) >= self._vector_batch_size:
                        self._flush_vector_buffer()
                except Exception as flush_err:
                    self.logger.debug(f"批量刷新失败（不影响主流程）: {flush_err}")

                return len(documents)

            # 非批量模式：使用批量API
            with self._index_lock:
                for document in documents:
                    try:
                        self._add_doc_to_writer(document)
                        success_count += 1
                    except Exception as e:
                        self.logger.error(
                            f"批量添加文档失败 {document.get('path', '')}: {e}"
                        )

                if success_count > 0 and len(documents) > 100:
                    self.logger.info(
                        f"[BATCH_ADD] 批量添加 {success_count}/{len(documents)} 个文档"
                    )

                return success_count

        except Exception as e:
            self.logger.error(f"批量添加文档失败: {e}")
            return success_count

    def _add_vector_in_batch_mode(self, document):
        """批量模式下延迟添加向量索引"""
        if not self.embedding_model or self.hnsw is None:
            return True

        try:
            if self.chunk_enabled and self.chunker:
                return self._add_document_chunks_batch(document)
            else:
                return self._add_document_single_batch(document)

        except Exception as e:
            self.logger.error(
                f"批量模式添加向量索引失败 {document.get('path', '')}: {str(e)}"
            )
            return False

    def _add_document_single_batch(self, document):
        """批量模式：缓冲单文档向量到批量编码队列

        注意：此方法只负责将文档追加到缓冲区，不触发刷新。
        刷新由 add_document 在锁外调用 _flush_vector_buffer 处理。
        """
        content_to_encode = (
            document["content"][:MAX_ENCODE_LENGTH] if document["content"] else ""
        )
        if not content_to_encode.strip():
            return True

        metadata = {
            "path": document["path"],
            "filename": document["filename"],
            "file_type": document["file_type"],
            "modified": (
                document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(document["modified"], datetime)
                else str(document["modified"])
            ),
            "is_chunk": False,
            "chunk_index": 0,
            "total_chunks": 1,
        }

        with self._batch_lock:
            self._vector_buffer.append((content_to_encode, metadata))
            # 不再在此触发刷新，避免三层嵌套锁
            # 刷新由 add_document 在锁外统一处理

        return True

    def _add_document_chunks_batch(self, document):
        """批量模式：将文档分块后缓冲到向量批量编码队列

        注意：此方法只负责将文档追加到缓冲区，不触发刷新。
        刷新由 add_document 在锁外调用 _flush_vector_buffer 处理。
        """
        from .text_chunker import TextChunker

        chunker = self.chunker or TextChunker(
            strategy=self.chunk_strategy,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        chunks = chunker.chunk_document(
            content=document.get("content", ""),
            doc_path=document.get("path", ""),
            doc_filename=document.get("filename", ""),
        )

        if not chunks:
            self.logger.warning(
                f"文档分块结果为空，跳过向量索引: {document.get('path', '')}"
            )
            return True

        original_chunk_count = len(chunks)
        if len(chunks) > MAX_CHUNKS_PER_DOC:
            doc_path = document.get("path", "")
            self.logger.warning(
                f"文档 {doc_path} 产生过多分块 ({len(chunks)})，"
                f"已截断至 {MAX_CHUNKS_PER_DOC}"
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        with self._batch_lock:
            for chunk in chunks:
                chunk_content = chunk.content[:MAX_ENCODE_LENGTH]
                if not chunk_content.strip():
                    continue

                metadata = {
                    "path": document["path"],
                    "filename": document["filename"],
                    "file_type": document["file_type"],
                    "modified": (
                        document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                        if isinstance(document["modified"], datetime)
                        else str(document["modified"])
                    ),
                    "is_chunk": True,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": original_chunk_count,
                    "chunk_start_pos": chunk.start_pos,
                    "chunk_end_pos": chunk.end_pos,
                    "chunk_content_preview": chunk.content[:200],
                }
                self._vector_buffer.append((chunk_content, metadata))

            # 不再在此触发刷新，避免三层嵌套锁
            # 刷新由 add_document 在锁外统一处理

        return True

    def _add_document_single(self, document):
        """传统模式：整个文档作为一个向量存储"""
        content_to_encode = (
            document["content"][:MAX_ENCODE_LENGTH] if document["content"] else ""
        )
        if not content_to_encode.strip():
            self.logger.warning(f"文档内容为空，跳过向量索引: {document['path']}")
            return

        v = np.array([self._encode_text(content_to_encode)], dtype=np.float32)
        doc_id = self.next_id
        ids = np.array([doc_id])

        try:
            self.hnsw.add_items(v, ids)
        except Exception:
            # 如果添加项目失败，尝试调整索引大小
            self.hnsw.resize_index(self.hnsw.get_max_elements() + 1024)
            self.hnsw.add_items(v, ids)

        # 记录元数据（标记为非分块文档）
        self.vector_metadata[str(doc_id)] = {
            "path": document["path"],
            "filename": document["filename"],
            "file_type": document["file_type"],
            "modified": (
                document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(document["modified"], datetime)
                else str(document["modified"])
            ),
            "is_chunk": False,
            "chunk_index": 0,
            "total_chunks": 1,
        }
        self.next_id += 1
        # 非批量模式下立即保存索引
        if not self._batch_mode:
            self.save_indexes()

    def _add_document_chunks(self, document):
        """分块模式：将文档分块后批量编码存储"""
        chunks = self.chunker.chunk_document(
            content=document["content"],
            doc_path=document["path"],
            doc_filename=document["filename"],
            doc_metadata={
                "file_type": document["file_type"],
                "modified": (
                    document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(document["modified"], datetime)
                    else str(document["modified"])
                ),
            },
        )

        if not chunks:
            self.logger.warning(f"文档分块结果为空，跳过向量索引: {document['path']}")
            return

        original_chunk_count = len(chunks)
        if len(chunks) > MAX_CHUNKS_PER_DOC:
            self.logger.warning(
                f"文档 {document['path']} 产生过多分块 ({len(chunks)})，"
                f"已截断至 {MAX_CHUNKS_PER_DOC}"
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        self.logger.info(f"文档分块完成: {document['filename']} -> {len(chunks)} 个块")

        # 收集所有有效分块内容和元数据
        texts_to_encode = []
        chunk_metadatas = []
        for chunk in chunks:
            chunk_content = chunk.content[:MAX_ENCODE_LENGTH]
            if not chunk_content.strip():
                continue
            texts_to_encode.append(chunk_content)
            chunk_metadatas.append(
                {
                    "path": chunk.doc_path,
                    "filename": chunk.doc_filename,
                    "file_type": document["file_type"],
                    "modified": (
                        document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                        if isinstance(document["modified"], datetime)
                        else str(document["modified"])
                    ),
                    "is_chunk": True,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": original_chunk_count,
                    "chunk_start": chunk.start_pos,
                    "chunk_end": chunk.end_pos,
                    "char_count": chunk.char_count,
                    "chunk_content_preview": chunk.content[:200],
                }
            )

        if not texts_to_encode:
            return

        # 批量编码所有分块
        success_count = 0
        try:
            vectors = self._encode_texts_batch(texts_to_encode)
            ids = np.arange(self.next_id, self.next_id + len(vectors))

            try:
                self.hnsw.add_items(vectors, ids)
            except Exception:
                self.hnsw.resize_index(
                    self.hnsw.get_max_elements() + len(vectors) + 1024
                )
                self.hnsw.add_items(vectors, ids)

            for i, metadata in enumerate(chunk_metadatas):
                self.vector_metadata[str(self.next_id + i)] = metadata
            self.next_id += len(vectors)
            success_count = len(chunk_metadatas)
        except Exception as e:
            self.logger.error(f"批量编码分块失败，回退到逐个编码: {e}")
            for text, metadata in zip(texts_to_encode, chunk_metadatas):
                if self._store_chunk_vector(text, metadata):
                    success_count += 1

        # 非批量模式下立即保存索引
        if not self._batch_mode:
            self.save_indexes()

        self.logger.info(
            f"成功添加 {success_count}/{len(chunks)} 个chunks到向量索引: "
            f"{document['path']}"
        )

    def _store_chunk_vector(
        self, chunk_content_or_chunk, metadata_or_document, total_chunks=None
    ):
        """存储单个chunk的向量（兼容两种调用方式）

        Args:
            chunk_content_or_chunk: 文本内容(str) 或 TextChunk 对象
            metadata_or_document: 元数据字典(dict) 或 原始文档(dict)
            total_chunks: 分块总数（仅 TextChunk 模式使用）
        """
        # 兼容旧调用方式: _store_chunk_vector(chunk, document, total_chunks)
        if isinstance(chunk_content_or_chunk, str):
            chunk_content = chunk_content_or_chunk
            metadata = metadata_or_document
        else:
            chunk = chunk_content_or_chunk
            document = metadata_or_document
            chunk_content = chunk.content[:MAX_ENCODE_LENGTH]
            if not chunk_content.strip():
                return False
            metadata = {
                "path": chunk.doc_path,
                "filename": chunk.doc_filename,
                "file_type": document["file_type"],
                "modified": (
                    document["modified"].strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(document["modified"], datetime)
                    else str(document["modified"])
                ),
                "is_chunk": True,
                "chunk_index": chunk.chunk_index,
                "total_chunks": total_chunks,
                "chunk_start": chunk.start_pos,
                "chunk_end": chunk.end_pos,
                "char_count": chunk.char_count,
                "chunk_content_preview": chunk.content[:200],
            }

        if not chunk_content.strip():
            return False

        try:
            v = np.array([self._encode_text(chunk_content)], dtype=np.float32)
            doc_id = self.next_id
            ids = np.array([doc_id])

            try:
                self.hnsw.add_items(v, ids)
            except Exception:
                self.hnsw.resize_index(self.hnsw.get_max_elements() + 1024)
                self.hnsw.add_items(v, ids)

            self.vector_metadata[str(doc_id)] = metadata
            self.next_id += 1
            return True

        except Exception as e:
            self.logger.error(f"添加chunk到向量索引失败: {str(e)}")
            return False

    def update_document(self, document):
        """更新文档（先删除旧文档，再添加新文档）- 线程安全"""
        if not isinstance(document, dict):
            self.logger.error(f"无效的文档格式，期望字典但得到 {type(document)}")
            return False
        with self._index_lock:
            try:
                self.delete_document(document.get("path"))
            except Exception as e:
                self.logger.debug(
                    f"删除旧文档失败（可能不存在）{document.get('path', '')}: {str(e)}"
                )
            return self.add_document(document)

    def delete_document(self, file_path):
        """从索引中删除文档"""
        if not getattr(self, "tantivy_index", None):
            return False

        # 首先尝试清理可能的锁文件
        try:
            lock_file = os.path.join(self.tantivy_index_path, "meta.json.lock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    self.logger.debug("已清理Tantivy索引锁文件")
                except Exception:
                    pass
        except Exception:
            pass

        # 辅助函数：检查并等待批量模式结束（避免死锁）
        def wait_for_batch_mode(timeout=90, force_if_timeout=True):
            """等待批量模式结束

            Args:
                timeout: 等待超时时间（秒）
                force_if_timeout: 超时后是否强制结束批量模式

            Returns:
                True: 批量模式已结束或被强制结束
                False: 批量模式仍在运行但未强制结束
            """
            if not self._batch_mode:
                return True

            batch_start = self._batch_mode_start_time or time.time()
            wait_start = time.time()

            while self._batch_mode and time.time() - wait_start < timeout:
                elapsed = time.time() - batch_start
                if elapsed > self._BATCH_MODE_TIMEOUT:
                    self.logger.warning(
                        f"批量模式已运行 {elapsed:.1f} 秒，"
                        f"超过上限 {self._BATCH_MODE_TIMEOUT} 秒"
                    )
                    if force_if_timeout:
                        self.logger.warning("强制结束卡住的批量模式（避免死锁）...")
                        # 使用强制重置避免死锁
                        self._force_reset_batch_mode()
                        return True
                time.sleep(0.2)

            if self._batch_mode:
                if force_if_timeout:
                    self.logger.warning("等待批量模式超时，强制结束（避免死锁）...")
                    self._force_reset_batch_mode()
                    return True
                return False
            return True

        # 等待批量模式结束（如果正在进行）
        if not wait_for_batch_mode(timeout=90, force_if_timeout=True):
            self.logger.warning("批量模式仍在运行，删除操作可能失败")

        # 添加重试机制处理锁冲突
        delete_success = False
        max_retries = 8
        for retry in range(max_retries):
            try:
                # 再次检查批量模式状态
                if self._batch_mode:
                    if not wait_for_batch_mode(timeout=15, force_if_timeout=True):
                        self.logger.warning("批量模式仍在运行，继续尝试删除...")

                query = self.tantivy_index.parse_query(f'"{file_path}"', ["path"])
                with self.tantivy_index.writer() as writer:
                    if hasattr(writer, "delete_query"):
                        getattr(writer, "delete_query")(query)
                        writer.commit()
                    elif hasattr(writer, "delete_documents"):
                        writer.delete_documents("path", file_path)
                        writer.commit()
                    else:
                        self.logger.warning(
                            "Tantivy writer不支持删除操作，跳过文本索引删除"
                        )
                delete_success = True
                break  # 成功则退出重试循环
            except Exception as e:
                if "LockBusy" in str(e) and retry < max_retries - 1:
                    self.logger.warning(
                        f"索引锁冲突，重试删除 {file_path} ({retry + 1}/{max_retries})"
                    )
                    time.sleep(0.5 * (retry + 1))  # 递增等待时间
                    # 如果批量模式超时太久了，强制结束它
                    if self._batch_mode:
                        batch_elapsed = time.time() - (
                            self._batch_mode_start_time or time.time()
                        )
                        if (
                            batch_elapsed > self._BATCH_MODE_TIMEOUT * 2
                        ):  # 超过超时2倍，强制结束
                            self.logger.warning(
                                f"批量模式运行太久({batch_elapsed:.1f}秒)，强制结束"
                            )
                            self.end_batch_mode(commit=True)
                else:
                    self.logger.warning(
                        f"从Tantivy索引删除文档失败 {file_path}: {str(e)}"
                    )
                    break

        # 标记文件为已删除（因为HNSW不支持真正删除向量，只能在搜索时过滤）
        with self._index_lock:
            self._deleted_paths.add(file_path)
            # 从向量元数据中删除（不影响搜索，只是清理元数据）
            try:
                for doc_id, metadata in list(self.vector_metadata.items()):
                    if metadata.get("path") == file_path:
                        del self.vector_metadata[doc_id]
                        self.logger.debug(f"已从向量元数据中删除文档 {file_path}")
                        break
            except (KeyError, RuntimeError) as e:
                # KeyError: doc_id已被删除; RuntimeError: 迭代中字典被修改
                self.logger.warning(
                    f"从向量元数据删除文档失败 {file_path}: {type(e).__name__}: {e}"
                )

        return delete_success

    def delete_documents_by_directory(self, directory_path: str) -> int:
        """
        从索引中删除指定目录下的所有文档

        Args:
            directory_path: 要删除的目录路径

        Returns:
            删除的文档数量
        """
        if not getattr(self, "tantivy_index", None):
            return 0

        deleted_count = 0
        directory_path_lower = directory_path.lower()

        # 辅助函数：检查并等待批量模式结束（避免死锁）
        def wait_for_batch_mode(timeout=90, force_if_timeout=True):
            """等待批量模式结束

            Args:
                timeout: 等待超时时间（秒）
                force_if_timeout: 超时后是否强制结束批量模式

            Returns:
                True: 批量模式已结束或被强制结束
                False: 批量模式仍在运行但未强制结束
            """
            if not self._batch_mode:
                return True

            batch_start = self._batch_mode_start_time or time.time()
            wait_start = time.time()

            while self._batch_mode and time.time() - wait_start < timeout:
                elapsed = time.time() - batch_start
                if elapsed > self._BATCH_MODE_TIMEOUT:
                    self.logger.warning(
                        f"批量模式已运行 {elapsed:.1f} 秒，"
                        f"超过上限 {self._BATCH_MODE_TIMEOUT} 秒"
                    )
                    if force_if_timeout:
                        self.logger.warning("强制结束卡住的批量模式（避免死锁）...")
                        # 使用强制重置避免死锁
                        self._force_reset_batch_mode()
                        return True
                time.sleep(0.2)

            if self._batch_mode:
                if force_if_timeout:
                    self.logger.warning("等待批量模式超时，强制结束（避免死锁）...")
                    self._force_reset_batch_mode()
                    return True
                return False
            return True

        # 1. 从Tantivy索引中删除（扫描并删除匹配目录的文档）
        try:
            # 先清理可能存在的锁文件
            lock_file = os.path.join(self.tantivy_index_path, "meta.json.lock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    self.logger.debug("已清理 Tantivy 索引锁文件")
                except Exception:
                    pass

            # 如果批量模式正在进行，等待批量模式结束
            # 因为批量模式持有 writer 锁，直接获取会 LockBusy
            if not wait_for_batch_mode(timeout=90, force_if_timeout=True):
                self.logger.warning("批量模式仍在运行，删除操作可能失败")

            # 由于 path 字段使用 raw tokenizer，前缀查询不工作
            # 因此需要遍历所有文档找到匹配的并删除
            max_retries = 10  # 增加重试次数
            for retry in range(max_retries):
                try:
                    # 再次检查并等待批量模式结束
                    if not wait_for_batch_mode(timeout=20, force_if_timeout=True):
                        self.logger.warning("批量模式仍在运行，继续尝试删除...")

                    # 刷新索引读取器以获取最新数据
                    if not self._batch_mode:
                        self.tantivy_index.reload()

                    # 使用新版 Tantivy API 遍历文档
                    docs_to_delete = []
                    searcher = None
                    try:
                        searcher = self.tantivy_index.searcher()
                        # 使用搜索方式查找匹配的文档
                        try:
                            from tantivy.query import RegexQuery

                            # 使用正则匹配路径前缀
                            regex_query = RegexQuery(
                                rf"{re.escape(directory_path_lower)}.*", "path"
                            )
                            result = searcher.search(regex_query, 1000)
                            for hit in result.hits:
                                try:
                                    doc = searcher.doc(hit.doc)
                                    path_value = doc.get_first("path", "")
                                    if path_value:
                                        docs_to_delete.append((hit.doc, hit.doc))
                                except Exception:
                                    continue
                        except ImportError:
                            # 如果 RegexQuery 不可用，使用暴力遍历
                            for doc_id in range(int(searcher.num_docs)):
                                try:
                                    doc = searcher.doc(doc_id)
                                    path_value = doc.get_first("path", "")
                                    if path_value and path_value.lower().startswith(
                                        directory_path_lower
                                    ):
                                        docs_to_delete.append((doc_id, doc_id))
                                except Exception:
                                    continue
                        except Exception as e:
                            # 降级：遍历所有文档
                            self.logger.debug(f"使用降级遍历方式: {e}")
                            for doc_id in range(int(searcher.num_docs)):
                                try:
                                    doc = searcher.doc(doc_id)
                                    path_value = doc.get_first("path", "")
                                    if path_value and path_value.lower().startswith(
                                        directory_path_lower
                                    ):
                                        docs_to_delete.append((doc_id, doc_id))
                                except Exception:
                                    continue
                    finally:
                        # 确保 searcher 被关闭
                        # Tantivy searcher 是轻量对象，不需要显式 release
                        if searcher is not None:
                            try:
                                searcher.release()
                            except Exception:
                                pass

                    if docs_to_delete:
                        # 分批删除，每批处理后释放锁，避免长时间持有索引锁
                        BATCH_SIZE = 50
                        for i in range(0, len(docs_to_delete), BATCH_SIZE):
                            batch = docs_to_delete[i : i + BATCH_SIZE]
                            try:
                                with self.tantivy_index.writer() as writer:
                                    seen_docs = set()
                                    for doc_id, _ in batch:
                                        if doc_id not in seen_docs:
                                            seen_docs.add(doc_id)
                                            try:
                                                writer.delete_document(doc_id)
                                                deleted_count += 1
                                            except Exception:
                                                pass
                                    writer.commit()
                            except Exception as e:
                                if "LockBusy" in str(e):
                                    time.sleep(0.5 * (retry + 1))
                                    # 不再强制结束批量模式！让 scan_and_index 继续运行
                                    continue
                                else:
                                    raise
                        self.logger.info(
                            f"已从Tantivy索引中删除 {deleted_count} 个文档"
                        )
                    break
                except Exception as e:
                    if "LockBusy" in str(e) and retry < max_retries - 1:
                        time.sleep(0.5 * (retry + 1))
                        # 如果批量模式超时太久了，强制结束它
                        if self._batch_mode:
                            batch_elapsed = time.time() - (
                                self._batch_mode_start_time or time.time()
                            )
                            if batch_elapsed > self._BATCH_MODE_TIMEOUT * 2:
                                self.logger.warning(
                                    f"批量模式运行太久({batch_elapsed:.1f}秒)，强制结束"
                                )
                                self.end_batch_mode(commit=True)
                    else:
                        self.logger.warning(
                            f"从Tantivy索引删除目录失败 {directory_path}: {str(e)}"
                        )
                        break
        except Exception as e:
            self.logger.warning(f"删除Tantivy索引文档时出错 {directory_path}: {str(e)}")

        # 2. 从向量元数据中删除
        try:
            docs_to_delete = []
            for doc_id, metadata in self.vector_metadata.items():
                path = metadata.get("path", "")
                if path.lower().startswith(directory_path_lower):
                    docs_to_delete.append(doc_id)

            for doc_id in docs_to_delete:
                del self.vector_metadata[doc_id]
                deleted_count += 1

            # 保存更新后的元数据
            if docs_to_delete:
                self.save_indexes()
                self.logger.info(f"已从向量索引中删除 {len(docs_to_delete)} 个文档")

        except Exception as e:
            self.logger.warning(f"删除向量元数据失败 {directory_path}: {str(e)}")

        self.logger.info(
            f"目录索引清理完成: {directory_path}，删除了约 {deleted_count} 个文档"
        )
        return deleted_count if deleted_count >= 0 else 0

    def _highlight_text(self, content, query, window_size=120, max_snippets=3):
        """生成带有高亮关键词的多段文本摘要，并兼容常见的空格/大小写差异"""
        if not content or not query:
            return (
                content[:200] + "..."
                if content and len(content) > 200
                else (content or "")
            )

        try:
            # 构建关键词集合
            keywords = self._extract_keywords(query)

            if not keywords:
                return content[:200] + "..." if len(content) > 200 else content

            # 构建高亮正则模式
            patterns = self._build_highlight_regex(keywords)

            if not patterns:
                return content[:200] + "..." if len(content) > 200 else content

            # 查找匹配项
            matches = self._find_matches(content, patterns, keywords)

            if not matches:
                return content[:200] + "..." if len(content) > 200 else content

            # 选择最佳摘要片段
            snippets = self._select_snippets(
                content, matches, query, keywords, window_size, max_snippets
            )

            if not snippets:
                return content[:200] + "..." if len(content) > 200 else content

            # 应用高亮
            processed_snippets = [
                self._apply_highlights(chunk, patterns) for chunk in snippets
            ]
            final_snippet = "<br>...<br>".join(processed_snippets)
            return final_snippet
        except Exception as exc:
            self.logger.error(f"生成摘要失败: {str(exc)}")
            return content[:200] + "..."

    def _extract_keywords(self, query):
        """从查询中提取关键词"""

        def _clean_keyword(token: str) -> str:
            return token.strip()

        keywords = set()

        # 1. 原始查询作为关键词
        if query.strip():
            keywords.add(query.strip())

        # 2. 分词后的关键词
        raw_tokens = [k.strip() for k in re.split(r"[\s,;，；]+", query) if k.strip()]
        for token in raw_tokens:
            cleaned = _clean_keyword(token)
            if cleaned:
                keywords.add(cleaned)
            # 只有当token比较长时才进行进一步分词，避免过度碎片化
            if len(token) > 2:
                for seg in jieba.lcut_for_search(token):
                    seg_clean = _clean_keyword(seg)
                    if seg_clean and len(seg_clean) > 1:  # 忽略单字，除非是原始token
                        keywords.add(seg_clean)

        return keywords

    def _build_highlight_regex(self, keywords):
        """构建高亮正则表达式模式（带缓存）"""
        # 使用 frozenset 作为缓存键
        cache_key = frozenset(keywords)
        if hasattr(self, "_highlight_regex_cache"):
            cached = self._highlight_regex_cache.get(cache_key)
            if cached is not None:
                return cached

        def _build_pattern(token: str):
            # 允许字符之间穿插空白，适配 "J a v a" 这类被拆分的文本
            # 对特殊字符进行转义
            escaped = re.escape(token)
            # 如果是字母或数字，允许中间有空格
            if token.isalnum():
                pieces = [f"{re.escape(ch)}\\s*" for ch in token]
                pattern = "".join(pieces)
                return re.compile(pattern, re.IGNORECASE)
            return re.compile(escaped, re.IGNORECASE)

        result = [_build_pattern(token) for token in keywords if token]

        # 初始化缓存（如果需要）
        if not hasattr(self, "_highlight_regex_cache"):
            self._highlight_regex_cache = {}
        # 限制缓存大小
        if len(self._highlight_regex_cache) < 100:
            self._highlight_regex_cache[cache_key] = result

        return result

    def _find_matches(self, content, patterns, keywords):
        """在内容中查找匹配项"""

        def _expand_ascii_span(text: str, start: int, end: int):
            # 向左右扩展，确保高亮完整的ASCII单词（如JavaScript）
            while start > 0 and text[start - 1].isascii() and text[start - 1].isalnum():
                start -= 1
            while end < len(text) and text[end].isascii() and text[end].isalnum():
                end += 1
            return start, end

        def _collect_matches(full_text: str, patterns):
            spans = []
            seen = set()
            for pat in patterns:
                for match in pat.finditer(full_text):
                    span = _expand_ascii_span(full_text, match.start(), match.end())
                    if span not in seen:
                        seen.add(span)
                        spans.append(span)
            return spans

        # 使用正则表达式查找匹配
        matches = _collect_matches(content, patterns)

        # fallback: 如果仍然没有匹配，则尝试直接定位（兼容极端情况）
        if not matches:
            lowered = content.lower()
            for token in keywords:
                idx = lowered.find(token.lower())
                if idx != -1:
                    match_span = _expand_ascii_span(content, idx, idx + len(token))
                    matches.append(match_span)
                    # 只要找到一个匹配就足够了
                    break

        # 按位置排序
        matches.sort(key=lambda x: x[0])
        return matches

    def _select_snippets(
        self, content, matches, query, keywords, window_size=120, max_snippets=3
    ):
        """从匹配项中选择最佳摘要片段"""
        # 合并窗口
        windows = []
        for start, end in matches:
            win_start = max(0, start - window_size // 2)
            win_end = min(len(content), end + window_size // 2)
            if windows and win_start < windows[-1][1]:
                windows[-1] = (windows[-1][0], max(windows[-1][1], win_end))
            else:
                windows.append((win_start, win_end))

        # 评分并选择最佳窗口
        scored_windows = []
        lowered_content = content.lower()
        for win_start, win_end in windows:
            chunk = lowered_content[win_start:win_end]
            score = 0
            for token in keywords:
                if token.lower() in chunk:
                    score += 1
            # 优先考虑包含完整查询词的窗口
            if query.lower() in chunk:
                score += 10
            scored_windows.append((score, win_start, win_end))

        scored_windows.sort(key=lambda x: x[0], reverse=True)
        selected_windows = [(s, e) for _, s, e in scored_windows[:max_snippets]]
        selected_windows.sort(key=lambda x: x[0])

        # 提取片段并进行自然截断
        snippets = []
        for start, end in selected_windows:
            # 尝试在标点符号处截断，使摘要更自然
            curr_start = start
            while (
                curr_start > 0
                and curr_start > start - 20
                and content[curr_start] not in " \t\n\r.,;，。；"
            ):
                curr_start -= 1
            if curr_start > 0 and content[curr_start] in " \t\n\r.,;，。；":
                curr_start += 1

            curr_end = end
            while (
                curr_end < len(content)
                and curr_end < end + 20
                and content[curr_end] not in " \t\n\r.,;，。；"
            ):
                curr_end += 1

            chunk = content[curr_start:curr_end].strip()
            if chunk:
                snippets.append(chunk)

        # 如果窗口提取失败，回退到简单的正则提取
        if not snippets:
            for token in keywords:
                pat = re.compile(re.escape(token), re.IGNORECASE)
                match = pat.search(content)
                if match:
                    start = max(0, match.start() - 60)
                    end = min(len(content), match.end() + 60)
                    snippets.append(content[start:end])
                    break

        return snippets

    def _apply_highlights(self, text, patterns):
        """在文本中应用高亮标记"""
        import html

        def _expand_ascii_span(text: str, start: int, end: int):
            # 向左右扩展，确保高亮完整的ASCII单词（如JavaScript）
            while start > 0 and text[start - 1].isascii() and text[start - 1].isalnum():
                start -= 1
            while end < len(text) and text[end].isascii() and text[end].isalnum():
                end += 1
            return start, end

        def _collect_matches(full_text: str, patterns):
            spans = []
            seen = set()
            for pat in patterns:
                for match in pat.finditer(full_text):
                    span = _expand_ascii_span(full_text, match.start(), match.end())
                    if span not in seen:
                        seen.add(span)
                        spans.append(span)
            return spans

        spans = _collect_matches(text, patterns)
        if not spans:
            return text

        spans.sort(key=lambda x: x[0])
        merged = []
        for start, end in spans:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        highlighted = []
        last = 0
        for start, end in merged:
            if start < last:
                continue
            # 先转义原始文本中的HTML特殊字符，防止破坏标签结构
            highlighted.append(html.escape(text[last:start]))
            # 使用 text-danger 和 fw-bold 高亮
            highlighted.append(
                '<span class="text-success fw-bold">'
                f"{html.escape(text[start:end])}</span>"
            )
            last = end
        # 最后一部分也需要转义
        highlighted.append(html.escape(text[last:]))
        return "".join(highlighted)

    def get_document_content(self, path):
        # 尝试从Tantivy索引中获取内容
        if getattr(self, "tantivy_index", None):
            try:
                self.tantivy_index.reload()
                searcher = self.tantivy_index.searcher()

                # 1. 尝试精确路径查询 (注意转义反斜杠)
                escaped_path = path.replace("\\", "\\\\").replace('"', '\\"')
                query_str = f'path:"{escaped_path}"'
                try:
                    query = self.tantivy_index.parse_query(query_str)
                    hits = searcher.search(query, 1).hits
                    if hits:
                        _, doc_addr = hits[0]
                        doc = searcher.doc(doc_addr)
                        raw_val = doc.get_first("content_raw")
                        content_val = raw_val or doc.get_first("content")
                        if raw_val:
                            return raw_val  # 返回完整内容，不限制长度
                        if content_val:
                            # 如果索引中的内容不完整，尝试直接解析文件
                            parsed = self._parse_file_direct(path)
                            return parsed if parsed else content_val
                except Exception as e:
                    self.logger.debug(f"精确路径查询失败 {path}: {str(e)}")

                # 2. 如果精确路径失败，尝试通过文件名查询 (作为后备)
                filename = os.path.basename(path)
                escaped_filename = filename.replace('"', '\\"')
                query_str = f'filename:"{escaped_filename}"'
                try:
                    query = self.tantivy_index.parse_query(query_str)
                    hits = searcher.search(query, 5).hits  # 获取前5个同名文件
                    for _, doc_addr in hits:
                        doc = searcher.doc(doc_addr)
                        idx_path = doc.get_first("path")
                        # 在Python层面验证路径是否匹配 (忽略大小写和分隔符差异)
                        if (
                            idx_path
                            and os.path.normpath(idx_path).lower()
                            == os.path.normpath(path).lower()
                        ):
                            raw_val = doc.get_first("content_raw")
                            content_val = raw_val or doc.get_first("content")
                            if raw_val:
                                return raw_val  # 返回完整内容，不限制长度
                            if content_val:
                                # 如果索引中的内容不完整，尝试直接解析文件
                                parsed = self._parse_file_direct(path)
                                return parsed if parsed else content_val
                except Exception as e:
                    self.logger.debug(f"文件名查询失败 {path}: {str(e)}")

            except Exception as e:
                self.logger.error(f"从索引获取内容失败: {str(e)}")

        # 降级方案：使用DocumentParser解析文件
        try:
            parsed = self._parse_file_direct(path)
            if parsed:
                return parsed
        except Exception as e:
            self.logger.error(f"使用DocumentParser解析失败: {str(e)}")

        # 最后的降级方案：直接读取文件
        try:
            # 扩展支持的文本格式列表
            ext = os.path.splitext(path)[1].lower()
            text_exts = [
                ".txt",
                ".md",
                ".py",
                ".json",
                ".xml",
                ".csv",
                ".log",
                ".js",
                ".html",
                ".css",
                ".bat",
                ".sh",
                ".yaml",
                ".yml",
                ".ini",
                ".conf",
                ".sql",
                ".properties",
                ".gradle",
                ".java",
                ".c",
                ".cpp",
                ".h",
                ".hpp",
            ]
            if ext in text_exts:
                if os.path.exists(path):
                    # 读取完整文件内容，不限制长度（调用方应自行处理大文件）
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        return f.read()
        except Exception as e:
            self.logger.debug(f"直接读取文件失败 {path}: {str(e)}")
        return ""

    def _parse_file_direct(self, path):
        try:
            from backend.core.document_parser import DocumentParser

            parser = DocumentParser(self.config_loader)
            content = parser.extract_text(path)
            if content and not content.startswith("错误"):
                return content
        except Exception as exc:
            self.logger.debug(f"直接解析文件失败: {exc}")
        return ""

    def _format_result(
        self,
        path,
        filename,
        content,
        raw_content,
        file_type,
        size,
        modified,
        score,
        query_str,
    ):
        """格式化搜索结果"""
        display_content = raw_content if raw_content else content or ""
        norm_query = (query_str or "").strip()
        norm_query_lower = norm_query.lower()

        # 改进内容结构：如果文件名没有在内容中，添加到内容开头
        # 这样可以确保文件名中的关键词也能被高亮和搜索到
        structured_content = display_content
        if filename:
            # 检查文件名是否已经在内容开头，避免重复
            if not display_content.strip().startswith(filename):
                structured_content = f"文件名: {filename}\n\n" + structured_content

        # 使用包含文件名的内容进行高亮和查询检查
        display_lower = structured_content.lower() if structured_content else ""
        contains_query = bool(norm_query and norm_query_lower in display_lower)

        # 生成高亮摘要
        snippet = self._highlight_text(structured_content, norm_query)

        # 如果没有生成高亮或缺少命中，再尝试解析原文 (fallback)
        if norm_query and (
            not snippet or "text-danger" not in snippet or not contains_query
        ):
            try:
                fallback = self.get_document_content(path)
                if fallback and fallback != display_content:
                    # 如果fallback内容不同，重新构建structured_content
                    fallback_structured = fallback
                    if filename and not fallback.strip().startswith(filename):
                        fallback_structured = f"文件名: {filename}\n\n" + fallback

                    display_lower = fallback_structured.lower()
                    contains_query = norm_query_lower in display_lower
                    snippet = self._highlight_text(fallback_structured, norm_query)
                    structured_content = fallback_structured
            except Exception as e:
                self.logger.debug(f"Fallback解析失败: {str(e)}")

        # 转换时间戳
        modified_time = None
        if modified:
            try:
                import datetime

                if isinstance(modified, (int, float)):
                    modified_time = datetime.datetime.fromtimestamp(modified).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    modified_time = str(modified)
            except (ValueError, TypeError, OverflowError) as e:
                self.logger.debug(f"时间戳转换失败: {str(e)}")

        return {
            "path": path,
            "filename": filename,
            "file_name": filename,
            "content": structured_content,  # 使用结构化内容
            "snippet": snippet,  # 添加高亮摘要
            "file_type": file_type,
            "size": size,
            "modified": modified_time,  # 添加修改时间
            "score": score,
            "has_query": contains_query,
        }

    def search_text(self, query_str, limit=10, filters=None):
        if not getattr(self, "tantivy_index", None):
            return []
        try:
            results = []

            # 统一转小写进行搜索（索引已小写存储）
            query_str_processed = query_str.lower().strip()
            if not query_str_processed:
                return []

            # 分词
            seg_query = self._segment(query_str_processed)

            # 批量模式下不调用 reload，避免与 writer 竞争
            with self._batch_lock:
                is_batch_mode = self._batch_mode

            if not is_batch_mode:
                self.tantivy_index.reload()
            searcher = self.tantivy_index.searcher()
            queries_to_try = []

            # Determine fields based on filters
            search_content = True
            if filters and "search_content" in filters:
                search_content = filters["search_content"]

            if search_content:
                exact_fields = ["content_raw", "filename"]
                fields = [
                    "filename",
                    "content",
                    "content_raw",
                    "keywords",
                    "filename_chars",
                    "content_chars",
                ]
            else:
                exact_fields = ["filename"]
                fields = ["filename", "filename_chars"]

            # 优化：短查询（单字符或双字符）简化搜索策略
            query_len = len(query_str_processed)
            is_short_query = query_len <= 2

            if is_short_query:
                # 短查询：只执行必要的查询，避免过多组合
                # 1. 精确匹配文件名
                try:
                    queries_to_try.append(
                        self.tantivy_index.parse_query(
                            query_str_processed, ["filename"]
                        )
                    )
                except Exception as e:
                    self.logger.debug(f"短查询文件名匹配失败: {str(e)}")

                # 2. 字符级匹配（对中文单字搜索很重要）
                try:
                    queries_to_try.append(
                        self.tantivy_index.parse_query(
                            query_str_processed, ["filename_chars", "content_chars"]
                        )
                    )
                except Exception as e:
                    self.logger.debug(f"短查询字符匹配失败: {str(e)}")

                # 3. 内容原始文本匹配
                if search_content:
                    try:
                        queries_to_try.append(
                            self.tantivy_index.parse_query(
                                query_str_processed, ["content_raw"]
                            )
                        )
                    except Exception as e:
                        self.logger.debug(f"短查询内容匹配失败: {str(e)}")
            else:
                # 正常查询：完整搜索策略
                # 0. 优先尝试精确短语匹配
                try:
                    queries_to_try.append(
                        self.tantivy_index.parse_query(
                            f'"{query_str_processed}"', exact_fields
                        )
                    )
                except Exception as e:
                    self.logger.debug(f"精确短语查询构建失败: {str(e)}")

                # 1. 分词查询
                try:
                    queries_to_try.append(
                        self.tantivy_index.parse_query(seg_query, fields)
                    )
                except Exception as e:
                    self.logger.debug(f"分词查询构建失败: {str(e)}")

                # 2. 原始查询
                if query_str != seg_query:
                    try:
                        queries_to_try.append(
                            self.tantivy_index.parse_query(query_str, fields)
                        )
                    except Exception as e:
                        self.logger.debug(f"原始查询构建失败: {str(e)}")

                # 3. 单词查询（只对较长的分词结果）
                words = [w for w in seg_query.split() if len(w.strip()) > 1]
                if words:
                    try:
                        for word in words[:3]:  # 限制最多3个单词查询
                            queries_to_try.append(
                                self.tantivy_index.parse_query(word, fields)
                            )
                    except Exception as e:
                        self.logger.debug(f"单词查询构建失败: {str(e)}")

                # 4. 字符查询（只对非中文短查询）
                if query_len <= 10:
                    try:
                        chars = re.findall(r"\w", query_str_processed)[:5]  # 限制字符数
                        for ch in chars:
                            if search_content:
                                queries_to_try.append(
                                    self.tantivy_index.parse_query(
                                        ch, ["filename_chars", "content_chars"]
                                    )
                                )
                            else:
                                queries_to_try.append(
                                    self.tantivy_index.parse_query(
                                        ch, ["filename_chars"]
                                    )
                                )
                    except Exception as e:
                        self.logger.debug(f"字符查询构建失败: {str(e)}")

            all_hits = []
            for query in queries_to_try:
                try:
                    hits = searcher.search(query, limit * 2).hits
                    all_hits.extend(hits)
                except Exception as e:
                    self.logger.debug(f"查询执行失败: {str(e)}")
                    continue

            unique_docs = {}
            for score, doc_address in all_hits:
                addr_key = str(doc_address)
                if addr_key not in unique_docs or unique_docs[addr_key][0] < score:
                    unique_docs[addr_key] = (score, doc_address)

            sorted_hits = sorted(unique_docs.values(), key=lambda x: x[0], reverse=True)
            final_hits = sorted_hits[:limit]

            for score, doc_address in final_hits:
                doc = searcher.doc(doc_address)
                try:
                    path_val = doc.get_first("path") or ""
                    filename_val = doc.get_first("filename") or ""
                    content_val = doc.get_first("content") or ""
                    content_raw_val = doc.get_first("content_raw") or ""
                    file_type_val = doc.get_first("file_type") or ""
                    size_val = doc.get_first("size") or 0
                    modified_val = doc.get_first("modified") or 0
                except (AttributeError, KeyError, TypeError) as e:
                    self.logger.debug(f"获取文档字段失败: {str(e)}")
                    continue

                # 不再限制BM25分数的上限，以便在搜索引擎中进行正确的归一化
                # normalized_score = min(float(score), 100.0)
                raw_score = float(score)

                results.append(
                    self._format_result(
                        path_val,
                        filename_val,
                        content_val,
                        content_raw_val,
                        file_type_val,
                        size_val,
                        modified_val,
                        raw_score,
                        query_str_processed,
                    )
                )

            results.sort(key=lambda x: x["score"], reverse=True)

            if query_str_processed and results:
                # 先将包含高亮的结果排列到前面，但保留其他候选
                highlighted = [
                    r for r in results if "text-danger" in (r.get("snippet") or "")
                ]
                if highlighted:
                    non_highlighted = [r for r in results if r not in highlighted]
                    results = highlighted + non_highlighted

                primary = [r for r in results if r.get("has_query")]
                secondary = [r for r in results if not r.get("has_query")]
                if primary:
                    results = primary + secondary

            # 同一路径仅保留得分最高的一个结果
            deduped_results = []
            seen_paths = set()
            for item in results:
                path_key = (item.get("path") or "").lower()
                if path_key and path_key in seen_paths:
                    continue
                if path_key:
                    seen_paths.add(path_key)
                deduped_results.append(item)

            return deduped_results
        except Exception as e:
            self.logger.error(f"文本搜索失败: {str(e)}")
            return []

    def search_vector(self, query_str, limit=10, group_by_doc=True):
        """
        向量搜索，支持返回chunk级别结果

        Args:
            query_str: 查询字符串
            limit: 返回结果数量
            group_by_doc: 是否按文档分组（同一文档的多个chunks只返回最相关的一个）
        """
        if getattr(self, "hnsw", None) is None:
            return []
        if not self.embedding_model:
            return []
        try:
            # 增加ef参数以避免"Cannot return the results in a contiguous 2D array"错误
            self.hnsw.set_ef(min(512, max(self.next_id, 200)))
            v = np.array([self._encode_text(query_str)], dtype=np.float32)
            k = min(limit * 3 if group_by_doc else limit, max(self.next_id, 1))
            labels, distances = self.hnsw.knn_query(v, k=k)
            results = []
            seen_docs = set()
            # 使用实例级内容缓存，避免同一文件多次 I/O
            # LRU 淘汰策略通过 _content_cache_order 实现
            cache = self._content_cache
            cache_order = self._content_cache_order
            max_cache_size = self._content_cache_max_size

            for i, idx in enumerate(labels[0]):
                # 在锁内读取共享数据，避免与删除操作产生竞态
                with self._index_lock:
                    if str(idx) not in self.vector_metadata:
                        continue
                    metadata = self.vector_metadata[str(idx)]
                    path = metadata["path"]

                    # 过滤已删除的文档
                    if path in self._deleted_paths:
                        continue

                    if group_by_doc and path.lower() in seen_docs:
                        continue

                    # 复制必要数据，释放锁后处理
                    d = distances[0][i]
                    sim = 1.0 - float(d)
                    adjusted = min(sim * 100.0, 100.0)
                    filename = metadata["filename"]
                    file_type = metadata["file_type"]
                    modified = metadata.get("modified")
                    is_chunk = metadata.get("is_chunk", False)
                    content_preview = (
                        metadata.get("chunk_content_preview", "") if is_chunk else ""
                    )
                    chunk_index = metadata.get("chunk_index", 0)
                    total_chunks = metadata.get("total_chunks", 1)
                    chunk_start = metadata.get("chunk_start", 0)
                    chunk_end = metadata.get("chunk_end", 0)

                    # seen_docs.add() 必须在锁内执行，避免竞态窗口
                    if group_by_doc:
                        seen_docs.add(path.lower())

                # 锁外执行耗时操作（I/O操作不应在锁内）
                # 使用实例级缓存 + LRU 淘汰，避免同一文件多次读取
                if is_chunk:
                    if len(content_preview) < 300:
                        if path not in cache:
                            # LRU 淘汰：当缓存满时移除最旧的条目
                            if len(cache) >= max_cache_size:
                                oldest = cache_order.pop(0)
                                cache.pop(oldest, None)
                            # 读取并缓存文件内容
                            cache[path] = self.get_document_content(path)
                            cache_order.append(path)
                        else:
                            # 缓存命中，更新 LRU 顺序（移到末尾表示最近使用）
                            if path in cache_order:
                                cache_order.remove(path)
                            cache_order.append(path)
                        full_content = cache.get(path)
                        if full_content and len(full_content) > chunk_start:
                            content = full_content[chunk_start:chunk_end]
                        else:
                            content = content_preview
                    else:
                        content = content_preview + "..."
                else:
                    if path not in cache:
                        if len(cache) >= max_cache_size:
                            oldest = cache_order.pop(0)
                            cache.pop(oldest, None)
                        cache[path] = self.get_document_content(path)
                        cache_order.append(path)
                    else:
                        # 缓存命中，更新 LRU 顺序（移到末尾表示最近使用）
                        if path in cache_order:
                            cache_order.remove(path)
                        cache_order.append(path)
                    content = cache.get(path)

                # 构建结果
                result = self._format_result(
                    path,
                    filename,
                    content,
                    content,
                    file_type,
                    0,
                    modified,
                    adjusted,
                    query_str,
                )

                result["is_chunk"] = is_chunk
                if is_chunk:
                    result["chunk_index"] = chunk_index
                    result["total_chunks"] = total_chunks
                    result["chunk_start"] = chunk_start
                    result["chunk_end"] = chunk_end
                    result["snippet"] = (
                        content[:300] + "..." if len(content) > 300 else content
                    )

                results.append(result)

                if len(results) >= limit:
                    break

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []

    def _encode_text(self, text: str):
        t0 = time.time()  # 调试计时
        # 触发延迟加载（如有必要）
        self._ensure_embedding_loaded()
        if not self.embedding_model:
            self.logger.warning(
                f"[ENCODE_SINGLE] 模型未就绪，返回零向量，耗时 {time.time() - t0:.3f}s"
            )
            return np.zeros(getattr(self, "vector_dim", 384), dtype=np.float32)
        try:
            vec = next(iter(self.embedding_model.embed([text])))
            result = np.array(vec, dtype=np.float32)
            self.logger.debug(f"[ENCODE_SINGLE] 完成，耗时 {time.time() - t0:.3f}s")
            return result
        except (StopIteration, RuntimeError, ValueError) as e:
            elapsed = time.time() - t0
            self.logger.warning(
                f"[ENCODE_SINGLE] 文本编码失败: {str(e)}，"
                f"耗时 {elapsed:.3f}s，返回零向量"
            )
            return np.zeros(getattr(self, "vector_dim", 384), dtype=np.float32)

    def _encode_texts_batch(self, texts: list) -> np.ndarray:
        """批量编码多个文本为向量（比逐个编码快 40-60%）

        Args:
            texts: 待编码的文本列表

        Returns:
            shape 为 (len(texts), vector_dim) 的 numpy 数组
        """
        t0 = time.time()  # 调试计时
        # 触发延迟加载（如有必要）
        self._ensure_embedding_loaded()
        if not texts or not self.embedding_model:
            dim = getattr(self, "vector_dim", 384)
            elapsed = time.time() - t0
            self.logger.warning(
                f"[ENCODE] Embedding模型未就绪，返回零向量，耗时 {elapsed:.3f}s"
            )
            return np.zeros((len(texts) if texts else 0, dim), dtype=np.float32)

        try:
            model_name = getattr(self.embedding_model, "model_name", "unknown")
            self.logger.info(
                f"[ENCODE] 开始编码 {len(texts)} 个文本，模型={model_name}"
            )
            t1 = time.time()
            vectors = list(self.embedding_model.embed(texts))
            t2 = time.time()
            self.logger.info(
                f"[ENCODE] embed() 调用完成，{len(texts)} 个文本，耗时 {t2 - t1:.3f}s"
            )
            result = np.array(vectors, dtype=np.float32)
            self.logger.info(
                f"[ENCODE] 转换为numpy完成，shape={result.shape}，总耗时 {t2 - t0:.3f}s"
            )
            return result
        except Exception as e:
            t_err = time.time()
            self.logger.error(
                f"[ENCODE] 批量编码失败 (耗时 {t_err - t0:.3f}s)，回退到逐个编码: {e}"
            )
            result = [self._encode_text(t) for t in texts]
            return np.array(result, dtype=np.float32)

    def _flush_vector_buffer(self):
        """将缓冲区中的向量批量编码并写入 HNSW 索引（线程安全）"""
        batch_lock = getattr(self, "_batch_lock", None)
        if batch_lock is None:
            # 如果锁未初始化（初始化失败），跳过刷新
            self.logger.warning("[VECTOR_FLUSH] _batch_lock 未初始化，跳过刷新")
            return
        with batch_lock:
            self._do_flush_vector_buffer()
            # with 语句自动释放锁

    def _do_flush_vector_buffer(self):
        """将缓冲区中的向量批量编码并写入 HNSW 索引（调用时必须持有 _batch_lock）"""
        if not self._vector_buffer:
            return

        t0 = time.time()  # 调试：记录开始时间
        self.logger.info(
            f"[VECTOR_FLUSH] 开始刷新向量缓冲区，大小={len(self._vector_buffer)}"
        )

        # 触发延迟加载（如有必要）
        self._ensure_embedding_loaded()
        if not self.embedding_model or self.hnsw is None:
            self.logger.info("[VECTOR_FLUSH] Embedding模型未就绪，清空缓冲区")
            self._vector_buffer = []
            return

        count = len(self._vector_buffer)
        texts = [item[0] for item in self._vector_buffer]
        metadatas = [item[1] for item in self._vector_buffer]

        try:
            t1 = time.time()  # 调试时间点
            self.logger.info(
                f"[VECTOR_FLUSH] 开始批量编码 {count} 个向量 (距开始 {t1 - t0:.3f}s)"
            )
            vectors = self._encode_texts_batch(texts)
            t2 = time.time()  # 调试：编码完成时间
            encode_time = t2 - t1
            total_time = t2 - t0
            self.logger.info(
                f"[VECTOR_FLUSH] 编码完成，shape={vectors.shape}，"
                f"耗时 {encode_time:.3f}s (累计 {total_time:.3f}s)"
            )

            # 预检查容量
            needed = self.next_id + len(vectors)
            max_elements = self.hnsw.get_max_elements()
            if needed > max_elements:
                self.logger.info(
                    f"[VECTOR_FLUSH] HNSW容量不足，"
                    f"扩展索引: {max_elements} -> {needed + 1024}"
                )
                self.hnsw.resize_index(needed + 1024)

            ids = np.arange(self.next_id, self.next_id + len(vectors))

            # HNSW写入需要保护，但只在写入时持有锁
            # metadata更新在锁外进行（因为commit thread不修改metadata）
            elapsed = t2 - t0
            self.logger.info(
                f"[VECTOR_FLUSH] 开始HNSW写入 {len(vectors)} 个向量 "
                f"(累计 {elapsed:.3f}s)"
            )
            t3 = time.time()  # 调试：HNSW写入开始时间
            # 注意：调用者已持有 _batch_lock，无需再次获取
            self.hnsw.add_items(vectors, ids)
            t4 = time.time()  # 调试：HNSW写入完成时间
            hnsw_time = t4 - t3
            total_time = t4 - t0
            self.logger.info(
                f"[VECTOR_FLUSH] HNSW写入完成，耗时 {hnsw_time:.3f}s "
                f"(累计 {total_time:.3f}s)"
            )

            # 更新metadata（在锁外进行，减少锁持有时间）
            t5 = time.time()  # 调试：metadata更新开始时间
            for i, metadata in enumerate(metadatas):
                self.vector_metadata[str(self.next_id + i)] = metadata
            self.next_id += len(vectors)
            t6 = time.time()  # 调试：metadata更新完成时间
            meta_time = t6 - t5
            total_time = t6 - t0
            self.logger.info(
                f"[VECTOR_FLUSH] metadata更新完成，{len(metadatas)} 条，"
                f"耗时 {meta_time:.3f}s (累计 {total_time:.3f}s)"
            )

            total_time = t6 - t0
            self.logger.info(
                f"[VECTOR_FLUSH] 向量批量写入完成: {count} 个向量，"
                f"总耗时 {total_time:.3f}s"
            )
        except Exception as e:
            t_err = time.time()
            elapsed = t_err - t0
            self.logger.error(
                f"[VECTOR_FLUSH] 向量批量写入失败 "
                f"(耗时 {elapsed:.3f}s)，回退到逐个写入: {e}"
            )
            for text, metadata in self._vector_buffer:
                try:
                    v = np.array([self._encode_text(text)], dtype=np.float32)
                    with self._batch_lock:
                        doc_id = self.next_id
                        ids = np.array([doc_id])
                        try:
                            self.hnsw.add_items(v, ids)
                        except Exception:
                            self.hnsw.resize_index(self.hnsw.get_max_elements() + 1024)
                            self.hnsw.add_items(v, ids)
                        self.vector_metadata[str(doc_id)] = metadata
                        self.next_id += 1
                except Exception as e2:
                    self.logger.warning(f"单个向量写入失败: {e2}")

        self._vector_buffer = []
        self.logger.info(f"[VECTOR_FLUSH] 刷新完成，缓冲区已清空")

    def save_indexes(self):
        try:
            # 刷新向量缓冲区
            self._flush_vector_buffer()

            # 确保目录存在
            os.makedirs(self.hnsw_index_path, exist_ok=True)
            os.makedirs(self.metadata_path, exist_ok=True)

            # 检查索引是否已初始化
            if getattr(self, "hnsw", None) is not None:
                # 使用临时文件，然后原子性地移动到目标位置以避免损坏
                index_file = os.path.join(self.hnsw_index_path, "vector_index.bin")
                temp_index_file = index_file + ".tmp"

                # 保存向量索引到临时文件
                self.hnsw.save_index(temp_index_file)

                # 原子性移动
                if os.path.exists(temp_index_file):
                    os.replace(temp_index_file, index_file)

            metadata_file = os.path.join(self.metadata_path, "vector_metadata.json")
            temp_metadata_file = metadata_file + ".tmp"
            metadata_dict = {
                "metadata": self.vector_metadata,
                "next_id": self.next_id,
                "vector_dim": self.vector_dim,
            }

            # 保存元数据到临时文件
            with open(temp_metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)

            # 原子性移动
            if os.path.exists(temp_metadata_file):
                os.replace(temp_metadata_file, metadata_file)

            self.logger.info("索引保存成功")
            return True
        except Exception as e:
            self.logger.error(f"保存索引失败: {str(e)}")
            import traceback

            self.logger.error(f"保存索引失败详细错误: {traceback.format_exc()}")
            return False

    def rebuild_index(self):
        """重建索引"""
        try:
            # 1. 先确保关闭索引，释放锁
            self.close()

            # 2. 删除 Tantivy 索引锁文件（如果存在）
            lock_file = os.path.join(self.tantivy_index_path, "meta.json.lock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    self.logger.info("已删除 Tantivy 索引锁文件")
                except Exception as e:
                    self.logger.warning(f"删除锁文件失败: {e}")

            # 3. 删除旧索引目录
            if os.path.exists(self.tantivy_index_path):
                shutil.rmtree(self.tantivy_index_path)
            if os.path.exists(self.hnsw_index_path):
                shutil.rmtree(self.hnsw_index_path)
            if os.path.exists(self.metadata_path):
                shutil.rmtree(self.metadata_path)

            # 4. 重新创建目录
            os.makedirs(self.tantivy_index_path, exist_ok=True)
            os.makedirs(self.hnsw_index_path, exist_ok=True)
            os.makedirs(self.metadata_path, exist_ok=True)

            # 5. 重新初始化索引
            self._init_tantivy_index()
            self._init_hnsw_index()
            return True
        except Exception as e:
            self.logger.error(f"重建索引失败: {str(e)}")
            return False

    def is_index_ready(self):
        try:
            return os.path.exists(self.tantivy_index_path)
        except (OSError, TypeError) as e:
            self.logger.debug(f"检查索引状态失败: {str(e)}")
            return False

    def get_index_stats(self):
        """获取索引统计信息"""
        try:
            # 获取Tantivy索引统计
            searcher = self.tantivy_index.searcher()
            # num_docs 在新版 tantivy 中是属性而非方法
            num_docs_attr = getattr(searcher, "num_docs", 0)
            if callable(num_docs_attr):
                doc_count = num_docs_attr()
            else:
                doc_count = num_docs_attr

            # 获取向量索引统计
            vector_count = (
                len(self.vector_metadata) if hasattr(self, "vector_metadata") else 0
            )

            # 统计分块信息
            chunk_stats = self._get_chunk_stats()

            # 获取索引目录大小
            import os

            def get_dir_size(path):
                total = 0
                for dirpath, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        total += os.path.getsize(filepath)
                return total

            tantivy_size = get_dir_size(self.tantivy_index_path)
            hnsw_size = (
                get_dir_size(self.hnsw_index_path)
                if os.path.exists(self.hnsw_index_path)
                else 0
            )
            metadata_size = (
                get_dir_size(self.metadata_path)
                if os.path.exists(self.metadata_path)
                else 0
            )

            return {
                "tantivy_docs": doc_count,
                "vector_docs": vector_count,
                "tantivy_size_mb": round(tantivy_size / (1024 * 1024), 2),
                "hnsw_size_mb": round(hnsw_size / (1024 * 1024), 2),
                "metadata_size_mb": round(metadata_size / (1024 * 1024), 2),
                "total_size_mb": round(
                    (tantivy_size + hnsw_size + metadata_size) / (1024 * 1024), 2
                ),
                "chunking": chunk_stats,
            }
        except Exception as e:
            self.logger.error(f"获取索引统计信息失败: {str(e)}")
            return {
                "tantivy_docs": 0,
                "vector_docs": 0,
                "tantivy_size_mb": 0,
                "hnsw_size_mb": 0,
                "metadata_size_mb": 0,
                "total_size_mb": 0,
                "chunking": {"enabled": False, "error": str(e)},
            }

    def _get_chunk_stats(self):
        """获取分块统计信息"""
        try:
            if not hasattr(self, "vector_metadata") or not self.vector_metadata:
                return {
                    "enabled": self.chunk_enabled,
                    "strategy": self.chunk_strategy if self.chunk_enabled else None,
                    "total_vectors": 0,
                    "chunked_docs": 0,
                    "total_chunks": 0,
                    "legacy_docs": 0,
                }

            chunked_docs = set()
            total_chunks = 0
            legacy_docs = set()

            for doc_id, metadata in self.vector_metadata.items():
                if not isinstance(metadata, dict):
                    continue

                is_chunk = metadata.get("is_chunk", False)
                path = metadata.get("path", "")

                if is_chunk:
                    total_chunks += 1
                    if path:
                        chunked_docs.add(path)
                elif path:
                    legacy_docs.add(path)

            return {
                "enabled": self.chunk_enabled,
                "strategy": self.chunk_strategy if self.chunk_enabled else None,
                "chunk_size": self.chunk_size if self.chunk_enabled else None,
                "chunk_overlap": self.chunk_overlap if self.chunk_enabled else None,
                "total_vectors": len(self.vector_metadata),
                "chunked_docs": len(chunked_docs),
                "total_chunks": total_chunks,
                "legacy_docs": len(legacy_docs),
                "chunk_ratio": (
                    round(total_chunks / len(self.vector_metadata), 2)
                    if self.vector_metadata
                    else 0
                ),
            }
        except Exception as e:
            self.logger.debug(f"获取分块统计失败: {e}")
            return {"enabled": self.chunk_enabled, "error": str(e)}

    def optimize_index(self):
        """优化索引性能"""
        try:
            # 优化Tantivy索引
            if hasattr(self, "tantivy_index") and self.tantivy_index:
                with self.tantivy_index.writer() as writer:
                    # 合并段以优化搜索性能
                    writer.commit()
                    self.logger.info("Tantivy索引优化完成")

            # 优化HNSW索引
            if hasattr(self, "hnsw") and self.hnsw:
                # HNSW索引本身不需要特别的优化，但可以调整参数
                self.hnsw.set_ef(200)  # 设置搜索参数
                self.logger.info("HNSW索引参数已优化")

            return True
        except Exception as e:
            self.logger.error(f"索引优化失败: {str(e)}")
            return False

    def validate_index_integrity(self):
        """验证索引完整性"""
        try:
            # 验证Tantivy索引
            if hasattr(self, "tantivy_index") and self.tantivy_index:
                searcher = self.tantivy_index.searcher()
                # num_docs 在新版 tantivy 中是属性而非方法
                num_docs_attr = getattr(searcher, "num_docs", 0)
                if callable(num_docs_attr):
                    doc_count = num_docs_attr()
                else:
                    doc_count = num_docs_attr
                self.logger.info(f"Tantivy索引验证完成，文档数: {doc_count}")

            # 验证向量索引
            if hasattr(self, "hnsw") and self.hnsw and hasattr(self, "vector_metadata"):
                vector_count = len(self.vector_metadata)
                self.logger.info(f"向量索引验证完成，向量数: {vector_count}")

                # 检查元数据与索引的一致性
                indexed_ids = set()
                for i in range(min(self.next_id, 1000)):  # 检查前1000个ID以避免性能问题
                    try:
                        # 尝试获取向量以验证其存在性
                        if i < self.hnsw.get_current_count():
                            indexed_ids.add(i)
                    except (RuntimeError, AttributeError) as e:
                        self.logger.debug(f"检查向量ID {i} 失败: {str(e)}")

                metadata_ids = set(int(k) for k in self.vector_metadata.keys())
                missing_in_metadata = indexed_ids - metadata_ids
                missing_in_index = metadata_ids - indexed_ids

                if missing_in_metadata or missing_in_index:
                    missing_meta = len(missing_in_metadata)
                    missing_idx = len(missing_in_index)
                    self.logger.warning(
                        f"向量索引与元数据不一致: "
                        f"索引中缺失元数据的ID数: {missing_meta}, "
                        f"元数据中缺失索引的ID数: {missing_idx}"
                    )
                else:
                    self.logger.info("向量索引与元数据一致性检查通过")

            return True
        except Exception as e:
            self.logger.error(f"索引完整性验证失败: {str(e)}")
            return False

    def warm_up(self, limit: int = 1000) -> Dict[str, Any]:
        """
        预热索引 - 将热数据加载到内存

        Args:
            limit: 预热的文档数量限制

        Returns:
            预热统计信息
        """
        try:
            stats = {"tantivy_warmed": 0, "vector_warmed": 0, "duration_ms": 0}

            start_time = time.time()

            # 预热 Tantivy 索引
            try:
                searcher = self.tantivy_index.searcher()
                # 执行一个简单查询来加载索引数据
                query = self.tantivy_index.parse_query("*", ["content"])
                _ = searcher.search(query, limit)
                stats["tantivy_warmed"] = limit
                self.logger.info(f"Tantivy索引预热完成，加载 {limit} 个文档")
            except Exception as e:
                self.logger.warning(f"Tantivy索引预热失败: {e}")

            # 预热向量索引
            try:
                if self.hnsw is not None:
                    # HNSW 在第一次查询时会加载，这里我们执行一个虚拟查询
                    dummy_vector = np.zeros(self.vector_dim, dtype=np.float32)
                    labels, distances = self.hnsw.knn_query(dummy_vector, k=1)
                    stats["vector_warmed"] = 1
                    self.logger.info("向量索引预热完成")
            except Exception as e:
                self.logger.warning(f"向量索引预热失败: {e}")

            stats["duration_ms"] = int((time.time() - start_time) * 1000)
            self.logger.info(f"索引预热完成，耗时 {stats['duration_ms']}ms")

            return stats
        except Exception as e:
            self.logger.error(f"索引预热失败: {e}")
            return {"error": str(e)}

    def close(self):
        """关闭索引管理器，释放资源"""
        try:
            # 确保批量模式正确结束（检查属性是否存在，避免初始化失败时出错）
            if hasattr(self, "_batch_mode") and self._batch_mode:
                self.end_batch_mode(commit=True)

            # 保存索引
            self.save_indexes()

            # 释放HNSW索引
            if hasattr(self, "hnsw") and self.hnsw is not None:
                try:
                    # HNSW没有明确的关闭方法，但我们可以删除引用
                    del self.hnsw
                    self.hnsw = None
                except Exception as e:
                    self.logger.warning(f"释放HNSW索引时出错: {e}")

            # 释放Tantivy索引
            if hasattr(self, "tantivy_index") and self.tantivy_index is not None:
                try:
                    # Tantivy索引会在垃圾回收时自动清理
                    del self.tantivy_index
                    self.tantivy_index = None
                except Exception as e:
                    self.logger.warning(f"释放Tantivy索引时出错: {e}")

            self.logger.info("索引管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭索引管理器时出错: {e}")

    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            if hasattr(self, "_batch_mode") and self._batch_mode:
                self.end_batch_mode(commit=True)
            if hasattr(self, "hnsw") and self.hnsw is not None:
                self.save_indexes()
        except Exception as e:
            # 静默处理以避免在析构时抛出异常，但至少记录日志
            try:
                self.logger.debug(f"析构时清理失败（忽略）: {e}")
            except Exception:
                pass  # 如果连日志都失败，就静默忽略
