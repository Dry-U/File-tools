"""
嵌入式模型管理器 - 统一管理 Embedding 和 Reranker 模型
支持 FastEmbed + ColBERT 轻量化方案
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# HuggingFace 镜像
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT


class EmbeddingModelError(Exception):
    """嵌入模型错误基类"""

    pass


class ModelDownloadError(EmbeddingModelError):
    """模型下载失败"""

    pass


class ModelLoadError(EmbeddingModelError):
    """模型加载失败"""

    pass


class EmbeddingModelManager:
    """
    统一管理 Embedding 和 Reranker 模型的生命周期
    """

    def __init__(self, config_loader):
        self.config_loader = config_loader
        self._embedding_model = None
        self._reranker_model = None
        self._embedding_dim = None
        self._reranker_type = None
        self._initialized = False

        # 加载配置
        self._load_config()

    def _load_config(self):
        """加载模型配置"""
        # Embedding 配置
        self.embedding_provider = self.config_loader.get(
            "embedding", "provider", "fastembed"
        ).strip()
        self.embedding_model_name = self.config_loader.get(
            "embedding", "model_name", "BAAI/bge-small-zh-v1.5"
        ).strip()
        self.embedding_cache_dir = self._resolve_cache_dir(
            self.config_loader.get("embedding", "cache_dir", "data/models")
        )
        self.embedding_device = self.config_loader.get(
            "embedding", "device", "cpu"
        ).strip()
        self.embedding_normalize = self.config_loader.getboolean(
            "embedding", "normalize", True
        )
        # 批处理大小上限验证，防止 GPU 显存耗尽
        MAX_BATCH_SIZE = 256
        self.embedding_batch_size = min(
            self.config_loader.getint("embedding", "batch_size", 32), MAX_BATCH_SIZE
        )

        # Reranker 配置
        self.reranker_enabled = self.config_loader.getboolean(
            "reranker", "enabled", True
        )
        self.reranker_model_name = self.config_loader.get(
            "reranker", "model_name", "answerdotai/answerai-colbert-small-v1"
        ).strip()
        self.reranker_cache_dir = self._resolve_cache_dir(
            self.config_loader.get("reranker", "cache_dir", "data/models")
        )
        # Reranker top_k 上限验证
        self.reranker_top_k = min(
            max(self.config_loader.getint("reranker", "top_k", 5), 1), 100
        )

        # 确保缓存目录存在
        os.makedirs(self.embedding_cache_dir, exist_ok=True)
        os.makedirs(self.reranker_cache_dir, exist_ok=True)

        logger.info(f"[EmbeddingManager] Embedding: {self.embedding_model_name}")
        reranker_info = (
            f"Reranker: {self.reranker_model_name} (enabled={self.reranker_enabled})"
        )
        logger.info(f"[EmbeddingManager] {reranker_info}")

    def _resolve_cache_dir(self, cache_dir: str) -> str:
        """解析缓存目录为绝对路径"""
        if not cache_dir:
            return str(Path("data/models").absolute())

        if not os.path.isabs(cache_dir):
            project_root = Path(__file__).parent.parent.parent
            resolved = project_root / cache_dir
        else:
            resolved = Path(cache_dir)

        return str(resolved)

    # ========== Embedding 模型管理 ==========

    def ensure_embedding_loaded(self) -> bool:
        """确保 Embedding 模型已加载"""
        if self._embedding_model is not None:
            return True

        try:
            return self._load_embedding_model()
        except Exception as e:
            logger.error(f"[EmbeddingManager] Embedding 模型加载失败: {e}")
            return False

    def is_embedding_model_cached(self) -> bool:
        """检测 Embedding 模型是否已缓存"""
        model_cache_path = self._get_model_cache_path(
            self.embedding_model_name, self.embedding_cache_dir
        )
        return os.path.exists(model_cache_path)

    def _get_model_cache_path(self, model_name: str, cache_dir: str) -> str:
        """获取模型的缓存路径（优先本地缓存，其次 HF 缓存）"""
        normalized_name = model_name.replace("/", "--")
        flat_name = model_name.replace("/", "_")
        model_tail = model_name.split("/")[-1]

        candidate_paths = [
            Path(cache_dir) / flat_name,
            Path(cache_dir) / f"models--{normalized_name}",
            (
                Path.home()
                / ".cache"
                / "huggingface"
                / "hub"
                / f"models--{normalized_name}"
            ),
        ]

        # FastEmbed / HF 可能将模型放在 snapshots 子目录
        for base in list(candidate_paths):
            candidate_paths.extend(sorted(base.glob("snapshots/*")))

        # 兜底：按模型名尾部在 cache_dir 中模糊匹配
        cache_root = Path(cache_dir)
        if cache_root.exists():
            lowered_tail = model_tail.lower()
            for entry in cache_root.iterdir():
                if lowered_tail in entry.name.lower():
                    candidate_paths.append(entry)
                    candidate_paths.extend(sorted(entry.glob("snapshots/*")))

        for path in candidate_paths:
            if path.exists():
                return str(path)

        return str(Path(cache_dir) / flat_name)  # 返回本地目标路径（即使不存在）

    def _verify_model_integrity(self, model_name: str, cache_dir: str) -> bool:
        """验证模型文件完整性：检查文件存在且大小 > 1MB

        这是基础完整性检查，能检测模型文件被截断或损坏的情况。
        方案C：仅验证文件存在且大小合理。

        Returns:
            True 如果验证通过，False 如果验证失败（但仍然允许使用）
        """
        MIN_MODEL_SIZE = 1024 * 1024  # 1MB

        model_path = self._get_model_cache_path(model_name, cache_dir)
        if not os.path.exists(model_path):
            # 模型可能在 HF 缓存但路径不对，尝试递归搜索
            hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
            hf_path = hf_cache / f"models--{model_name.replace('/', '--')}"
            if hf_path.exists():
                model_path = str(hf_path)

        if not os.path.exists(model_path):
            logger.warning(
                f"[EmbeddingManager] 模型缓存路径不存在: {model_name}, "
                f"可能正在下载或使用内存模式"
            )
            return True  # 不阻止使用，可能是首次下载

        # 检查目录下的文件
        if os.path.isdir(model_path):
            files = []
            for root, dirs, filenames in os.walk(model_path):
                for f in filenames:
                    fp = os.path.join(root, f)
                    if os.path.isfile(fp):
                        files.append(fp)

            if not files:
                logger.warning(f"[EmbeddingManager] 模型目录为空: {model_path}")
                return True

            # 检查最大文件的大小
            max_size = max(os.path.getsize(f) for f in files)
            if max_size < MIN_MODEL_SIZE:
                logger.warning(
                    "[EmbeddingManager] 模型文件异常小: "
                    f"{max_size} bytes < {MIN_MODEL_SIZE} bytes"
                )
                return False

            logger.debug(f"[EmbeddingManager] 模型完整性验证通过: {max_size} bytes")
            return True

        elif os.path.isfile(model_path):
            size = os.path.getsize(model_path)
            if size < MIN_MODEL_SIZE:
                logger.warning(
                    "[EmbeddingManager] 模型文件异常小: "
                    f"{size} bytes < {MIN_MODEL_SIZE} bytes"
                )
                return False
            return True

        return True

    def _load_embedding_model(self) -> bool:
        """加载 Embedding 模型"""
        try:
            from fastembed import TextEmbedding

            logger.info(
                f"[EmbeddingManager] 加载 FastEmbed 模型: {self.embedding_model_name}"
            )

            # 检查模型是否存在，不存在则下载
            if not self.is_embedding_model_cached():
                logger.info("[EmbeddingManager] 模型不存在，使用 FastEmbed 自动下载...")

            # 加载模型（FastEmbed 会自动从镜像下载）
            self._embedding_model = TextEmbedding(
                model_name=self.embedding_model_name,
                cache_dir=self.embedding_cache_dir,
            )

            # 获取向量维度
            self._embedding_dim = self._embedding_model.embedding_size
            dim_info = f"向量维度: {self._embedding_dim}"
            logger.info(f"[EmbeddingManager] FastEmbed 加载成功，{dim_info}")

            # 验证模型文件完整性（方案C：基础存在性检查）
            self._verify_model_integrity(
                self.embedding_model_name, self.embedding_cache_dir
            )

            return True

        except ImportError as e:
            logger.error(f"[EmbeddingManager] FastEmbed 未安装: {e}")
            return False
        except Exception as e:
            logger.error(f"[EmbeddingManager] FastEmbed 加载失败: {e}")
            return False

    def embed(self, texts: List[str]) -> Generator[List[float], None, None]:
        """
        生成文本嵌入向量

        Args:
            texts: 文本列表

        Yields:
            嵌入向量
        """
        if not self.ensure_embedding_loaded():
            raise ModelLoadError("Embedding 模型加载失败")

        try:
            for embedding in self._embedding_model.embed(texts):
                yield (
                    embedding.tolist()
                    if hasattr(embedding, "tolist")
                    else list(embedding)
                )
        except Exception as e:
            logger.error(f"[EmbeddingManager] 生成嵌入向量失败: {e}")
            raise

    # ========== Reranker 模型管理 ==========

    def ensure_reranker_loaded(self) -> bool:
        """确保 Reranker 模型已加载"""
        if not self.reranker_enabled:
            logger.info("[EmbeddingManager] Reranker 未启用")
            return False

        if self._reranker_model is not None:
            return True

        try:
            return self._load_reranker_model()
        except Exception as e:
            logger.error(f"[EmbeddingManager] Reranker 模型加载失败: {e}")
            return False

    def is_reranker_model_cached(self) -> bool:
        """检测 Reranker 模型是否已缓存"""
        model_cache_path = self._get_model_cache_path(
            self.reranker_model_name, self.reranker_cache_dir
        )
        return os.path.exists(model_cache_path)

    def _load_reranker_model(self) -> bool:
        """加载 Reranker 模型"""
        try:
            from fastembed.late_interaction import LateInteractionTextEmbedding

            logger.info(
                f"[EmbeddingManager] 加载 ColBERT 模型: {self.reranker_model_name}"
            )

            # 检查模型是否存在
            if not self.is_reranker_model_cached():
                logger.info(
                    "[EmbeddingManager] ColBERT 模型不存在，使用 FastEmbed 自动下载..."
                )

            # 加载 ColBERT 模型
            self._reranker_model = LateInteractionTextEmbedding(
                model_name=self.reranker_model_name,
                cache_dir=self.reranker_cache_dir,
            )
            self._reranker_type = "colbert"
            logger.info("[EmbeddingManager] ColBERT 模型加载成功")

            # 验证模型文件完整性（方案C：基础存在性检查）
            self._verify_model_integrity(
                self.reranker_model_name, self.reranker_cache_dir
            )

            return True

        except ImportError as e:
            logger.warning(f"[EmbeddingManager] FastEmbed ColBERT 未安装: {e}")
            return False
        except Exception as e:
            logger.error(f"[EmbeddingManager] ColBERT 模型加载失败: {e}")
            return False

    def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        对文档进行重排序

        Args:
            query: 查询字符串
            documents: 文档列表，每个包含 content/path 等字段
            top_k: 返回前 k 个结果

        Returns:
            重排序后的文档列表
        """
        if top_k is None:
            top_k = self.reranker_top_k

        if not self.ensure_reranker_loaded():
            return documents[:top_k]

        try:
            return self._colbert_rerank(query, documents, top_k)
        except Exception as e:
            logger.warning(f"[EmbeddingManager] Rerank 失败: {e}")
            return documents[:top_k]

    def _colbert_rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """使用 ColBERT 进行重排序"""
        import numpy as np

        # 提取文档内容
        doc_contents = []
        for doc in documents:
            content = doc.get("content", "") or doc.get("snippet", "")
            doc_contents.append(content[:512])  # 限制长度

        # 编码
        query_emb = np.array(list(self._reranker_model.embed([query]))[0])
        doc_embs = list(self._reranker_model.embed(doc_contents))

        # 计算 ColBERT MaxSim 分数
        scores = []
        for doc_emb in doc_embs:
            doc_emb = np.array(doc_emb)
            # MaxSim: 每个query token与doc所有token的最大相似度之和
            sim_matrix = np.matmul(query_emb, doc_emb.T)
            max_sims = np.max(sim_matrix, axis=1)
            score = float(np.mean(max_sims))
            scores.append(score)

        # 合并分数并排序
        scored_docs = list(zip(scores, documents))
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # 构建结果
        reranked = []
        for rank, (score, doc) in enumerate(scored_docs[:top_k]):
            new_doc = doc.copy()
            new_doc["rerank_score"] = score
            new_doc["rerank_rank"] = rank + 1
            reranked.append(new_doc)

        return reranked

    # ========== 工具方法 ==========

    @property
    def embedding_dim(self) -> Optional[int]:
        """获取 Embedding 向量维度"""
        if self._embedding_dim is None and self._embedding_model is not None:
            self._embedding_dim = self._embedding_model.embedding_size
        return self._embedding_dim

    def get_model_info(self) -> Dict[str, Any]:
        """获取当前加载的模型信息"""
        return {
            "embedding": {
                "loaded": self._embedding_model is not None,
                "provider": self.embedding_provider,
                "model_name": self.embedding_model_name,
                "dim": self._embedding_dim,
            },
            "reranker": {
                "loaded": self._reranker_model is not None,
                "enabled": self.reranker_enabled,
                "model_name": self.reranker_model_name,
                "type": self._reranker_type,
            },
        }

    def cleanup(self):
        """清理资源"""
        self._embedding_model = None
        self._reranker_model = None
        logger.info("[EmbeddingManager] 资源已清理")
