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
        """获取可用VRAM信息"""
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
        # 返回8GB作为默认值，这样会选择较大的模型
        return 8 * 1024**3  # 8GB

    def update_last_used(self, model_name: str) -> None:
        """更新模型最后使用时间"""
        self.last_used[model_name] = time.time()
        logger.debug(f"更新模型最后使用时间: {model_name}")

    def load_model(self, model_name: str, model_class, gpu_layers: Optional[int] = None) -> Optional[Any]:
        """加载模型到GPU或CPU"""
        try:
            # 检查模型文件是否存在
            model_path = os.path.join(self.models_dir, model_name)
            if not os.path.exists(model_path):
                logger.warning(f"模型文件不存在: {model_path}")
                # 创建一个空文件作为占位符
                os.makedirs(self.models_dir, exist_ok=True)
                with open(model_path, 'w', encoding='utf-8') as f:
                    f.write("# 模型文件占位符")

            # 根据可用VRAM决定GPU层数
            if gpu_layers is None:
                available_vram = self.available_vram()
                if available_vram > 6 * 1024**3:  # 如果有超过6GB VRAM
                    gpu_layers = 20  # 使用较多GPU层
                elif available_vram > 4 * 1024**3:  # 如果有超过4GB VRAM
                    gpu_layers = 10  # 使用中等GPU层
                else:
                    gpu_layers = 0  # 使用CPU模式

            # 尝试初始化模型
            model = model_class(model_path=model_path, n_ctx=4096, n_gpu_layers=gpu_layers)
            self.models[model_name] = model
            self.update_last_used(model_name)
            logger.info(f"模型加载成功: {model_name}, GPU层数: {gpu_layers}")
            return model
        except Exception as e:
            logger.error(f"加载模型失败: {model_name}, 错误: {str(e)}")
            # 尝试使用CPU模式加载
            try:
                model = model_class(model_path=model_path, n_ctx=4096, n_gpu_layers=0)
                self.models[model_name] = model
                self.update_last_used(model_name)
                logger.info(f"模型加载成功 (CPU模式): {model_name}")
                return model
            except Exception as e2:
                logger.error(f"CPU模式加载模型也失败: {str(e2)}")
                return None

    def unload_model(self, model_name: str) -> bool:
        """卸载模型并释放内存"""
        if model_name in self.models:
            model = self.models[model_name]
            # 尝试释放模型占用的资源
            try:
                if hasattr(model, 'unload'):
                    model.unload()
                elif hasattr(model, '__del__'):
                    del model
            except Exception as e:
                logger.warning(f"卸载模型时出现问题: {str(e)}")

            del self.models[model_name]
            if model_name in self.last_used:
                del self.last_used[model_name]
            logger.info(f"模型卸载成功: {model_name}")
            # 强制进行垃圾回收
            gc.collect()
            return True
        return False

    def cleanup_unused_models(self, timeout_seconds: int = 300) -> int:
        """清理长时间未使用的模型"""
        current_time = time.time()
        unloaded_count = 0
        for model_name, last_used_time in list(self.last_used.items()):
            if current_time - last_used_time > timeout_seconds:
                self.unload_model(model_name)
                unloaded_count += 1
        return unloaded_count

    def get_loaded_models(self) -> list:
        """获取当前加载的所有模型名称"""
        return list(self.models.keys())

    def get_memory_usage(self):
        """Get current memory usage"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # in MB

    def should_limit_context(self):
        """Check if context should be limited based on memory usage"""
        current_memory = self.get_memory_usage()
        # If using more than 80% of memory limit, suggest limiting context
        return current_memory > (self.mem_limit * 0.8)

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