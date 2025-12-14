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

logger = setup_logger()

DEFAULT_PROMPT = (
    "你是一名专业的中文文档助理。请根据下方的【文档集合】回答用户的【问题】。\n"
    "规则：\n"
    "1. 严格基于文档内容回答，不要编造。\n"
    "2. 如果用户询问某人、某事出现在哪里，或者询问来源，请务必列出对应的文件名。\n"
    "3. 如果答案仅出现在文件名中（例如文件名包含查询词），请明确指出该文件。\n"
    "4. 如果文档中没有相关信息，请直接说明未找到。\n\n"
    "【文档集合】:\n{context}\n\n"
    "【问题】: {question}\n\n"
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

        self.session_histories: Dict[str, List[Dict[str, str]]] = {}

    def _adjust_context_for_memory(self, doc_budget: int) -> int:
        """Adjust document budget based on memory constraints"""
        if self.vram_manager.should_limit_context():
            # Reduce context size by 50% if memory is constrained
            return max(doc_budget // 2, self.max_context_chars // 2)
        return doc_budget

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
        history = self.session_histories.get(session_id, []) or []
        if not history or budget <= 0:
            return '', 0

        # 改进：按时间倒序获取最近的对话轮次，但保留重要的上下文
        turns = history[-self.max_history_turns :]
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
        history = self.session_histories.setdefault(session_id, [])

        # 改进：添加会话条目时，包括时间戳以更好地管理过期
        import time
        history.append({
            'q': query,
            'a': answer,
            'timestamp': time.time()  # 添加时间戳
        })

        # 限制对话轮次数量
        if len(history) > self.max_history_turns:
            overflow = len(history) - self.max_history_turns
            del history[0:overflow]

        def _total_len(items: List[Dict[str, str]]) -> int:
            total = 0
            for item in items:
                total += len(item.get('q', '') or '')
                total += len(item.get('a', '') or '')
            return total

        # 智能地根据字符数清理历史记录，保留最近的重要对话
        while _total_len(history) > self.max_history_chars and len(history) > 1:
            # 删除最旧的条目
            history.pop(0)

    def _reset_session(self, session_id: str) -> None:
        self.session_histories.pop(session_id, None)

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
        try:
            # Try to get cached results first to improve performance
            cache_key = f"search_{query[:50]}"  # Use first 50 chars as cache key
            results = self.vram_manager.get_cached_result(cache_key)

            if results is None:
                results = self.search_engine.search(query) or []
                # Cache results if they exist and caching is beneficial
                if results:
                    self.vram_manager.cache_result(cache_key, results, len(results))
            else:
                # Update cache access time
                self.vram_manager.get_cached_result(cache_key)
        except Exception as e:
            logger.error(f"文档收集过程中发生错误: {str(e)}")
            results = []  # 回退到空结果

        try:
            # 改进：首先收集所有结果，然后根据相关性排序，再选择最相关的文档
            all_candidates: List[Dict[str, Any]] = []
            seen_paths = set()

            for res in results:
                try:
                    path = res.get('path', '')
                    if path and path.lower() in seen_paths:
                        continue
                    if path:
                        seen_paths.add(path.lower())

                    # 优先获取完整内容，而不是截断的索引内容
                    # 从索引中获取完整内容
                    raw_content = res.get('content') or ''
                    snippet = res.get('snippet') or ''

                    # 尝试从索引获取完整内容（避免索引中存储的截断内容）
                    full_content = self.search_engine.index_manager.get_document_content(path) if hasattr(self.search_engine, 'index_manager') else ''

                    # 如果索引中没有完整内容，使用原始检索到的内容
                    if full_content:
                        cleaned = self._strip_tags(full_content)
                    else:
                        cleaned = self._strip_tags(raw_content) if raw_content else self._strip_tags(snippet)

                    # 优先使用路径获取真实文件名，避免索引返回的 filename 字段可能存在的截断或分词问题
                    if path:
                        filename = os.path.basename(path)
                    else:
                        filename = res.get('filename') or res.get('file_name') or '未知文件'

                    composite = cleaned or ''
                    for extra in (filename, res.get('file_name'), os.path.basename(path), path):
                        if extra:
                            composite += f" {extra}"

                    # 改进：仅对明显不相关的文档进行过滤，保留可能相关的结果进行后续相关性评估
                    if not self._has_query_overlap(composite, query):
                        # 对于内容和文件名都不匹配的文档，给予较低的权重但不完全过滤
                        is_low_relevance = True
                    else:
                        is_low_relevance = False

                    # 如果文件名包含查询词，显式添加到内容开头，确保LLM能看到
                    if filename and self._has_query_overlap(filename, query):
                        prefix = f"【重要证据：文件名包含查询词】文件名: {filename}\n"
                        if not cleaned.startswith("【重要证据"):
                            cleaned = prefix + cleaned

                    if not cleaned:
                        cleaned = f"文件名匹配：{filename}" if filename else "文件名匹配"

                    # 去除重复内容以减少AI重复生成
                    cleaned = self._remove_repeated_content(cleaned)

                    # 仅在必要时进行截断，并且保留更多内容
                    if len(cleaned) > self.max_context_chars:
                        # 尝试保留最重要的部分：先保留开头，然后是结尾
                        max_len = self.max_context_chars
                        if max_len > 200:  # 如果允许的空间足够，使用头尾截断
                            head_size = min(max_len // 2, 500)  # 保留前500字符
                            tail_size = max_len - head_size - 3  # 剩余给尾部的空间
                            if tail_size > 0:
                                cleaned = cleaned[:head_size] + '...' + cleaned[-tail_size:]
                            else:
                                cleaned = cleaned[:max_len - 3] + '...'
                        else:
                            cleaned = cleaned[:max_len - 3] + '...'

                    # 计算文档的相关性得分，结合搜索分数和内容匹配程度
                    relevance_score = float(res.get('score', 0.0))

                    # 如果标题或文件名包含关键词，提高相关性得分
                    if filename and self._has_query_overlap(filename, query):
                        relevance_score *= 1.3  # 增加30%的权重

                    # 根据内容与查询的匹配程度调整相关性
                    if self._has_query_overlap(cleaned, query):
                        relevance_score *= 1.2  # 内容匹配时增加20%的权重

                    all_candidates.append({
                        'path': path,
                        'filename': filename,
                        'score': float(res.get('score', 0.0)),  # 原始搜索分数
                        'relevance_score': relevance_score,  # 改进的相关性分数
                        'content': cleaned,
                        'is_low_relevance': is_low_relevance  # 标记是否为低相关性
                    })
                except Exception as e:
                    logger.warning(f"处理搜索结果时出现错误，跳过该结果: {str(e)}")
                    continue  # 跳过有问题的结果，继续处理下一个

            # 按改进的相关性分数排序
            all_candidates.sort(key=lambda x: x['relevance_score'], reverse=True)

            # 选择最相关的文档，优先选择高相关性的，同时包括一些中等相关性的以增加多样性
            documents: List[Dict[str, Any]] = []
            high_relevance_docs = []
            low_relevance_docs = []

            for candidate in all_candidates:
                if candidate['is_low_relevance']:
                    low_relevance_docs.append(candidate)
                else:
                    high_relevance_docs.append(candidate)

            # 优先添加高相关性文档
            for candidate in high_relevance_docs:
                if len(documents) >= self.max_docs:
                    break
                documents.append({
                    'path': candidate['path'],
                    'filename': candidate['filename'],
                    'score': candidate['score'],
                    'content': candidate['content']
                })

            # 如果还有空间，添加一些低相关性但可能有用的结果
            remaining_slots = self.max_docs - len(documents)
            for candidate in low_relevance_docs:
                if len(documents) >= self.max_docs:
                    break
                documents.append({
                    'path': candidate['path'],
                    'filename': candidate['filename'],
                    'score': candidate['score'],
                    'content': candidate['content']
                })

            return documents
        except Exception as e:
            logger.error(f"收集文档过程中发生严重错误: {str(e)}")
            # 回退到空文档列表
            return []

    def _build_prompt(self, query: str, documents: List[Dict[str, Any]], history_text: str, doc_budget: Optional[int]) -> str:
        if not documents and not history_text:
            return ''

        context_sections = []

        if history_text:
            context_sections.append(f"对话历史（最近）:\n{history_text}")

        if doc_budget is None:
            context_budget = max(self.max_context_chars_total, 0)
        else:
            context_budget = max(doc_budget, 0)

        enforce_budget = context_budget > 0
        used_chars = len(history_text) if history_text else 0  # 修正：将历史记录长度计入已使用字符数

        for idx, doc in enumerate(documents, start=1):
            if enforce_budget and used_chars >= context_budget:
                break

            content = doc.get('content', '') or ''

            if not content:
                continue

            # 先构建完整部分，计算其长度
            section = (
                f"[文档{idx}] {doc.get('filename', '未知文件')}\n"
                f"路径: {doc.get('path', '未知路径')}\n"
                f"相关性: {doc.get('score', 0.0):.2f}\n"
                f"内容:\n{content}"
            )

            # 如果启用预算限制，检查是否需要截断
            if enforce_budget:
                remaining = context_budget - used_chars
                if remaining <= 0:
                    break  # 没有剩余空间

                if len(section) > remaining:
                    # 需要截断内容以适应预算
                    # 计算格式开销
                    overhead = len(section) - len(content)
                    available_content = remaining - overhead

                    if available_content > 3:  # 确保有足够的空间用于内容和省略号
                        # 简化截断逻辑：保留开头和结尾
                        if available_content > 200:  # 如果剩余空间足够，使用头尾截断策略
                            head_size = min(available_content // 2, 500)  # 保留前500字符
                            tail_size = available_content - head_size - 3  # 剩余给尾部的空间
                            if tail_size > 0:
                                content = content[:head_size] + '...' + content[-tail_size:]
                            else:
                                content = content[:available_content - 3] + '...'
                        else:
                            content = content[:available_content - 3] + '...'

                        # 重新构建 section
                        section = (
                            f"[文档{idx}] {doc.get('filename', '未知文件')}\n"
                            f"路径: {doc.get('path', '未知路径')}\n"
                            f"相关性: {doc.get('score', 0.0):.2f}\n"
                            f"内容:\n{content}"
                        )
                    else:
                        # 空间太小，连格式都放不下，跳过此文档
                        continue

            # 添加文档部分到上下文
            context_sections.append(section)
            # 更新已使用的字符数 - 修正为累加整个部分的长度
            used_chars += len(section)

        context_text = "\n\n".join(context_sections)
        logger.info(f"Constructed context length: {len(context_text)}")
        logger.debug(f"Context snippet: {context_text[:200]}...")
        template = self.prompt_template or DEFAULT_PROMPT
        try:
            return template.format(context=context_text, question=query).strip()
        except KeyError:
            # 当模板缺少占位符时退回默认模板，避免崩溃
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

            sources = [doc.get('path') or doc.get('filename') for doc in documents]
            self._remember_turn(session_key, query, answer)
            return {"answer": answer, "sources": sources}
        except Exception as exc:
            logger.error(f"RAG查询失败: {exc}")
            return {"answer": f"错误：处理查询时发生异常 ({str(exc)})。", "sources": []}
