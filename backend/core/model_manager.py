# src/core/model_manager.py
import os
import time
import json
from typing import Optional, Generator, Any
import requests  # 用于WSL API fallback
from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
# 临时定义缺失的类
class InferenceOptimizer:
    def __init__(self, model_manager):
        self.model_manager = model_manager
    def generate(self, prompt, session_id=None, max_tokens=512, temperature=0.7):
        # 模拟生成
        yield "模拟响应: " + prompt
logger = setup_logger()

def _normalize_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text

    # 如果已经包含正常的Unicode字符（例如中文），则无需处理
    if any(ord(ch) > 255 for ch in text):
        return text

    # 检测是否存在较多的扩展拉丁字符，可能是UTF-8被当作Latin-1解析后的"乱码"
    extended = sum(1 for ch in text if 0x80 <= ord(ch) <= 0xFF)
    if extended == 0:
        return text

    try:
        # 尝试修复常见的编码错误
        fixed = text.encode('latin-1').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text

def _normalize_text_wrapper(text: str) -> str:
    """包装器，用于在类方法中调用"""
    return _normalize_text(text)


class ModelManager:
    """模型管理器：仅支持WSL和在线API接口"""

    def __init__(self, config_loader):
        self.optimizer = InferenceOptimizer(self)
        self.config_loader = config_loader
        # 获取配置时增加健壮性检查
        try:
            self.interface_type: str = config_loader.get('ai_model', 'interface_type', 'wsl')
            self.api_url: str = config_loader.get('ai_model', 'api_url', 'http://localhost:8000/v1/chat/completions')
            self.api_key: str = config_loader.get('ai_model', 'api_key', '')
            self.api_format: str = config_loader.get('ai_model', 'api_format', 'openai_chat')
            self.api_model_name: str = config_loader.get('ai_model', 'api_model', 'wsl')
            self.system_prompt: str = config_loader.get('ai_model', 'system_prompt', '')
            self.request_timeout: int = config_loader.getint('ai_model', 'request_timeout', 60)
            self.default_max_tokens: int = config_loader.getint('ai_model', 'max_tokens', 2048)
        except Exception as e:
            print(f"获取模型配置失败: {str(e)}")
            logger.error(f"获取模型配置失败: {str(e)}")
            # 使用默认值
            self.interface_type = 'wsl'
            self.api_url = 'http://localhost:8000/v1/chat/completions'
            self.api_key = ''
            self.api_format = 'openai_chat'
            self.api_model_name = 'wsl'
            self.system_prompt = ''
            self.request_timeout = 60
            self.default_max_tokens = 2048

        if self.interface_type == 'api':
            self.api_model_name = config_loader.get('ai_model', 'api_model', 'gpt-3.5-turbo')

    def generate(self, prompt: str, session_id: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.7) -> Generator[str, None, None]:
        """根据配置的接口类型进行推理生成 - 现在只支持WSL和API"""
        try:
            # 检查模型是否启用
            model_enabled = False
            try:
                model_enabled = self.config_loader.getboolean('ai_model', 'enabled', False)
            except Exception as e:
                print(f"检查模型启用状态失败: {str(e)}")
                logger.error(f"检查模型启用状态失败: {str(e)}")

            if not model_enabled:
                yield "模拟响应: " + prompt
                return

            # 根据接口类型选择不同的生成方式
            if self.interface_type == 'wsl':
                for chunk in self._wsl_generate(prompt, max_tokens, temperature):
                    yield _normalize_text(chunk)
            elif self.interface_type == 'api':
                for chunk in self._api_generate(prompt, max_tokens, temperature):
                    yield _normalize_text(chunk)
            else:
                yield f"错误：未知的AI接口类型: {self.interface_type}。当前仅支持 'wsl' 和 'api'。"
        except Exception as e:
            logger.error(f"生成失败: {e}")
            yield f"错误：{str(e)}"

    def _wsl_generate(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """WSL API生成 - 代理到通用API生成"""
        # 根据配置决定使用 Chat API 还是 Completion API
        if self.api_format == 'openai_chat':
            return self._chat_generate(prompt, max_tokens, temperature)
        return self._api_generate(prompt, max_tokens, temperature)

    def _chat_generate(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """OpenAI Chat API生成"""
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            effective_max_tokens = max_tokens or self.default_max_tokens

            # 确保使用 /chat/completions 端点
            request_url = self.api_url
            if '/completions' in request_url and '/chat/completions' not in request_url:
                request_url = request_url.replace('/completions', '/chat/completions')
            elif '/chat/completions' not in request_url:
                # 如果URL没有明确指定端点，尝试追加
                if request_url.endswith('/'):
                    request_url += 'chat/completions'
                else:
                    request_url += '/chat/completions'

            # 构建消息列表
            messages = [{"role": "user", "content": prompt}]
            # 如果有系统提示词，可以添加
            if self.system_prompt:
                messages.insert(0, {"role": "system", "content": self.system_prompt})

            payload = {
                "model": self.api_model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": effective_max_tokens,
                "stream": True
            }

            logger.debug(f"Chat API Request URL: {request_url}")

            response = requests.post(
                request_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.request_timeout
            )

            if response.status_code >= 400:
                logger.error(f"Chat API Error: {response.status_code} - {response.text}")
                yield f"错误：API返回 {response.status_code}"
                return

            response.raise_for_status()

            # 手动处理编码，避免 iter_lines(decode_unicode=True) 可能的问题
            if not response.encoding:
                response.encoding = 'utf-8'

            for line in response.iter_lines():
                if not line: continue

                # 解码行
                try:
                    decoded_line = line.decode('utf-8').strip()
                except Exception:
                    continue

                if not decoded_line: continue

                if decoded_line.startswith('data:'):
                    data_str = decoded_line[5:].strip()
                else:
                    continue

                if data_str == '[DONE]':
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning(f"JSON Decode Error for chunk: {data_str}")
                    continue

                choices = chunk.get('choices', [])
                if not choices: continue

                delta = choices[0].get('delta', {})
                content = delta.get('content', '')

                # 检查结束原因
                finish_reason = choices[0].get('finish_reason')
                if finish_reason:
                    logger.info(f"Generation finished. Reason: {finish_reason}")

                if content:
                    yield _normalize_text_wrapper(content)

        except Exception as e:
            logger.error(f"Chat API调用失败: {e}")
            yield f"错误：Chat API调用失败 - {str(e)}"

    def _api_generate(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """通用API生成 - 为 Qwen3-VL-2B-Thinking-abliterated 模型优化"""
        try:
            headers = {
                'Content-Type': 'application/json'
            }

            # 如果配置了API密钥，添加到请求头
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            effective_max_tokens = max_tokens or self.default_max_tokens

            # 从配置中获取额外的生成参数
            try:
                rag_config = self.config_loader.get('rag', {})
                top_p = rag_config.get('top_p', 1.0)
                frequency_penalty = rag_config.get('frequency_penalty', 0.0)
                presence_penalty = rag_config.get('presence_penalty', 0.0)
                repetition_penalty = rag_config.get('repetition_penalty', 1.0)
            except:
                top_p = 1.0
                frequency_penalty = 0.0
                presence_penalty = 0.0
                repetition_penalty = 1.0

            # 强制使用 /v1/completions 端点，因为我们发送的是 raw prompt
            request_url = self.api_url
            if '/chat/completions' in request_url:
                request_url = request_url.replace('/chat/completions', '/completions')

            payload = {
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": effective_max_tokens,
                "top_p": top_p,
                "top_k": 40,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
                "repetition_penalty": repetition_penalty,
                "stream": True
            }

            # 打印调试信息
            logger.debug(f"API Request URL: {request_url}")
            # logger.debug(f"API Request Payload: {json.dumps(payload, ensure_ascii=False)}")

            response = requests.post(
                request_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.request_timeout
            )

            if response.status_code >= 400:
                logger.error(f"API Error Status: {response.status_code}")
                logger.error(f"API Error Response: {response.text}")

            response.raise_for_status()
            if not response.encoding:
                response.encoding = 'utf-8'

            content_type = response.headers.get('Content-Type', '').lower()
            # 对于 completions API, 通常返回的是 text/event-stream
            if 'text/event-stream' not in content_type and not response.headers.get('Transfer-Encoding') == 'chunked':
                # 处理非流式响应（不太常见，但以防万一）
                data = response.json()
                choices = data.get('choices', []) if isinstance(data, dict) else []
                if choices:
                    text = choices[0].get('text', '')
                    if text:
                        yield _normalize_text(text)
                return

            # 处理流式响应
            # 简化逻辑：直接输出所有内容，不进行

            buffer = ""
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue

                # 如果我们在buffer模式（上一行JSON不完整），我们需要拼接
                if buffer:
                    # 恢复被iter_lines消耗的换行符（假设分裂是因为换行符）
                    current_text = buffer + "\n" + raw_line
                else:
                    # 新的行，处理 data: 前缀
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith('data:'):
                        current_text = line[5:].strip()
                    elif line == '[DONE]':
                        continue
                    else:
                        # 可能是注释或无效行
                        continue

                if not current_text or current_text == '[DONE]':
                    continue

                try:
                    chunk = json.loads(current_text)
                    buffer = "" # 解析成功，清空buffer
                except json.JSONDecodeError:
                    # 解析失败，可能是因为JSON不完整（被换行符切断），存入buffer等待下一行
                    buffer = current_text
                    continue

                choices = chunk.get('choices', []) if isinstance(chunk, dict) else []
                if not choices:
                    continue

                text_piece = choices[0].get('text', '')
                if not text_piece:
                    continue

                # DEBUG: Print raw text piece to console to verify what model sends
                # print(f"DEBUG CHUNK: {repr(text_piece)}")

                # 直接输出，不做任何过滤
                yield _normalize_text_wrapper(text_piece)

        except Exception as e:
            logger.error(f"API调用失败: {e}")
            yield f"错误：API调用失败。" 