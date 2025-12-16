# -*- coding: utf-8 -*-
"""VRAM管理器模块 - 用于内存和性能优化"""
import os
import time
import logging
import psutil
import gc
import threading
from typing import Optional, Dict, Any

# 尝试导入GPU监控库
try:
    import GPUtil
    gpu_available = True
except ImportError:
    gpu_available = False
    logging.warning("GPUtil not found, GPU monitoring will be disabled. Install it with: pip install gputil")

logger = logging.getLogger(__name__)

class VRAMManager:
    """VRAM管理器，用于优化RAG系统性能，特别是在处理大上下文时"""

    def __init__(self, config):
        self.config = config
        self.models: Dict[str, Any] = {}
        self.last_used: Dict[str, float] = {}
        self.cache: Dict[str, Any] = {}
        self.cache_access_times: Dict[str, float] = {}
        self.cache_size = 0
        self.cache_lock = threading.Lock()

        # 从配置中获取模型目录 - 使用ConfigLoader的get方法
        self.models_dir = config.get('ai_model', 'model_path', './data/models')

        # 获取内存管理配置
        try:
            advanced_config = config.get('advanced', {})
            self.mem_limit = int(advanced_config.get('whoosh_mem_limit', 512))  # in MB
            self.max_cached_results = int(advanced_config.get('max_cached_results', 1000))
        except:
            self.mem_limit = 512  # default 512MB limit
            self.max_cached_results = 1000

        logger.info(f"内存管理器初始化，模型目录: {self.models_dir}, 内存限制: {self.mem_limit}MB, 最大缓存: {self.max_cached_results}")

    def available_vram(self) -> int:
        """获取可用VRAM信息 - 现在主要用于API接口"""
        if gpu_available:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    # 获取第一个GPU的可用内存
                    gpu = gpus[0]
                    # 返回可用内存（以字节为单位）
                    return int(gpu.memoryFree * 1024 * 1024)  # 转换为字节
            except Exception as e:
                logger.warning(f"无法获取GPU信息: {e}")

        # 如果无法获取GPU信息，返回一个合理的估计值
        return 8 * 1024**3  # 8GB

    def update_last_used(self, model_name: str) -> None:
        """更新模型最后使用时间 - 现在主要用于API接口"""
        self.last_used[model_name] = time.time()
        logger.debug(f"更新模型最后使用时间: {model_name}")

    def load_model(self, model_name: str, model_class, gpu_layers: Optional[int] = None) -> Optional[Any]:
        """加载模型到GPU或CPU - 现在主要用于API接口"""
        logger.warning(f"尝试加载本地模型 {model_name}，但本地模型支持已移除")
        return None

    def unload_model(self, model_name: str) -> bool:
        """卸载模型并释放内存 - 现在主要用于API接口"""
        logger.warning(f"尝试卸载本地模型 {model_name}，但本地模型支持已移除")
        return False

    def cleanup_unused_models(self, timeout_seconds: int = 300) -> int:
        """清理长时间未使用的模型 - 现在主要用于API接口"""
        logger.warning("本地模型清理功能已移除")
        return 0

    def get_loaded_models(self) -> list:
        """获取当前加载的所有模型名称 - 现在主要用于API接口"""
        logger.warning("本地模型列表功能已移除")
        return []

    def get_memory_usage(self):
        """Get current memory usage"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # in MB

    def should_limit_context(self):
        """Check if context should be limited based on memory usage"""
        current_memory = self.get_memory_usage()
        # If using more than 70% of memory limit, suggest limiting context (more conservative)
        return current_memory > (self.mem_limit * 0.7)

    def adjust_context_size(self, requested_size: int) -> int:
        """根据当前内存使用情况调整上下文大小"""
        if self.should_limit_context():
            # 如果内存紧张，减少到请求大小的50%
            return max(requested_size // 2, 500)  # 最小500字符
        else:
            # 内存充足时，可以使用请求的大小
            return requested_size

    def get_optimal_batch_size(self) -> int:
        """根据当前内存状况计算最佳批处理大小"""
        current_memory = self.get_memory_usage()
        memory_ratio = current_memory / self.mem_limit

        if memory_ratio > 0.8:
            return 1  # 内存紧张时使用最小批处理
        elif memory_ratio > 0.6:
            return 2  # 中等内存使用时使用中等批处理
        else:
            return 4  # 内存充足时使用较大批处理

    def get_gpu_info(self) -> Dict:
        """获取GPU信息（如果可用）"""
        if gpu_available:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_info = []
                    for gpu in gpus:
                        gpu_info.append({
                            'id': gpu.id,
                            'name': gpu.name,
                            'load': gpu.load,
                            'memory_util': gpu.memoryUtil,
                            'memory_free': gpu.memoryFree,
                            'memory_total': gpu.memoryTotal,
                            'temperature': gpu.temperature
                        })
                    return {'available': True, 'gpus': gpu_info}
            except Exception as e:
                logger.warning(f"无法获取GPU信息: {e}")

        return {'available': False, 'gpus': []}

    def cache_result(self, key: str, result: Any, size_estimate: int = 1):
        """Cache a result with size management"""
        with self.cache_lock:
            # Check if cache needs cleanup
            if len(self.cache) >= self.max_cached_results:
                self._cleanup_cache()

            # Store the result
            self.cache[key] = result
            self.cache_access_times[key] = time.time()
            self.cache_size += size_estimate

    def get_cached_result(self, key: str) -> Optional[Any]:
        """Get a cached result"""
        with self.cache_lock:
            if key in self.cache:
                self.cache_access_times[key] = time.time()  # Update access time
                return self.cache[key]
            return None

    def _cleanup_cache(self):
        """Clean up the cache using LRU strategy"""
        if not self.cache:
            return

        # Sort by access time (LRU)
        sorted_items = sorted(self.cache_access_times.items(), key=lambda x: x[1])

        # Remove oldest items until cache is under limit
        items_to_remove = max(1, len(self.cache) // 4)  # Remove 25% of items
        for key, _ in sorted_items[:items_to_remove]:
            if key in self.cache:
                del self.cache[key]
                del self.cache_access_times[key]
                self.cache_size -= 1  # Decrement cache size

    def clear_memory(self):
        """Clear memory cache"""
        with self.cache_lock:
            self.cache.clear()
            self.cache_access_times.clear()
            self.cache_size = 0
        gc.collect()

    def get_model_info(self, model_name: str) -> Optional[Dict]:
        """获取模型信息"""
        if model_name in self.models and model_name in self.last_used:
            return {
                'name': model_name,
                'path': os.path.join(self.models_dir, model_name),
                'last_used': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_used[model_name]))
            }
        return None

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance and memory statistics"""
        return {
            'memory_usage_mb': self.get_memory_usage(),
            'memory_limit_mb': self.mem_limit,
            'cache_size': len(self.cache),
            'cache_limit': self.max_cached_results,
            'should_limit_context': self.should_limit_context(),
            'gpu_info': self.get_gpu_info()
        }