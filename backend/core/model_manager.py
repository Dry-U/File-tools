# backend/core/model_manager.py
import os
import json
import time
import hashlib
from typing import Optional, Generator, Dict, Any
from enum import Enum
import requests
from requests.adapters import HTTPAdapter, Retry

from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
from backend.core.privacy_guard import get_privacy_guard

logger = setup_logger()


class ModelError(Exception):
    """模型调用错误基类"""
    pass


class APIKeyError(ModelError):
    """API密钥错误"""
    pass


class NetworkError(ModelError):
    """网络连接错误"""
    pass


class RateLimitError(ModelError):
    """速率限制"""
    pass


class ContextLengthError(ModelError):
    """上下文超长"""
    pass


def _normalize_text(text: str) -> str:
    """修复编码问题"""
    if not isinstance(text, str) or not text:
        return text

    if any(ord(ch) > 255 for ch in text):
        return text

    extended = sum(1 for ch in text if 0x80 <= ord(ch) <= 0xFF)
    if extended == 0:
        return text

    try:
        fixed = text.encode('latin-1').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


class ModelMode(Enum):
    """模型模式"""
    LOCAL = "local"
    API = "api"


class ModelManager:
    """
    模型管理器 - 支持本地和API两种模式
    始终启用隐私保护
    """

    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.privacy_guard = get_privacy_guard()

        # 获取当前模式（带异常处理）
        try:
            mode_str = config_loader.get('ai_model', 'mode', 'local')
            self.mode = ModelMode(mode_str)
        except ValueError:
            logger.warning(f"Invalid mode configured, defaulting to local")
            self.mode = ModelMode.LOCAL

        # 安全配置
        self.verify_ssl = config_loader.getboolean('ai_model', 'security.verify_ssl', True)
        self.timeout = config_loader.getint('ai_model', 'security.timeout', 120)
        self.retry_count = config_loader.getint('ai_model', 'security.retry_count', 2)

        # 根据模式加载配置
        if self.mode == ModelMode.LOCAL:
            self._init_local_config()
        else:
            self._init_api_config()

        # 创建会话（带连接池和重试）
        self.session = self._create_session()

    def _init_local_config(self):
        """初始化本地模型配置"""
        self.api_url = self.config_loader.get('ai_model', 'local.api_url',
                                               'http://localhost:8000/v1/chat/completions')
        self.api_key = ""
        self.max_context = self.config_loader.getint('ai_model', 'local.max_context', 4096)
        self.default_max_tokens = self.config_loader.getint('ai_model', 'local.max_tokens', 512)
        self.default_temperature = 0.3  # 本地模型使用更低温度

        # 获取用户配置的模型名称（优先）
        configured_model = self.config_loader.get('ai_model', 'local.model_name', 'local')

        # 尝试通过API自动探测模型信息
        detected_model = self._auto_detect_model()

        # 决策：优先使用用户配置，除非配置的是默认'local'且有探测结果
        if configured_model and configured_model != 'local':
            self.model_name = configured_model
            logger.info(f"使用用户配置的模型名称: {self.model_name}")
        elif detected_model:
            self.model_name = detected_model
            logger.info(f"自动探测到本地模型: {self.model_name}")
        else:
            self.model_name = configured_model or 'local'
            logger.info(f"使用默认模型名称: {self.model_name}")

        # 检测模型大小参数（用于自动调整RAG策略）
        self.model_size_params = self._detect_model_size()
        logger.info(f"模型大小识别结果: {self.model_size_params}")

    def _auto_detect_model(self) -> Optional[str]:
        """
        尝试通过 /v1/models 接口自动探测模型名称
        支持 OpenAI 兼容的 API 格式
        """
        try:
            # 构造 /v1/models 端点 URL
            base_url = self.api_url.replace('/v1/chat/completions', '').rstrip('/')
            models_url = f"{base_url}/v1/models"

            response = requests.get(models_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('data', [])
                if models:
                    # 获取第一个可用模型的ID
                    model_id = models[0].get('id', '')
                    if model_id:
                        logger.info(f"通过API探测到模型ID: {model_id}")
                        return model_id
        except requests.exceptions.ConnectionError:
            logger.debug("无法连接到本地模型服务，跳过自动探测")
        except requests.exceptions.Timeout:
            logger.debug("探测模型信息超时")
        except Exception as e:
            logger.debug(f"自动探测模型失败: {e}")

        return None

    def _init_api_config(self):
        """初始化API模型配置"""
        self.api_url = self.config_loader.get('ai_model', 'api.api_url',
                                               'https://api.siliconflow.cn/v1/chat/completions')
        # 获取当前provider
        provider = self.config_loader.get('ai_model', 'api.provider', 'siliconflow')
        # 优先从新的多provider结构获取key
        self.api_key = self.config_loader.get('ai_model', f'api.keys.{provider}', '')
        if not self.api_key:
            # 回退到旧配置
            self.api_key = self.config_loader.get('ai_model', 'api.api_key', '')
        self.model_name = self.config_loader.get('ai_model', 'api.model_name',
                                                   'deepseek-ai/DeepSeek-V2.5')
        self.max_context = self.config_loader.getint('ai_model', 'api.max_context', 8192)
        self.default_max_tokens = self.config_loader.getint('ai_model', 'api.max_tokens', 2048)
        self.default_temperature = 0.7

    def _create_session(self) -> requests.Session:
        """创建带连接池和重试的会话"""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.retry_count,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        adapter = HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=retry_strategy
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get_mode(self) -> ModelMode:
        """获取当前模式"""
        return self.mode

    def _detect_model_size(self) -> Dict[str, Any]:
        """
        尝试检测本地模型的大小参数
        基于模型名称或配置的启发式检测
        """
        model_name = self.model_name.lower()
        max_context = self.max_context

        # 基于模型名称的启发式检测
        size_hints = {
            '1b': 1, '1.5b': 1.5, '2b': 2,
            '3b': 3, '4b': 4, '7b': 7, '8b': 8,
            '13b': 13, '14b': 14, '20b': 20,
            '30b': 30, '32b': 32, '70b': 70
        }

        detected_size = None
        for size_str, size_gb in size_hints.items():
            if size_str in model_name:
                detected_size = size_gb
                break

        # 根据上下文窗口推断（如果没有从名称检测到）
        if detected_size is None:
            if max_context <= 4096:
                detected_size = 3  # 默认为3B配置
            elif max_context <= 8192:
                detected_size = 7  # 可能是7B
            else:
                detected_size = 13  # 更大的模型

        # 分类模型大小
        if detected_size <= 4:
            category = 'small'  # 1-4B: 小模型
        elif detected_size <= 8:
            category = 'medium'  # 7-8B: 中等模型
        else:
            category = 'large'  # 13B+: 大模型

        return {
            'detected_size': detected_size,
            'category': category,
            'model_name': self.model_name
        }

    def get_model_limits(self) -> Dict[str, Any]:
        """获取当前模型的限制参数（基于模型大小动态优化）"""
        if self.mode == ModelMode.LOCAL:
            # 获取模型大小分类
            model_category = getattr(self, 'model_size_params', {}).get('category', 'small')
            max_context_size = self.max_context

            # 根据模型大小分类动态调整参数
            if model_category == 'small':
                # 小模型（1-4B）：保守配置
                max_docs = 3
                chunk_size = 500
                chunk_overlap = 80
                min_doc_score = 0.45
                logger.debug(f"应用小模型(1-4B)配置: max_docs={max_docs}, chunk_size={chunk_size}")
            elif model_category == 'medium':
                # 中等模型（7-8B）：平衡配置
                max_docs = 4
                chunk_size = 700
                chunk_overlap = 100
                min_doc_score = 0.4
                logger.debug(f"应用中等模型(7-8B)配置: max_docs={max_docs}, chunk_size={chunk_size}")
            else:
                # 大模型（13B+）：宽松配置
                max_docs = 5
                chunk_size = 900
                chunk_overlap = 120
                min_doc_score = 0.35
                logger.debug(f"应用大模型(13B+)配置: max_docs={max_docs}, chunk_size={chunk_size}")

            # 根据上下文窗口做最终调整
            if max_context_size <= 2048:
                # 极小上下文窗口
                max_docs = min(max_docs, 2)
                chunk_size = min(chunk_size, 400)
            elif max_context_size >= 16384 and model_category != 'small':
                # 超大上下文窗口（仅对大模型）
                max_docs += 1
                chunk_size += 100

            return {
                'max_context': max_context_size,
                'max_docs': max_docs,           # 根据模型大小调整
                'chunk_size': chunk_size,       # 适中切片长度
                'chunk_overlap': chunk_overlap, # 适度重叠保持连贯
                'temperature': self.default_temperature,
                'max_tokens': self.default_max_tokens,
                'min_doc_score': min_doc_score,  # 根据模型能力调整阈值
            }
        else:
            # API模式：使用更高限制以充分利用远程模型能力
            return {
                'max_context': self.max_context,
                'max_docs': 10,          # API模式可以处理更多文档
                'chunk_size': 2000,      # 更大的切片长度
                'chunk_overlap': 200,
                'temperature': self.default_temperature,
                'max_tokens': self.default_max_tokens,
                'min_doc_score': 0.4,    # API模式使用较高阈值确保质量
            }

    def _validate_api_config(self):
        """验证API配置"""
        if self.mode == ModelMode.API:
            if not self.api_key:
                raise APIKeyError("API密钥未配置")
            if not self.api_url:
                raise NetworkError("API URL未配置")
            if not self.api_url.startswith(('http://', 'https://')):
                raise NetworkError("API URL必须以http://或https://开头")
            # 基本URL格式验证
            from urllib.parse import urlparse
            parsed = urlparse(self.api_url)
            if not parsed.netloc:
                raise NetworkError("API URL格式无效")

    def _handle_response_error(self, response: requests.Response):
        """处理响应错误"""
        if response.status_code == 401:
            raise APIKeyError("API密钥无效或已过期")
        elif response.status_code == 429:
            raise RateLimitError("请求过于频繁，请稍后再试")
        elif response.status_code == 413:
            raise ContextLengthError("请求内容过长")
        elif response.status_code >= 500:
            raise NetworkError(f"服务器错误: {response.status_code}")
        elif response.status_code >= 400:
            raise ModelError(f"请求错误: {response.status_code} - {response.text}")

    def generate(self, prompt: str, session_id: Optional[str] = None,
                 max_tokens: Optional[int] = None,
                 temperature: Optional[float] = None,
                 top_p: Optional[float] = None,
                 top_k: Optional[int] = None,
                 min_p: Optional[float] = None,
                 seed: Optional[int] = None,
                 repeat_penalty: Optional[float] = None,
                 frequency_penalty: Optional[float] = None,
                 presence_penalty: Optional[float] = None) -> Generator[str, None, None]:
        """
        生成回答 - 始终经过隐私保护处理

        Args:
            prompt: 输入提示词
            session_id: 会话ID
            max_tokens: 最大生成token数
            temperature: 温度参数
            top_p: 核采样参数
            top_k: Top K采样参数
            min_p: 最小概率参数
            seed: 随机种子
            repeat_penalty: 重复惩罚
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚

        Yields:
            生成的文本片段
        """
        try:
            # 检查模型是否启用
            model_enabled = self.config_loader.getboolean('ai_model', 'enabled', False)
            if not model_enabled:
                yield "AI功能未启用，请在设置中开启"
                return

            # 隐私保护：脱敏处理
            redacted_prompt = self.privacy_guard.redact(prompt)
            if redacted_prompt != prompt:
                logger.debug("提示词已脱敏")  # 使用debug级别避免泄露信息

            # 验证配置
            self._validate_api_config()

            # 使用默认参数
            effective_max_tokens = max_tokens or self.default_max_tokens
            effective_temperature = temperature or self.default_temperature

            # 调用生成
            for chunk in self._chat_generate(redacted_prompt, effective_max_tokens,
                                             effective_temperature, top_p, top_k,
                                             min_p, seed, repeat_penalty,
                                             frequency_penalty, presence_penalty):
                yield _normalize_text(chunk)

        except APIKeyError as e:
            logger.error(f"API密钥错误: {e}")
            yield f"错误：API密钥无效 - {str(e)}"
        except NetworkError as e:
            logger.error(f"网络错误: {e}")
            yield f"错误：网络连接失败 - {str(e)}"
        except RateLimitError as e:
            logger.error(f"速率限制: {e}")
            yield f"错误：{str(e)}"
        except ContextLengthError as e:
            logger.error(f"上下文超长: {e}")
            yield f"错误：内容过长，请缩短输入或精简文档"
        except Exception as e:
            logger.error(f"生成失败: {e}")
            yield f"错误：{str(e)}"

    def _chat_generate(self, prompt: str, max_tokens: int,
                       temperature: float, top_p: Optional[float] = None,
                       top_k: Optional[int] = None, min_p: Optional[float] = None,
                       seed: Optional[int] = None, repeat_penalty: Optional[float] = None,
                       frequency_penalty: Optional[float] = None,
                       presence_penalty: Optional[float] = None) -> Generator[str, None, None]:
        """
        OpenAI Chat API 生成
        同时适用于本地和API模式
        """
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # 确保使用 /chat/completions 端点
            request_url = self._normalize_url(self.api_url)

            # 获取系统提示词
            system_prompt = self.config_loader.get('ai_model', 'system_prompt', '')

            # 构建消息列表
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # 构建请求体
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }

            # 添加可选采样参数
            if top_p is not None:
                payload["top_p"] = top_p
            if top_k is not None:
                payload["top_k"] = top_k
            if min_p is not None:
                payload["min_p"] = min_p
            if seed is not None and seed >= 0:
                payload["seed"] = seed
            if repeat_penalty is not None:
                payload["repeat_penalty"] = repeat_penalty
            if frequency_penalty is not None:
                payload["frequency_penalty"] = frequency_penalty
            if presence_penalty is not None:
                payload["presence_penalty"] = presence_penalty

            # API模式添加默认top_p（如果未指定）
            if self.mode == ModelMode.API and top_p is None:
                payload["top_p"] = 0.9

            logger.debug(f"Chat API Request URL: {request_url}")

            # 根据模式调整超时：本地模型通常响应较慢
            if self.mode == ModelMode.LOCAL:
                connect_timeout, read_timeout = 5, self.timeout * 2
            else:
                connect_timeout, read_timeout = 10, self.timeout

            response = self.session.post(
                request_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=(connect_timeout, read_timeout),
                verify=self.verify_ssl
            )

            # 处理错误
            if response.status_code >= 400:
                self._handle_response_error(response)

            response.raise_for_status()

            # 处理流式响应
            if not response.encoding:
                response.encoding = 'utf-8'

            buffer = ""
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                line = line.strip()
                if not line:
                    continue

                if line.startswith('data:'):
                    data_str = line[5:].strip()
                else:
                    continue

                if data_str == '[DONE]':
                    break

                # 处理可能的JSON截断
                if buffer:
                    data_str = buffer + data_str
                    buffer = ""

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    buffer = data_str
                    continue

                choices = chunk.get('choices', [])
                if not choices:
                    continue

                delta = choices[0].get('delta', {})
                content = delta.get('content', '')

                if content:
                    yield content

        except requests.exceptions.Timeout:
            raise NetworkError(f"请求超时（{self.timeout}秒）")
        except requests.exceptions.ConnectionError:
            raise NetworkError("无法连接到模型服务")
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"请求异常: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """测试连接 - 用于健康检查"""
        try:
            self._validate_api_config()

            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # 发送一个简单的请求测试连接
            test_payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }

            # 使用标准化后的 URL
            test_url = self._normalize_url(self.api_url)
            response = self.session.post(
                test_url,
                json=test_payload,
                headers=headers,
                timeout=10,
                verify=self.verify_ssl
            )

            if response.status_code == 200:
                return {"status": "ok", "mode": self.mode.value, "model": self.model_name}
            elif response.status_code == 401:
                return {"status": "error", "error": "API密钥无效"}
            else:
                return {"status": "error", "error": f"HTTP {response.status_code}"}

        except APIKeyError as e:
            return {"status": "error", "error": str(e)}
        except NetworkError as e:
            return {"status": "error", "error": str(e)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _normalize_url(self, url: str) -> str:
        """标准化 API URL，确保使用 /chat/completions 端点"""
        if '/chat/completions' not in url:
            if url.endswith('/'):
                return url + 'chat/completions'
            else:
                return url + '/chat/completions'
        return url

    def close(self):
        """关闭会话，释放资源"""
        if self.session:
            self.session.close()
