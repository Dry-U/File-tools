# src/core/rag_pipeline.py
import os
import re
import secrets
from typing import Dict, List, Any, Optional

# 修复 torch DLL 加载问题
try:
    import torch
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')
    if os.path.exists(torch_lib_path) and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(torch_lib_path)
except Exception:
    pass

from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
from backend.core.model_manager import ModelManager
from backend.core.search_engine import SearchEngine
from backend.core.vram_manager import VRAMManager
from backend.core.chat_history_db import ChatHistoryDB

logger = setup_logger()

DEFAULT_PROMPT = (
    "你是一名专业的中文文档分析助理。请严格基于【文档集合】中的内容，对用户的【问题】提供准确、全面的回答。\n\n"
    "注意事项：\n"
    "1. 严格基于文档内容回答，不得编造任何信息。\n"
    "2. 重点提取文档中的知识内容、技术细节、数据信息、方法论等。\n"
    "3. 如果用户询问某人、某事出现在哪里，或询问来源，请明确指出文件名。\n"
    "4. 对于论文、技术文档等，可以提及作者、学校、机构等背景信息，但要重点聚焦内容。\n"
    "5. 如果文档中没有相关信息，请直接说明未找到。\n"
    "6. 回答要简洁明了，突出关键信息，避免冗长的引用。\n\n"
    "【文档集合】:\n{context}\n\n"
    "【问题】: {question}\n\n"
    "请提供一个准确、全面、简洁的回答："
)


class RAGPipeline:
    """本地RAG问答管道，依赖检索结果与模型推理"""

    def __init__(self, model_manager: ModelManager, config_loader: ConfigLoader, search_engine: SearchEngine):
        self.model_manager = model_manager
        self.config_loader = config_loader
        self.search_engine = search_engine
        self.vram_manager = VRAMManager(config_loader)

        try:
            rag_config = config_loader.get('rag') or {}
        except Exception:
            rag_config = {}

        self.max_docs = int(rag_config.get('max_docs', 3))
        self.max_context_chars = int(rag_config.get('max_context_chars', 1200))
        default_total = self.max_context_chars * self.max_docs
        self.max_context_chars_total = int(rag_config.get('max_context_chars_total', default_total))
        self.max_history_turns = int(rag_config.get('max_history_turns', 6))
        self.max_history_chars = int(rag_config.get('max_history_chars', 800))
        self.max_output_tokens = int(rag_config.get('max_output_tokens', 512))
        self.temperature = float(rag_config.get('temperature', 0.7))
        self.prompt_template = rag_config.get('prompt_template', DEFAULT_PROMPT)
        self.fallback_response = rag_config.get(
            'fallback_response',
            "你好！我是 FileTools Copilot，当前检索没有找到相关文档，请告诉我需要查询的内容。"
        )
        self.context_exhausted_response = rag_config.get(
            'context_exhausted_response',
            "对话过长，为避免超出上下文，请说‘重置’或简要概括后再继续。"
        )
        self.reset_response = rag_config.get(
            'reset_response',
            "已清空上下文，可以重新开始提问。"
        )
        self.greeting_response = rag_config.get('greeting_response', self.fallback_response)
        phrases = rag_config.get('greeting_keywords', []) or []
        if isinstance(phrases, str):
            phrases = [p.strip() for p in phrases.split(',') if p.strip()]
        self.greeting_keywords = [p.lower() for p in phrases if p]

        reset_cmds = rag_config.get('reset_commands', ['重置', '清空上下文', 'reset', 'restart']) or []
        self.reset_commands = [c.strip().lower() for c in reset_cmds if c]

        # Use SQLite for chat history persistence
        self.chat_db = ChatHistoryDB()

    def _adjust_context_for_memory(self, doc_budget: int) -> int:
        """Adjust document budget based on memory constraints"""
        # 使用VRAMManager的新功能来动态调整上下文大小
        adjusted_budget = self.vram_manager.adjust_context_size(doc_budget)
        return adjusted_budget

    @staticmethod
    def _render_template(template: str, query: str) -> str:
        if not template:
            return ''
        query_text = (query or '').strip()
        try:
            return template.replace('{query}', query_text)
        except Exception:
            return template

    @staticmethod
    def _is_noise_query(query: str) -> bool:
        """Detect inputs that are too short or repetitive to search meaningfully."""
        normalized = re.sub(r'\s+', '', query or '')
        if not normalized:
            return True
        alnum_text = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]', '', normalized)
        if not alnum_text:
            return True
        if len(alnum_text) <= 1:
            return True
        unique_chars = set(alnum_text.lower())
        if len(alnum_text) <= 2 and len(unique_chars) == 1:
            return True
        return False

    @staticmethod
    def _strip_tags(text: str) -> str:
        clean = re.sub(r'<[^>]+>', '', text or '')
        return clean.replace('\xa0', ' ').strip()

    def _build_history(self, session_id: str, budget: int) -> (str, int):
        # 从数据库获取会话历史
        messages = self.chat_db.get_session_messages(session_id)
        if not messages or budget <= 0:
            return '', 0

        # 构建问答对
        history = []
        current_q, current_a = None, None
        for msg in messages:
            if msg['role'] == 'user':
                if current_q is not None:
                    history.append({'q': current_q, 'a': current_a or ''})
                current_q = msg['content']
                current_a = None
            elif msg['role'] == 'assistant':
                current_a = msg['content']
        if current_q is not None:
            history.append({'q': current_q, 'a': current_a or ''})

        if not history:
            return '', 0

        # 按时间倒序获取最近的对话轮次
        turns = history[-self.max_history_turns:]
        used = 0
        parts: List[str] = []

        for idx, turn in enumerate(turns, start=1):
            q = turn.get('q', '') or ''
            a = turn.get('a', '') or ''

            # 改进：创建更结构化的对话历史表示
            block = f"【上文{idx}】用户: {q}\n助手: {a}"

            if used + len(block) > budget:
                # 如果块太大，尝试截断以保留更多上下文
                remaining = budget - used
                if remaining <= 0:
                    break
                # 截断较长的对话内容，但保留结构
                if len(block) > remaining:
                    # 优先保留问题部分，然后是答案
                    question_len = len(q)
                    if question_len >= remaining:
                        # 问题部分就占满了预算，只保留部分问题
                        block = f"【上文{idx}】用户: {q[:remaining-10]}..."
                    else:
                        # 保留完整问题，部分答案
                        remaining_for_answer = remaining - question_len - 20  # 预留空间给标记和格式
                        if remaining_for_answer > 0:
                            answer_snippet = a[:remaining_for_answer] if len(a) > remaining_for_answer else a
                            block = f"【上文{idx}】用户: {q}\n助手: {answer_snippet}"
                        else:
                            block = f"【上文{idx}】用户: {q[:question_len + remaining_for_answer]}..."

                # 确保最终块不超过预算
                if len(block) > remaining:
                    block = block[:remaining]

            parts.append(block)
            used += len(block)
            if used >= budget:
                break

        return "\n".join(parts), used

    def _remember_turn(self, session_id: str, query: str, answer: str) -> None:
        # 确保会话存在
        if not self.chat_db.session_exists(session_id):
            self.chat_db.create_session(session_id)

        # 保存用户消息
        self.chat_db.add_message(session_id, 'user', query)
        # 保存助手消息
        self.chat_db.add_message(session_id, 'assistant', answer)

        # 注意：数据库层面不自动清理旧消息，保留完整历史
        # 上下文截断在 _build_history 中根据预算处理

    def _reset_session(self, session_id: str) -> None:
        self.chat_db.delete_session(session_id)

    @staticmethod
    def _has_query_overlap(cleaned: str, query: str) -> bool:
        """Check if cleaned text (or filename/path) contains meaningful overlap with query keywords/names."""
        if not cleaned or not query:
            return False

        def _normalize(txt: str) -> str:
            # remove spaces, underscores, hyphens and common punctuation to improve filename matching
            return re.sub(r'[\s_\-，。；、,.!?:；:]+', '', txt.lower())

        text_norm = _normalize(cleaned)
        q_norm = _normalize(query)

        if len(q_norm) >= 2 and q_norm in text_norm:
            return True

        # Split by common separators to get tokens; keep tokens length>=2
        tokens = re.split(r'[\s,;，。；、_\-]+', query)
        for t in tokens:
            t_norm = _normalize(t)
            if len(t_norm) >= 2 and t_norm in text_norm:
                return True
        return False

    def _collect_documents(self, query: str) -> List[Dict[str, Any]]:
        """高级文档收集流程，集成多级RAG优化策略"""
        try:
            # 尝试获取缓存结果以提高性能
            cache_key = f"search_{query[:50]}"
            results = self.vram_manager.get_cached_result(cache_key)

            if results is None:
                # 使用扩展查询来提高召回率
                search_queries = [query]

                # 如果查询是缩写或短词，尝试不同的变体
                if len(query) <= 5 or query.isupper():
                    # 添加小写版本
                    search_queries.append(query.lower())
                    # 添加首字母大写版本
                    search_queries.append(query.capitalize())

                all_results = []
                seen_paths = set()

                for search_query in search_queries:
                    query_results = self.search_engine.search(search_query) or []
                    for res in query_results:
                        path = res.get('path', '')
                        if path and path not in seen_paths:
                            seen_paths.add(path)
                            all_results.append(res)

                results = all_results
                if results:
                    self.vram_manager.cache_result(cache_key, results, len(results))
            else:
                # 更新缓存访问时间
                self.vram_manager.get_cached_result(cache_key)
        except Exception as e:
            logger.error(f"文档收集过程中发生错误: {str(e)}")
            results = []

        try:
            # 多级文档处理流程
            all_candidates: List[Dict[str, Any]] = []
            seen_paths = set()

            for res in results:
                try:
                    path = res.get('path', '')
                    if path and path.lower() in seen_paths:
                        continue
                    if path:
                        seen_paths.add(path.lower())

                    # 从索引获取完整内容
                    full_content = self.search_engine.index_manager.get_document_content(path) if hasattr(self.search_engine, 'index_manager') else ''
                    if full_content:
                        cleaned = self._strip_tags(full_content)
                    else:
                        raw_content = res.get('content') or ''
                        snippet = res.get('snippet') or ''
                        cleaned = self._strip_tags(raw_content) if raw_content else self._strip_tags(snippet)

                    if path:
                        filename = os.path.basename(path)
                    else:
                        filename = res.get('filename') or res.get('file_name') or '未知文件'

                    # 内容预处理：智能分块和语义增强
                    processed_content = self._preprocess_content(cleaned, query)

                    # 内容提炼：提取关键信息片段
                    max_allowed_chars = self.vram_manager.adjust_context_size(self.max_context_chars)
                    if len(processed_content) > max_allowed_chars:
                        if any(keyword in query.lower() for keyword in ['摘要', '概述', '总结', '概要', '总结', 'abstract', 'summary', 'overview']):
                            processed_content = self._generate_document_summary(processed_content, max_chars=max_allowed_chars)
                        else:
                            processed_content = self._extract_relevant_fragments(processed_content, query, max_allowed_chars)

                    # 计算多维度相关性得分
                    relevance_score = self._calculate_multidimensional_relevance(query, processed_content, res, filename)

                    all_candidates.append({
                        'path': path,
                        'filename': filename,
                        'score': float(res.get('score', 0.0)),
                        'relevance_score': relevance_score,
                        'content': processed_content,
                        'original_score': float(res.get('score', 0.0)),  # 保留原始搜索得分
                        'semantic_score': self._calculate_semantic_relevance(query, processed_content)  # 语义相关性得分
                    })
                except Exception as e:
                    logger.warning(f"处理搜索结果时出现错误，跳过该结果: {str(e)}")
                    continue

            # 使用多标准排序（原始得分、语义得分、相关性得分）
            all_candidates.sort(key=lambda x: (
                x['relevance_score'] * 0.5 +  # 主要权重
                x['semantic_score'] * 0.3 +   # 语义相关性权重
                x['original_score'] * 0.2     # 原始搜索得分权重
            ), reverse=True)

            # 选择最相关的文档，实现信息聚合和冲突检测
            documents = self._select_optimal_documents(all_candidates)
            return documents
        except Exception as e:
            logger.error(f"收集文档过程中发生严重错误: {str(e)}")
            return []

    def _preprocess_content(self, content: str, query: str) -> str:
        """内容预处理：智能分块、关键词增强"""
        import re

        # 1. 文本分块：将文档分成逻辑段落
        paragraphs = re.split(r'\n\s*\n|[\n。！？.!?]', content)

        # 2. 识别重要段落：标题、摘要、结论等
        important_segments = []
        regular_segments = []

        for para in paragraphs:
            if para.strip():
                para_lower = para.lower()
                # 检查是否为重要部分
                if any(keyword in para_lower for keyword in ['摘要', 'abstract', '结论', 'conclusion', '总结', '引言', 'introduction', '标题']):
                    important_segments.append(para.strip())
                else:
                    regular_segments.append(para.strip())

        # 3. 按重要性组织内容
        organized_content = "\n\n".join(important_segments + regular_segments)

        # 4. 为查询相关的词汇添加上下文
        query_words = set(re.findall(r'\w+', query.lower()))
        enhanced_content = organized_content

        for word in query_words:
            # 为查询词添加上下文标记，提高其在最终回答中的突出程度
            enhanced_content = re.sub(
                r'\b(' + re.escape(word) + r')\b',
                f"[QUERY_TERM]{word}[/QUERY_TERM]",
                enhanced_content,
                flags=re.IGNORECASE
            )

        return enhanced_content

    def _calculate_multidimensional_relevance(self, query: str, content: str, original_result: Dict, filename: str) -> float:
        """计算多维度相关性得分，强化文件名匹配权重"""
        import re

        # 基础得分
        base_score = float(original_result.get('score', 0.0))

        # 关键词匹配得分
        query_lower = query.lower()
        content_lower = content.lower()
        query_keywords = set(re.findall(r'\w+', query_lower))
        content_keywords = set(re.findall(r'\w+', content_lower))
        keyword_overlap = len(query_keywords.intersection(content_keywords))
        keyword_score = keyword_overlap * 2.0  # 每个匹配关键词2分

        # === 强化文件名相关性得分 ===
        filename_lower = filename.lower()
        filename_relevance = 0.0

        # 核心优化：如果查询词完全或大部分包含在文件名中，则给予高分
        if query_lower in filename_lower:
            filename_relevance = 30.0 # 给予较高的基础分
        else:
            # 检查查询词中有多少包含在文件名中
            matched_in_filename = sum(1 for kw in query_keywords if kw in filename_lower)
            if matched_in_filename > 0:
                # 根据匹配比例给予分数
                match_ratio = matched_in_filename / max(len(query_keywords), 1) # 避免除以零
                filename_relevance = 10.0 + 20.0 * match_ratio # 基础10分，最多再加20分

        # 位置加权得分（如果内容中包含查询词）
        position_score = 0.0
        if query_lower in content_lower:
            position_score = 5.0 # 稍微提高一点
        else:
            # 检查是否有查询关键词的匹配
            for kw in query_keywords:
                if kw in content_lower:
                    position_score += 2.0 # 稍微提高一点
                    break

        # 综合得分计算 - 调整权重，让文件名匹配更重要
        total_score = (
            base_score * 0.2 +           # 原始搜索得分权重降低到20%
            keyword_score * 0.2 +        # 关键词匹配权重降低到20%
            position_score * 0.1 +       # 位置相关性权重降低到10%
            filename_relevance * 0.5     # 文件名相关性权重提高到50% !!
        )

        return min(total_score, 100.0)  # 限制在合理范围内

    def _calculate_semantic_relevance(self, query: str, content: str) -> float:
        """计算语义相关性得分（使用实际的嵌入模型）"""
        try:
            # 检查是否已初始化嵌入模型
            if hasattr(self.search_engine, 'index_manager') and self.search_engine.index_manager:
                embedding_model = getattr(self.search_engine.index_manager, 'embedding_model', None)
                if embedding_model:
                    # 截断内容以适应模型输入限制
                    max_content_len = 2000  # 大多数嵌入模型的限制
                    if len(content) > max_content_len:
                        content = content[:max_content_len] + "..."

                    # 计算查询和内容的嵌入向量
                    query_embedding = next(embedding_model.embed([query]))
                    content_embedding = next(embedding_model.embed([content]))

                    # 计算余弦相似度
                    from sklearn.metrics.pairwise import cosine_similarity
                    import numpy as np

                    query_vec = np.array(query_embedding).reshape(1, -1)
                    content_vec = np.array(content_embedding).reshape(1, -1)

                    similarity = cosine_similarity(query_vec, content_vec)[0][0]

                    # 转换为百分制
                    return float(similarity * 100.0)

        except Exception as e:
            # 如果嵌入模型不可用，则回退到Jaccard相似度计算
            logger.warning(f"嵌入模型计算语义相关性失败，使用回退方法: {e}")

        # 回退到简化的Jaccard相似度计算
        import re
        query_tokens = set(re.findall(r'\w+', query.lower()))
        content_tokens = set(re.findall(r'\w+', content.lower()))

        if not query_tokens or not content_tokens:
            return 0.0

        intersection = len(query_tokens.intersection(content_tokens))
        union = len(query_tokens.union(content_tokens))

        if union == 0:
            return 0.0

        jaccard_similarity = intersection / union
        return jaccard_similarity * 100.0  # 转换为百分制

    def _select_optimal_documents(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """选择最佳文档，实现信息聚合和冲突检测"""
        if not candidates:
            return []

        # 信息聚合：合并相似内容的文档
        aggregated_docs = []
        processed_content_hashes = set()

        for candidate in candidates:
            # 创建内容的简短哈希以便于比较
            content_hash = hash(candidate['content'][:100])  # 只使用内容的前100字符做哈希

            # 如果内容与已选择的文档相似度高，则跳过（避免重复信息）
            if content_hash not in processed_content_hashes:
                # 添加证据标记，便于AI理解信息来源
                enhanced_content = f"[文档证据来源: {candidate['filename']}]\n{candidate['content']}"
                candidate['content'] = enhanced_content
                aggregated_docs.append(candidate)
                processed_content_hashes.add(content_hash)

                if len(aggregated_docs) >= self.max_docs:
                    break

        return aggregated_docs

    def _extract_relevant_fragments(self, content: str, query: str, max_chars: int) -> str:
        """
        智能提取与查询最相关的内容片段，而不是固定位置的片段
        """
        # 将内容分割成段落或句子
        import re
        # 根据换行符、句号等分割
        paragraphs = re.split(r'\n\s*\n|[\n。！？.!?]', content)

        # 为每个段落计算相关性得分
        paragraph_scores = []
        query_lower = query.lower()
        query_keywords = set(re.findall(r'\w+', query_lower))  # 提取查询关键词

        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue
            para_lower = para.lower()
            score = 0

            # 基于关键词匹配的得分
            para_keywords = set(re.findall(r'\w+', para_lower))
            common_keywords = query_keywords.intersection(para_keywords)
            score += len(common_keywords) * 2  # 关键词匹配得分

            # 基于查询在段落中的出现频率
            for qword in query_keywords:
                score += para_lower.count(qword)

            # 基于字符长度的奖励（避免选择过短的段落）
            if len(para) > 20:
                score += 1
            if len(para) > 50:
                score += 1

            paragraph_scores.append((score, i, para.strip()))

        # 按得分排序
        paragraph_scores.sort(key=lambda x: x[0], reverse=True)

        # 选择得分最高的段落，直到达到最大字符限制
        selected_fragments = []
        total_chars = 0

        for score, idx, paragraph in paragraph_scores:
            if score <= 0:  # 跳过得分低的段落
                continue
            if len(paragraph) + total_chars > max_chars:
                # 如果加上这个段落会超出限制，尝试截断它
                remaining_chars = max_chars - total_chars
                if remaining_chars > 10:  # 如果还有足够的空间
                    truncated_para = paragraph[:remaining_chars-3] + "..."
                    selected_fragments.append(truncated_para)
                    break
            else:
                selected_fragments.append(paragraph)
                total_chars += len(paragraph)

            # 添加少量上下文信息
            if total_chars >= max_chars * 0.8:  # 达到80%限制就停止
                break

        # 在片段间添加分隔符
        result = "\n\n--- 相关片段 ---\n\n".join(selected_fragments)

        # 如果结果仍然太长，使用之前的截断方法作为备用
        if len(result) > max_chars:
            head_size = min(max_chars // 3, 800)
            mid_size = max_chars // 3
            tail_size = max_chars - head_size - mid_size - 6
            if tail_size > 0:
                mid_start = (len(result) - mid_size) // 2
                mid_end = mid_start + mid_size
                result = result[:head_size] + '\n...[内容省略]...\n' + result[mid_start:mid_end] + '\n...[内容省略]...\n' + result[-tail_size:]
            else:
                head_size = min(max_chars // 2, 1000)
                tail_size = max_chars - head_size - 3
                if tail_size > 0:
                    result = result[:head_size] + '...' + result[-tail_size:]
                else:
                    result = result[:max_chars - 3] + '...'

        return result

    def _generate_document_summary(self, content: str, max_summary_chars: int = 500) -> str:
        """
        生成文档的结构化摘要，突出关键信息
        """
        import re
        # 尝试提取文档的关键部分：标题、摘要、引言、结论、参考文献前的部分等
        lines = content.split('\n')

        # 寻找可能的关键部分
        title_section = ""
        abstract_section = ""
        intro_section = ""
        conclusion_section = ""
        main_content = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 检查标题（通常在文档开头）
            if not title_section and len(line) > 5 and len(line) < 100 and i < 10:
                title_section = line
                i += 1
                continue

            # 检查摘要部分
            if re.search(r'摘要|abstract', line.lower()):
                j = i + 1
                while j < len(lines) and j < i + 10:  # 摘要通常不会太长
                    sub_line = lines[j].strip()
                    if sub_line and not re.search(r'引言|intro|正文|正文|1\.|一、', sub_line.lower()):
                        abstract_section += sub_line + " "
                        j += 1
                    else:
                        break
                i = j
                continue

            # 检查引言部分
            if re.search(r'引言|介绍|intro|introduction|背景|background', line.lower()):
                j = i + 1
                while j < len(lines) and j < i + 15:  # 引言通常不会太长
                    sub_line = lines[j].strip()
                    if sub_line and not re.search(r'方法|method|材料|materials|实验|experiment|结论|conclusion', sub_line.lower()):
                        intro_section += sub_line + " "
                        j += 1
                    else:
                        break
                i = j
                continue

            # 检查结论部分
            if re.search(r'结论|conclusion|总结|summary|讨论|discussion', line.lower()):
                j = i + 1
                while j < len(lines) and j < i + 15:  # 结论通常不会太长
                    sub_line = lines[j].strip()
                    if sub_line and not re.search(r'参考文献|references|致谢|acknowledgments', sub_line.lower()):
                        conclusion_section += sub_line + " "
                        j += 1
                    else:
                        break
                i = j
                continue

            i += 1

        # 构建摘要
        summary_parts = []
        if title_section:
            summary_parts.append(f"标题: {title_section[:200]}")
        if abstract_section:
            summary_parts.append(f"摘要: {abstract_section[:300]}")
        if intro_section:
            summary_parts.append(f"引言: {intro_section[:200]}")
        if conclusion_section:
            summary_parts.append(f"结论: {conclusion_section[:300]}")

        # 如果关键部分不够，补充一些内容
        if len(" ".join(summary_parts)) < max_summary_chars and content:
            remaining_content = content[:max_summary_chars - len(" ".join(summary_parts))]
            if remaining_content:
                summary_parts.append(f"其他内容: {remaining_content}")

        summary = "\n\n".join(summary_parts)

        # 确保摘要不超过最大长度
        if len(summary) > max_summary_chars:
            summary = summary[:max_summary_chars] + "..."

        return summary

    def _build_prompt(self, query: str, documents: List[Dict[str, Any]], history_text: str, doc_budget: Optional[int]) -> str:
        """Build RAG prompt from query, documents, and history"""
        if not documents and not history_text:
            return ''

        context_sections = []
        entity_instruction = self._extract_key_entities(documents)

        if history_text:
            context_sections.append(f"对话历史（最近）:\n{history_text}")

        context_budget = self._calculate_context_budget(doc_budget)
        used_chars = len(history_text) if history_text else 0

        for doc in documents:
            if used_chars >= context_budget:
                break

            section = self._format_document_section(doc)
            section = self._truncate_content_if_needed(section, doc.get('content', ''), context_budget, used_chars)

            if not section:
                continue

            context_sections.append(section)
            used_chars += len(section)

        context_text = "\n\n".join(context_sections)
        logger.info(f"Constructed context length: {len(context_text)}")
        logger.debug(f"Context snippet: {context_text[:200]}...")

        if entity_instruction:
            context_text = entity_instruction + "\n" + context_text

        return self._format_prompt_with_template(context_text, query)

    def _extract_key_entities(self, documents: List[Dict[str, Any]]) -> str:
        """Extract key entities (names/keywords from filenames) for prompt enhancement"""
        key_entities = []
        for doc in documents:
            fname = doc.get('filename', '')
            if not fname:
                continue

            name_only = self._remove_file_extension(fname)
            if name_only:
                entities = self._parse_entities_from_filename(name_only)
                key_entities.extend(entities)

        if key_entities:
            unique_entities = list(set(key_entities))
            return f"\n    重要实体名单（禁止截断）：{', '.join(unique_entities)}\n"
        return ""

    def _remove_file_extension(self, filename: str) -> str:
        """Remove file extension from filename"""
        for ext in ['.pdf', '.docx', '.doc', '.txt', '.md', '.xlsx', '.xls', '.pptx', '.ppt']:
            if filename.lower().endswith(ext):
                return filename[:-len(ext)]
        return filename

    def _parse_entities_from_filename(self, name_only: str) -> List[str]:
        """Parse entities from filename"""
        entities = []

        # Strategy 1: Extract after underscore (usually author name)
        if '_' in name_only:
            parts = name_only.rsplit('_', 1)
            if len(parts) > 1 and parts[1]:
                entities.append(parts[1])

        # Strategy 2: Short names that look like entities
        if 2 <= len(name_only) <= 10:
            entities.append(name_only)

        return entities

    def _format_document_section(self, doc: Dict[str, Any]) -> str:
        """Format a single document section"""
        return (
            f"--- 文件: {doc.get('filename', '未知文件')} ---\n"
            f"路径: {doc.get('path', '未知路径')}\n"
            f"相关性: {doc.get('score', 0.0):.2f}\n"
            f"内容:\n{doc.get('content', '')}"
        )

    def _truncate_content_if_needed(self, section: str, content: str, budget: int, used: int) -> str:
        """Truncate document content if budget exceeded"""
        if not content:
            return ''

        overhead = len(section) - len(content)
        remaining = budget - used

        if remaining <= overhead + 3:
            return ''

        available_content = remaining - overhead
        if available_content <= len(content):
            return section

        if available_content > 300:
            head_size = min(available_content // 2, 1000)
            tail_size = available_content - head_size - 3
            if tail_size > 0:
                content = content[:head_size] + '...' + content[-tail_size:]
            else:
                content = content[:available_content - 3] + '...'
        else:
            content = content[:available_content - 3] + '...'

        return (
            f"--- 文件: {section.split('--- 文件: ')[1].split(' ---')[0]} ---\n"
            f"路径: {section.split('路径: ')[1].split('\\n')[0]}\n"
            f"相关性: {section.split('相关性: ')[1].split('\\n')[0]}\n"
            f"内容:\n{content}"
        )

    def _calculate_context_budget(self, doc_budget: Optional[int]) -> int:
        """Calculate context budget for documents"""
        if doc_budget is None:
            return max(self.max_context_chars_total, 0)
        return max(doc_budget, 0)

    def _format_prompt_with_template(self, context_text: str, query: str) -> str:
        """Format prompt with template"""
        template = self.prompt_template or DEFAULT_PROMPT
        try:
            return template.format(context=context_text, question=query).strip()
        except KeyError:
            logger.warning("RAG提示模板缺少必要占位符，已使用默认模板")
            return DEFAULT_PROMPT.format(context=context_text, question=query).strip()

    def _remove_repeated_content(self, text: str) -> str:
        """去除重复内容以减少AI生成重复文本"""
        if not text:
            return text

        # 分割成句子或短语
        import re

        # 按换行符或句号分割
        sentences = re.split(r'[\n。！？.!?]', text)

        # 去除重复的句子 - 使用 OrderedDict 保持插入顺序并去重
        from collections import OrderedDict
        unique_sentences = list(OrderedDict.fromkeys(s.strip() for s in sentences if s.strip()))

        return '。'.join(unique_sentences)

    def _is_small_talk(self, query: str) -> bool:
        normalized = (query or '').strip().lower()
        if not normalized:
            return True
        for phrase in self.greeting_keywords:
            if not phrase:
                continue
            if normalized == phrase:
                return True
            if normalized.startswith(phrase) and len(normalized) <= len(phrase) + 2:
                return True
        return False

    def query(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """执行检索增强生成流程，支持简单会话记忆与重置"""
        session_key = (session_id or '').strip()
        if not session_key:
            # 没有提供 session_id 时，为避免不同用户共享"default"历史，生成一次性会话键
            session_key = secrets.token_hex(8)

        normalized_reset = (query or '').strip().lower()
        if normalized_reset in self.reset_commands:
            self._reset_session(session_key)
            return {"answer": self.reset_response, "sources": []}

        try:
            if self._is_small_talk(query):
                return {"answer": self.greeting_response, "sources": []}

            if self._is_noise_query(query):
                return {"answer": self._render_template(self.fallback_response, query), "sources": []}

            if self.max_context_chars_total > 0:
                history_budget = min(self.max_history_chars, self.max_context_chars_total)
            else:
                history_budget = self.max_history_chars

            history_text, used_history = self._build_history(session_key, history_budget)

            doc_budget: Optional[int] = None
            if self.max_context_chars_total > 0:
                doc_budget = max(self.max_context_chars_total - used_history, 0)
                if doc_budget <= 0:
                    return {"answer": self.context_exhausted_response, "sources": []}

                # Adjust document budget based on memory constraints
                doc_budget = self._adjust_context_for_memory(doc_budget)

            documents = self._collect_documents(query)
            if not documents and not history_text:
                answer = self._render_template(self.fallback_response, query)
                return {"answer": answer, "sources": []}

            prompt = self._build_prompt(query, documents, history_text, doc_budget)
            if not prompt:
                return {"answer": self._render_template(self.fallback_response, query), "sources": []}

            # 改进：使用更高效的生成方式，并添加超时处理
            chunks: List[str] = []
            try:
                import threading
                import time

                # 使用线程实现超时机制
                result = {'chunks': [], 'completed': False, 'error': None}

                def generate_content():
                    try:
                        for piece in self.model_manager.generate(prompt, max_tokens=self.max_output_tokens, temperature=self.temperature):
                            if piece:
                                result['chunks'].append(str(piece))
                        result['completed'] = True
                    except Exception as e:
                        result['error'] = e

                # 创建并启动生成线程
                gen_thread = threading.Thread(target=generate_content)
                gen_thread.daemon = True
                gen_thread.start()

                # 获取配置的超时时间，默认为120秒
                timeout = self.config_loader.getint('ai_model', 'request_timeout', 120)
                
                # 等待生成完成
                gen_thread.join(timeout=float(timeout))

                if not result['completed']:
                    logger.warning(f"生成超时({timeout}s)，使用回退响应: {query[:50]}...")
                    # 如果有部分结果，尝试使用
                    partial_answer = ''.join(result['chunks']).strip()
                    if partial_answer:
                        answer = partial_answer + "\n\n(注意：回答生成超时，内容可能不完整)"
                    else:
                        # 如果完全没有结果（例如还在思考中），给出明确提示而不是通用的“未找到”
                        if documents:
                            answer = "已找到相关文档，但AI模型思考时间过长导致超时。请尝试：\n1. 增加配置文件中的 request_timeout\n2. 简化问题\n3. 直接查看下方列出的参考来源"
                        else:
                            answer = self._render_template(self.fallback_response, query)
                elif result['error']:
                    logger.error(f"生成过程中发生错误: {str(result['error'])}")
                    answer = f"生成回答时发生错误: {str(result['error'])}"
                else:
                    answer = ''.join(result['chunks']).strip()
                    if not answer:
                        # 如果生成结果为空（可能是被过滤器完全过滤了），给出提示
                        if documents:
                            answer = "AI模型已完成处理，但未生成有效回答（可能是思考过程被过滤且未生成正文）。请尝试重新提问。"
                        else:
                            answer = self._render_template(self.fallback_response, query)
            except Exception as e:
                logger.error(f"生成过程中发生错误: {str(e)}")
                answer = self._render_template(self.fallback_response, query)

            # 后处理：优化回答格式，确保连贯流畅
            sources = [doc.get('path') or doc.get('filename') for doc in documents]
            answer = self._post_process_answer(answer, sources)
            self._remember_turn(session_key, query, answer)
            return {"answer": answer, "sources": sources}
        except Exception as exc:
            logger.error(f"RAG查询失败: {exc}")
            return {"answer": f"错误：处理查询时发生异常 ({str(exc)})。", "sources": []}

    def _post_process_answer(self, answer: str, sources: List[str]) -> str:
        """
        后处理AI的回答，优化格式使其更连贯流畅
        """
        # 移除分点列表格式，将列表项整合为连贯段落
        import re

        # 将数字列表转换为连贯叙述
        answer = re.sub(r'\n\d+\.\s*', '；', answer)  # 将列表数字替换为分号
        answer = re.sub(r'\n\s*[-*]\s*', '；', answer)  # 将项目符号替换为分号

        # 清理多余的换行符，保持段落连贯
        answer = re.sub(r'\n\s*\n', '\n', answer)

        # 优化引用格式，使其自然融入文本
        if sources and '[文档证据来源:' in answer:
            # 提取来源信息并整合到回答中
            source_pattern = r'\[文档证据来源:\s*([^\]]+)\]'
            matches = re.findall(source_pattern, answer)
            if matches:
                # 提取第一个来源作为主要来源
                primary_source = matches[0] if matches else ""
                # 从原始sources中找到匹配的完整路径
                full_source = next((s for s in sources if primary_source in s), primary_source)

                # 移除标记，改用自然引用方式
                answer = re.sub(source_pattern, '', answer)

                # 在回答开头或结尾添加自然引用
                if full_source and full_source not in answer:
                    # 如果回答中没有提到来源，添加自然的引用
                    if '。' in answer:
                        parts = answer.rsplit('。', 1)
                        if len(parts) > 1:
                            answer = f"{parts[0]}。相关信息来源于文档《{full_source}》{parts[1]}"
                        else:
                            answer = f"{answer}（信息来源于文档《{full_source}》）"
                    else:
                        answer = f"{answer}（信息来源于文档《{full_source}》）"

        # 清理多余的分号和空格
        answer = re.sub(r'；+', '；', answer)
        answer = re.sub(r'；\s*[，。；]', r'\g<0>', answer)  # 保留正确的标点

        # 统一标点符号
        answer = answer.replace('[QUERY_TERM]', '').replace('[/QUERY_TERM]', '')

        return answer.strip()

    def get_session_stats(self, session_id: str = None) -> Dict[str, Any]:
        """获取会话统计信息"""
        session_key = session_id or ''
        messages = self.chat_db.get_session_messages(session_key)

        total_chars = 0
        for msg in messages:
            total_chars += len(msg.get('content', '') or '')

        # 计算对话轮次（用户消息数）
        turn_count = sum(1 for msg in messages if msg.get('role') == 'user')

        return {
            'session_id': session_key,
            'turn_count': turn_count,
            'total_characters': total_chars,
            'max_history_turns': self.max_history_turns,
            'max_history_chars': self.max_history_chars
        }

    def clear_session(self, session_id: str = None) -> bool:
        """清空指定会话的历史记录"""
        session_key = session_id or ''
        return self.chat_db.delete_session(session_key)

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有活跃会话的详细信息"""
        # 直接从数据库获取所有会话信息
        return self.chat_db.get_all_sessions()

    def update_config(self, **kwargs):
        """动态更新RAG配置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"更新RAG配置: {key} = {value}")
    
    def get_config(self) -> Dict[str, Any]:
        """获取当前RAG配置"""
        return {
            'max_docs': self.max_docs,
            'max_context_chars': self.max_context_chars,
            'max_context_chars_total': self.max_context_chars_total,
            'max_history_turns': self.max_history_turns,
            'max_history_chars': self.max_history_chars,
            'max_output_tokens': self.max_output_tokens,
            'temperature': self.temperature,
            'prompt_template': self.prompt_template,
            'greeting_keywords': self.greeting_keywords,
            'reset_commands': self.reset_commands
        }
