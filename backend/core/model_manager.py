# src/core/model_manager.py
import os
import time
from typing import Optional, Generator
from llama_cpp import Llama  # llama-cpp-python
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

class ModelManager:
    """模型管理器：自动选择和自适应推理（基于文档1.4和2.2）"""

    def __init__(self, config_loader):
        self.optimizer = InferenceOptimizer(self)
        self.config_loader = config_loader
        self.vram_manager = VRAMManager(config_loader)
        self.current_model: Optional[Llama] = None
        self.current_model_name: str = self.auto_select_model()
        # 获取配置时增加健壮性检查
        try:
            self.interface_type: str = config_loader.get('model', 'interface_type', 'local')
            self.api_url: str = config_loader.get('model', 'api_url', 'http://localhost:8000/v1/completions')
            self.api_key: str = config_loader.get('model', 'api_key', '')
        except Exception as e:
            print(f"获取模型配置失败: {str(e)}")
            logger.error(f"获取模型配置失败: {str(e)}")
            # 使用默认值
            self.interface_type = 'local'
            self.api_url = 'http://localhost:8000/v1/completions'
            self.api_key = ''

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

    def get_model(self) -> Optional[Llama]:
        """获取或加载模型"""
        if self.current_model:
            self.vram_manager.update_last_used(self.current_model_name)
            return self.current_model
        
        self.current_model = self.vram_manager.load_model(self.current_model_name, Llama)
        return self.current_model

    def generate(self, prompt: str, session_id: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.7) -> Generator[str, None, None]:
        """根据配置的接口类型进行推理生成"""
        try:
            # 检查模型是否启用
            model_enabled = False
            try:
                model_enabled = self.config_loader.getboolean('model', 'enabled', False)
            except Exception as e:
                print(f"检查模型启用状态失败: {str(e)}")
                logger.error(f"检查模型启用状态失败: {str(e)}")
            
            # 根据接口类型选择不同的生成方式
            if self.interface_type == 'local' and not model_enabled:
                # 如果是本地模式但模型被禁用，使用模拟响应
                yield from self._mock_generate(prompt)
            elif self.interface_type == 'local':
                # 本地模型生成
                model = self.get_model()
                if model:
                    for token in model(prompt, max_tokens=max_tokens, temperature=temperature, stream=True):
                        yield token['choices'][0]['text']
                    self.vram_manager.update_last_used(self.current_model_name)
                else:
                    yield "错误：无法加载本地模型。"
            elif self.interface_type == 'wsl':
                # WSL API生成
                yield from self._wsl_generate(prompt, max_tokens, temperature)
            elif self.interface_type == 'api':
                # 通用API生成
                yield from self._api_generate(prompt, max_tokens, temperature)
            else:
                yield f"错误：未知的AI接口类型: {self.interface_type}"
        except Exception as e:
            logger.error(f"生成失败: {e}")
            yield f"错误：{str(e)}"
        
        # 使用优化器进一步处理
        yield from self.optimizer.generate(prompt, session_id, max_tokens, temperature)

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
        """通用API生成"""
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            
            # 如果配置了API密钥，添加到请求头
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            response = requests.post(self.api_url, json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }, headers=headers, stream=True)
            
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    # 根据不同API的响应格式进行处理
                    # 这里简单处理，实际使用时需要根据具体API的响应格式进行调整
                    yield line.decode('utf-8')
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            yield f"错误：API调用失败。"
            
    def _mock_generate(self, prompt: str) -> Generator[str, None, None]:
        """模拟生成响应，用于模型禁用时"""
        yield "模拟响应: " + prompt