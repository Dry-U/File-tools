# src/core/vram_manager.py
import time
from typing import Dict, Any, Optional
import psutil
import GPUtil
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader

logger = setup_logger()

class VRAMManager:
    """显存优化管理器：监控和释放资源（基于文档4.1）"""

    def __init__(self, config: ConfigLoader):
        self.config = config
        self.model_cache: Dict[str, Dict[str, Any]] = {}  # {model_name: {'model': Llama, 'last_used': time, 'size': int}}
        self.current_vram: int = 0  # 当前占用显存（字节）
        self.timeout: int = 600  # 未使用超时（秒）

    def available_vram(self) -> int:
        """获取可用显存（使用GPUtil）"""
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                return int(gpus[0].memoryFree * 1024 * 1024)  # MB to bytes
            return 0
        except Exception as e:
            logger.warning(f"GPU检测失败: {e}, fallback to 0")
            return 0

    def get_model_size(self, model_name: str) -> int:
        """估算模型显存占用（基于文档1.4的预定义大小，单位bytes）"""
        sizes = {
            'nous-hermes-2-7b.Q4_K_M.gguf': 6.5 * 1024**3,
            'mistral-7b-instruct-v0.2.Q5_K_M.gguf': 4.5 * 1024**3,
            'qwen-7b-chat-v1.5.Q4_K_S.gguf': 4.2 * 1024**3,
            'phi-3-mini-4k-instruct.Q5_K_M.gguf': 2.8 * 1024**3,
            'tinyllama-1.1b.Q8_0.gguf': 1.5 * 1024**3,
        }
        return sizes.get(model_name, 4 * 1024**3)  # 默认4GB

    def load_model(self, model_name: str, llama_class: Any) -> Optional[Any]:  # llama_class is Llama from llama_cpp
        """加载模型，显存感知（基于文档4.1）"""
        model_size = self.get_model_size(model_name)
        available = self.available_vram()
        
        if model_size > available:
            self.release_unused_models()
            available = self.available_vram()
            if model_size > available:
                logger.warning(f"显存不足，尝试加载更低量化模型: {model_name}")
                model_name = self._get_lower_quant_model(model_name)
                model_size = self.get_model_size(model_name)
                if model_size > available:
                    raise ValueError(f"显存不足，无法加载模型: {model_name}")
        
        try:
            model_path = self.config.get('model', 'model_dir') + '/' + model_name
            model = llama_class(
                model_path=model_path,
                n_gpu_layers=-1 if self.config.get('model', 'inference', 'use_gpu') else 0,
                n_ctx=self.config.get('model', 'inference', 'max_context_length', 4096),
                seed=42
            )
            self.model_cache[model_name] = {
                'model': model,
                'last_used': time.time(),
                'size': model_size
            }
            self.current_vram += model_size
            logger.info(f"模型加载成功: {model_name}, 占用 {model_size / 1024**3:.2f} GB")
            return model
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            return None

    def release_unused_models(self, timeout: Optional[int] = None):
        """释放未使用模型（基于超时）"""
        timeout = timeout or self.timeout
        current_time = time.time()
        to_release = []
        for name, info in list(self.model_cache.items()):
            if current_time - info['last_used'] > timeout:
                del info['model']  # 释放模型
                self.current_vram -= info['size']
                to_release.append(name)
        
        for name in to_release:
            del self.model_cache[name]
        
        if to_release:
            logger.info(f"释放未使用模型: {to_release}")

    def _get_lower_quant_model(self, model_name: str) -> str:
        """回退到更低量化级别（e.g., Q4 instead of Q5）"""
        if 'Q5' in model_name:
            return model_name.replace('Q5', 'Q4')
        elif 'Q4' in model_name:
            return model_name.replace('Q4', 'Q3')
        return 'tinyllama-1.1b.Q8_0.gguf'  # 最终fallback

    def update_last_used(self, model_name: str):
        """更新模型最后使用时间"""
        if model_name in self.model_cache:
            self.model_cache[model_name]['last_used'] = time.time()