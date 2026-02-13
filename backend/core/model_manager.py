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
        self.model_name = "local"
        self.max_context = self.config_loader.getint('ai_model', 'local.max_context', 4096)
        self.default_max_tokens = self.config_loader.getint('ai_model', 'local.max_tokens', 512)
        self.default_temperature = 0.3  # 本地模型使用更低温度

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

    def get_model_limits(self) -> Dict[str, Any]:
        """获取当前模型的限制参数"""
        if self.mode == ModelMode.LOCAL:
            return {
                'max_context': self.max_context,
                'max_docs': 3,
                'chunk_size': 500,
                'chunk_overlap': 100,
                'temperature': self.default_temperature,
                'max_tokens': self.default_max_tokens,
            }
        else:
            return {
                'max_context': self.max_context,
                'max_docs': 5,
                'chunk_size': 1500,
                'chunk_overlap': 200,
                'temperature': self.default_temperature,
                'max_tokens': self.default_max_tokens,
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
                 temperature: Optional[float] = None) -> Generator[str, None, None]:
        """
        生成回答 - 始终经过隐私保护处理

        Args:
            prompt: 输入提示词
            session_id: 会话ID
            max_tokens: 最大生成token数
            temperature: 温度参数

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
                logger.debug("Prompt redacted for privacy")  # 使用debug级别避免泄露信息

            # 验证配置
            self._validate_api_config()

            # 使用默认参数
            effective_max_tokens = max_tokens or self.default_max_tokens
            effective_temperature = temperature or self.default_temperature

            # 调用生成
            for chunk in self._chat_generate(redacted_prompt, effective_max_tokens,
                                             effective_temperature):
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
                       temperature: float) -> Generator[str, None, None]:
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
            request_url = self.api_url
            if '/completions' in request_url and '/chat/completions' not in request_url:
                request_url = request_url.replace('/completions', '/chat/completions')
            elif '/chat/completions' not in request_url:
                if request_url.endswith('/'):
                    request_url += 'chat/completions'
                else:
                    request_url += '/chat/completions'

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

            # API模式添加额外参数
            if self.mode == ModelMode.API:
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

            response = self.session.post(
                self.api_url,
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

    def close(self):
        """关闭会话，释放资源"""
        if self.session:
            self.session.close()
