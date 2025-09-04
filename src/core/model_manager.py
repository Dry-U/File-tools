# src/core/model_manager.py
import os
import time
from typing import Optional, Generator
# from llama_cpp import Llama  # llama-cpp-python (临时注释掉以避免DLL加载问题)
import requests  # 用于WSL API fallback
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.core.vram_manager import VRAMManager

# 临时定义缺失的类
class InferenceOptimizer:
    def __init__(self, model_manager):
        self.model_manager = model_manager
    def generate(self, prompt, session_id=None, max_tokens=512, temperature=0.7):
        # 模拟生成
        yield "模拟响应: " + prompt

# 临时模拟Llama类以避免DLL加载问题
class Llama:
    def __init__(self, model_path, n_ctx=4096, n_gpu_layers=0):
        pass
    def __call__(self, prompt, max_tokens=512, temperature=0.7, stream=True):
        # 模拟生成结果
        class MockResponse:
            def __init__(self, text):
                self.text = text
        return [{"choices": [{"text": "模拟响应: " + prompt}]}]

logger = setup_logger()

class ModelManager:
    """模型管理器：自动选择和自适应推理（基于文档1.4和2.2）"""

    def __init__(self, config: ConfigLoader):
        self.optimizer = InferenceOptimizer(self)
        self.config = config
        self.vram_manager = VRAMManager(config)
        self.current_model: Optional[Llama] = None
        self.current_model_name: str = self.auto_select_model()
        self.wsl_api_url: str = "http://localhost:8000/v1/completions"  # WSL服务器API（从app.py启动）

    def auto_select_model(self) -> str:
        """根据硬件自动选择模型（基于文档代码）"""
        vram = self.vram_manager.available_vram()
        cpu_cores = os.cpu_count()
        
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

    def generate(self, prompt: str, session_id: str = None, max_tokens: int = 512, temperature: float = 0.7) -> Generator[str, None, None]:
        """自适应推理生成（优先本地，fallback到WSL API）"""
        model = self.get_model()
        if model:
            try:
                for token in model(prompt, max_tokens=max_tokens, temperature=temperature, stream=True):
                    yield token['choices'][0]['text']
                self.vram_manager.update_last_used(self.current_model_name)
            except Exception as e:
                logger.error(f"本地推理失败: {e}, fallback to WSL")
                yield from self._wsl_generate(prompt, max_tokens, temperature)
        else:
            yield from self._wsl_generate(prompt, max_tokens, temperature)
        return self.optimizer.generate(prompt, session_id, max_tokens, temperature)

    def _wsl_generate(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """Fallback到WSL API生成"""
        try:
            response = requests.post(self.wsl_api_url, json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield line.decode('utf-8')  # 假设流式输出文本
        except Exception as e:
            logger.error(f"WSL API失败: {e}")
            yield "错误：无法生成响应。"