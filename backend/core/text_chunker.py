#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文本分块模块 - 支持多种分块策略

此模块提供文档分块功能，将长文档切分成适合向量化的chunks，
支持多种分块策略和重叠区域处理。
"""

import re
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """文本块数据结构"""
    content: str           # 块内容
    doc_path: str          # 所属文档路径
    doc_filename: str      # 所属文档文件名
    chunk_index: int       # 在文档中的块索引
    start_pos: int         # 在原文档中的起始位置
    end_pos: int           # 在原文档中的结束位置
    char_count: int        # 字符数
    metadata: Dict[str, Any] = None  # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TextChunker:
    """文本分块器"""

    # 分块策略常量
    STRATEGY_PARAGRAPH = 'paragraph'      # 按段落分块
    STRATEGY_SENTENCE = 'sentence'        # 按句子分块
    STRATEGY_FIXED = 'fixed'              # 固定长度分块
    STRATEGY_SEMANTIC = 'semantic'        # 语义分块（基于段落+长度）

    # 默认配置
    DEFAULT_CHUNK_SIZE = 800              # 默认块大小（字符）
    DEFAULT_CHUNK_OVERLAP = 100           # 默认重叠大小（字符）
    DEFAULT_MIN_CHUNK_SIZE = 100          # 最小块大小
    DEFAULT_MAX_CHUNK_SIZE = 1500         # 最大块大小

    def __init__(
        self,
        strategy: str = 'semantic',
        chunk_size: int = None,
        chunk_overlap: int = None,
        min_chunk_size: int = None,
        max_chunk_size: int = None
    ):
        """
        初始化分块器

        Args:
            strategy: 分块策略，可选 'paragraph', 'sentence', 'fixed', 'semantic'
            chunk_size: 目标块大小（字符数）
            chunk_overlap: 块间重叠大小
            min_chunk_size: 最小块大小
            max_chunk_size: 最大块大小
        """
        self.strategy = strategy
        self.chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
        self.min_chunk_size = min_chunk_size or self.DEFAULT_MIN_CHUNK_SIZE
        self.max_chunk_size = max_chunk_size or self.DEFAULT_MAX_CHUNK_SIZE

        # 策略映射
        self._strategies = {
            self.STRATEGY_PARAGRAPH: self._chunk_by_paragraph,
            self.STRATEGY_SENTENCE: self._chunk_by_sentence,
            self.STRATEGY_FIXED: self._chunk_fixed,
            self.STRATEGY_SEMANTIC: self._chunk_semantic,
        }

        if strategy not in self._strategies:
            raise ValueError(f"未知的分块策略: {strategy}，可用策略: {list(self._strategies.keys())}")

        logger.info(f"文本分块器初始化: 策略={strategy}, 块大小={self.chunk_size}, 重叠={self.chunk_overlap}")

    def chunk_document(
        self,
        content: str,
        doc_path: str,
        doc_filename: str,
        doc_metadata: Dict[str, Any] = None
    ) -> List[TextChunk]:
        """
        对文档进行分块

        Args:
            content: 文档内容
            doc_path: 文档路径
            doc_filename: 文档文件名
            doc_metadata: 文档元数据

        Returns:
            TextChunk列表
        """
        if not content or not content.strip():
            return []

        # 清理内容
        content = self._clean_content(content)

        # 如果内容很短，直接作为一个块
        if len(content) <= self.chunk_size:
            return [TextChunk(
                content=content,
                doc_path=doc_path,
                doc_filename=doc_filename,
                chunk_index=0,
                start_pos=0,
                end_pos=len(content),
                char_count=len(content),
                metadata=doc_metadata or {}
            )]

        # 调用对应的分块策略
        chunk_func = self._strategies[self.strategy]
        chunks = chunk_func(content)

        # 包装为TextChunk对象
        text_chunks = []
        for i, (chunk_text, start_pos, end_pos) in enumerate(chunks):
            if len(chunk_text.strip()) >= self.min_chunk_size:
                text_chunks.append(TextChunk(
                    content=chunk_text,
                    doc_path=doc_path,
                    doc_filename=doc_filename,
                    chunk_index=i,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    char_count=len(chunk_text),
                    metadata={
                        **(doc_metadata or {}),
                        'total_chunks': len(chunks),
                        'strategy': self.strategy
                    }
                ))

        logger.debug(f"文档分块完成: {doc_filename} -> {len(text_chunks)} 个块")
        return text_chunks

    def _clean_content(self, content: str) -> str:
        """清理内容"""
        # 移除多余的空白字符
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = re.sub(r'[ \t]+', ' ', content)
        return content.strip()

    def _chunk_by_paragraph(self, content: str) -> List[tuple]:
        """按段落分块"""
        # 按段落分割（支持多种换行格式）
        paragraphs = re.split(r'\n\s*\n', content)

        chunks = []
        current_pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            start_pos = content.find(para, current_pos)
            end_pos = start_pos + len(para)
            current_pos = end_pos

            # 如果段落太长，进一步切分
            if len(para) > self.max_chunk_size:
                sub_chunks = self._split_large_chunk(para, start_pos)
                chunks.extend(sub_chunks)
            else:
                chunks.append((para, start_pos, end_pos))

        return self._merge_small_chunks(chunks)

    def _chunk_by_sentence(self, content: str) -> List[tuple]:
        """按句子分块"""
        # 中文句子结束符
        sentence_endings = r'[。！？\.\!\?]'

        sentences = re.split(f'({sentence_endings})', content)

        chunks = []
        current_chunk = []
        current_length = 0
        chunk_start = 0
        current_pos = 0

        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i]
            ending = sentences[i + 1] if i + 1 < len(sentences) else ''
            full_sentence = sentence + ending

            if current_length + len(full_sentence) > self.chunk_size and current_chunk:
                # 保存当前块
                chunk_text = ''.join(current_chunk)
                chunks.append((chunk_text, chunk_start, current_pos))

                # 开始新块，保留重叠
                overlap_text = self._get_overlap(current_chunk)
                current_chunk = [overlap_text, full_sentence]
                current_length = len(overlap_text) + len(full_sentence)
                chunk_start = current_pos - len(overlap_text)
            else:
                current_chunk.append(full_sentence)
                current_length += len(full_sentence)

            current_pos += len(full_sentence)

        # 处理剩余内容
        if current_chunk:
            chunk_text = ''.join(current_chunk)
            chunks.append((chunk_text, chunk_start, current_pos))

        return chunks

    def _chunk_fixed(self, content: str) -> List[tuple]:
        """固定长度分块"""
        chunks = []
        start = 0
        content_length = len(content)

        while start < content_length:
            end = min(start + self.chunk_size, content_length)

            # 如果不是最后一块，尝试在单词/句子边界处分割
            if end < content_length:
                end = self._find_nearest_boundary(content, end)

            chunk_text = content[start:end].strip()
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append((chunk_text, start, end))

            # 下一块的起点（考虑重叠）
            start = end - self.chunk_overlap if end < content_length else end

        return chunks

    def _chunk_semantic(self, content: str) -> List[tuple]:
        """
        语义分块策略

        结合段落边界和长度限制，优先保持段落完整，
        对超长段落进行智能切分。
        """
        # 首先按段落分割
        paragraphs = re.split(r'\n\s*\n', content)

        chunks = []
        current_chunk_paras = []
        current_length = 0
        chunk_start = 0
        current_pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_start = content.find(para, current_pos)
            para_end = para_start + len(para)

            # 如果单个段落就超过最大限制，需要切分段落
            if len(para) > self.max_chunk_size:
                # 先保存当前累积的内容
                if current_chunk_paras:
                    chunk_text = '\n\n'.join(current_chunk_paras)
                    chunks.append((chunk_text, chunk_start, para_start))
                    current_chunk_paras = []
                    current_length = 0

                # 切分大段落
                sub_chunks = self._split_paragraph_smart(para, para_start)
                chunks.extend(sub_chunks)
                chunk_start = para_end
                current_pos = para_end
                continue

            # 如果加入当前段落后超出限制，保存当前块并开始新块
            if current_length + len(para) > self.chunk_size and current_chunk_paras:
                chunk_text = '\n\n'.join(current_chunk_paras)
                chunks.append((chunk_text, chunk_start, para_start))

                # 新块从当前段落开始
                current_chunk_paras = [para]
                current_length = len(para)
                chunk_start = para_start
            else:
                current_chunk_paras.append(para)
                current_length += len(para) + 2  # +2 for '\n\n'

            current_pos = para_end

        # 处理最后剩余的段落
        if current_chunk_paras:
            chunk_text = '\n\n'.join(current_chunk_paras)
            last_para_start = content.find(current_chunk_paras[0], chunk_start)
            chunks.append((chunk_text, chunk_start, current_pos))

        return chunks

    def _split_paragraph_smart(self, paragraph: str, start_offset: int) -> List[tuple]:
        """智能切分长段落"""
        chunks = []

        # 优先按句子切分
        sentences = re.split(r'([。！？\.\!\?]\s*)', paragraph)

        current_chunk = []
        current_length = 0
        chunk_start = 0
        pos = 0

        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i]
            sep = sentences[i + 1] if i + 1 < len(sentences) else ''
            full = sentence + sep

            if current_length + len(full) > self.chunk_size and current_chunk:
                chunk_text = ''.join(current_chunk)
                chunks.append((chunk_text, start_offset + chunk_start, start_offset + pos))
                current_chunk = [full]
                current_length = len(full)
                chunk_start = pos + len(sentence)
            else:
                current_chunk.append(full)
                current_length += len(full)

            pos += len(full)

        if current_chunk:
            chunk_text = ''.join(current_chunk)
            chunks.append((chunk_text, start_offset + chunk_start, start_offset + len(paragraph)))

        return chunks

    def _split_large_chunk(self, text: str, start_offset: int) -> List[tuple]:
        """将大块切分成合适大小"""
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            if end < len(text):
                end = self._find_nearest_boundary(text, end)

            chunk_text = text[start:end].strip()
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append((chunk_text, start_offset + start, start_offset + end))

            start = end

        return chunks

    def _find_nearest_boundary(self, text: str, pos: int) -> int:
        """在位置附近找到最近的边界（句子结束符或空格）"""
        # 向前查找最大50个字符
        search_range = min(50, len(text) - pos)

        for i in range(search_range):
            if pos + i < len(text) and text[pos + i] in '。！？.!?\n':
                return pos + i + 1

        # 如果没找到句子边界，找空格
        for i in range(search_range):
            if pos + i < len(text) and text[pos + i] == ' ':
                return pos + i + 1
            if pos - i > 0 and text[pos - i] == ' ':
                return pos - i

        return pos

    def _get_overlap(self, chunks: List[str]) -> str:
        """获取块间重叠文本"""
        if not chunks:
            return ''

        overlap_text = ''
        total_len = 0

        # 从后向前取文本，直到达到重叠大小
        for chunk in reversed(chunks):
            if total_len + len(chunk) <= self.chunk_overlap:
                overlap_text = chunk + overlap_text
                total_len += len(chunk)
            else:
                remaining = self.chunk_overlap - total_len
                if remaining > 0:
                    overlap_text = chunk[-remaining:] + overlap_text
                break

        return overlap_text

    def _merge_small_chunks(self, chunks: List[tuple]) -> List[tuple]:
        """合并过小的块"""
        if not chunks:
            return chunks

        merged = []
        current_chunk = list(chunks[0])

        for i in range(1, len(chunks)):
            chunk_text, chunk_start, chunk_end = chunks[i]

            if len(current_chunk[0]) + len(chunk_text) <= self.chunk_size:
                # 合并
                current_chunk[0] += '\n\n' + chunk_text
                current_chunk[2] = chunk_end
            else:
                merged.append(tuple(current_chunk))
                current_chunk = list(chunks[i])

        merged.append(tuple(current_chunk))
        return merged


# 便捷函数
def chunk_document(
    content: str,
    doc_path: str,
    doc_filename: str,
    strategy: str = 'semantic',
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    **kwargs
) -> List[TextChunk]:
    """
    便捷分块函数

    Args:
        content: 文档内容
        doc_path: 文档路径
        doc_filename: 文档文件名
        strategy: 分块策略
        chunk_size: 块大小
        chunk_overlap: 重叠大小
        **kwargs: 其他参数

    Returns:
        TextChunk列表
    """
    chunker = TextChunker(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        **kwargs
    )
    return chunker.chunk_document(content, doc_path, doc_filename)
