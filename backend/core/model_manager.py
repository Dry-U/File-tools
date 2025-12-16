# src/core/model_manager.py
import os
import time
import json
from typing import Optional, Generator, Any
try:
    from llama_cpp import Llama  # llama-cpp-python
except ImportError:
    Llama = None
import requests  # 用于WSL API fallback
# 尝试导入win32api，如失败则设置为None
try:
    import win32api  # 用于获取Windows磁盘驱动器
except ImportError:
    win32api = None
from backend.utils.logger import setup_logger
from backend.utils.config_loader import ConfigLoader
from backend.core.vram_manager import VRAMManager
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

    # 检测是否存在较多的扩展拉丁字符，可能是UTF-8被当作Latin-1解析后的“乱码”
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
    """模型管理器：自动选择和自适应推理（基于文档1.4和2.2）"""

    def __init__(self, config_loader):
        self.optimizer = InferenceOptimizer(self)
        self.config_loader = config_loader
        self.vram_manager = VRAMManager(config_loader)
        self.current_model: Optional[Any] = None
        self.current_model_name: str = self.auto_select_model()
        # 获取配置时增加健壮性检查
        try:
            self.interface_type: str = config_loader.get('ai_model', 'interface_type', 'local')
            self.api_url: str = config_loader.get('ai_model', 'api_url', 'http://localhost:8000/v1/completions')
            self.api_key: str = config_loader.get('ai_model', 'api_key', '')
            self.api_format: str = config_loader.get('ai_model', 'api_format', 'openai_chat')
            self.api_model_name: str = config_loader.get('ai_model', 'api_model', self.current_model_name)
            self.system_prompt: str = config_loader.get('ai_model', 'system_prompt', '')
            self.request_timeout: int = config_loader.getint('ai_model', 'request_timeout', 60)
            self.default_max_tokens: int = config_loader.getint('ai_model', 'max_tokens', 2048)
        except Exception as e:
            print(f"获取模型配置失败: {str(e)}")
            logger.error(f"获取模型配置失败: {str(e)}")
            # 使用默认值
            self.interface_type = 'local'
            self.api_url = 'http://localhost:8000/v1/completions'
            self.api_key = ''
            self.api_format = 'openai_chat'
            self.api_model_name = self.current_model_name
            self.system_prompt = ''
            self.request_timeout = 60
            self.default_max_tokens = 2048

        if self.interface_type == 'api':
            self.current_model_name = self.api_model_name or self.current_model_name

    def auto_select_model(self) -> str:
        """根据硬件自动选择模型（基于文档代码）"""
        vram = self.vram_manager.available_vram()
        cpu_cores = os.cpu_count() or 0

        if vram >= 8 * 1024**3 and cpu_cores >= 8:
            return "nous-hermes-2-7b.Q4_K_M.gguf"
        elif vram >= 6 * 1024**3:
            return "mistral-7b-instruct-v0.2.Q5_K_M.gguf"
        elif vram >= 4 * 1024**3:
            return "qwen-7b-chat-v1.5.Q4_K_S.gguf"
        elif cpu_cores >= 6:
            return "phi-3-mini-4k-instruct.Q5_K_M.gguf"
        else:
            return "tinyllama-1.1b.Q8_0.gguf"

    def get_model(self) -> Optional[Any]:
        """获取或加载模型"""
        if self.current_model:
            self.vram_manager.update_last_used(self.current_model_name)
            return self.current_model

        if Llama is None:
            logger.warning("llama_cpp module not found. Cannot load local model.")
            return None

        self.current_model = self.vram_manager.load_model(self.current_model_name, Llama)
        return self.current_model

    def generate(self, prompt: str, session_id: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.7) -> Generator[str, None, None]:
        """根据配置的接口类型进行推理生成"""
        produced = False
        try:
            # 检查模型是否启用
            model_enabled = False
            try:
                model_enabled = self.config_loader.getboolean('ai_model', 'enabled', False)
            except Exception as e:
                print(f"检查模型启用状态失败: {str(e)}")
                logger.error(f"检查模型启用状态失败: {str(e)}")

            # 根据接口类型选择不同的生成方式
            if self.interface_type == 'local' and not model_enabled:
                for chunk in self._mock_generate(prompt):
                    produced = True
                    yield _normalize_text(chunk)
            elif self.interface_type == 'local':
                model = self.get_model()
                if model:
                    for token in model(prompt, max_tokens=max_tokens, temperature=temperature, stream=True):
                        text_piece = token
                        if isinstance(token, dict):
                            choices = token.get('choices', [])
                            if choices and isinstance(choices, list):
                                choice = choices[0]
                                if isinstance(choice, dict):
                                    text_piece = choice.get('text', '')
                                else:
                                    text_piece = choice
                        if text_piece:
                            produced = True
                            yield _normalize_text(str(text_piece))
                    self.vram_manager.update_last_used(self.current_model_name)
                else:
                    produced = True
                    yield "错误：无法加载本地模型。"
            elif self.interface_type == 'wsl':
                for chunk in self._wsl_generate(prompt, max_tokens, temperature):
                    produced = True
                    yield _normalize_text(chunk)
            elif self.interface_type == 'api':
                for chunk in self._api_generate(prompt, max_tokens, temperature):
                    produced = True
                    yield _normalize_text(chunk)
            else:
                produced = True
                yield f"错误：未知的AI接口类型: {self.interface_type}"
        except Exception as e:
            logger.error(f"生成失败: {e}")
            yield f"错误：{str(e)}"
            produced = True

        if not produced:
            for chunk in self.optimizer.generate(prompt, session_id, max_tokens, temperature):
                yield _normalize_text(chunk)

    def _wsl_generate(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """WSL API生成"""
        try:
            response = requests.post(self.api_url, json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')
        except Exception as e:
            logger.error(f"WSL API失败: {e}")
            yield f"错误：WSL API调用失败。"

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
                "top_k": 50,
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
            # 简化逻辑：直接输出所有内容，不进行 <think> 标签过滤
            # 这样可以避免因过滤逻辑导致的缺字或截断问题，同时让用户看到完整的思考过程（如果模型输出了的话）
            
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

    def _mock_generate(self, prompt: str) -> Generator[str, None, None]:
        """模拟生成响应，用于模型禁用时"""
        yield "模拟响应: " + prompt