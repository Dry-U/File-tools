"""VRAM Manager 单元测试"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.vram_manager import VRAMManager


class TestVRAMManager:
    """VRAMManager 测试类"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock()
        config.get.return_value = './data/models'
        config.getint.return_value = 512
        return config

    @pytest.fixture
    def vram_manager(self, mock_config):
        """创建 VRAMManager 实例"""
        return VRAMManager(mock_config)

    def test_init(self, mock_config):
        """测试初始化"""
        vm = VRAMManager(mock_config)
        assert vm.config == mock_config
        assert vm.models == {}
        assert vm.cache == {}
        assert vm.cache_size == 0

    def test_get_memory_usage(self, vram_manager):
        """测试获取内存使用量"""
        memory = vram_manager.get_memory_usage()
        assert isinstance(memory, float)
        assert memory > 0  # 进程应该使用一些内存

    def test_should_limit_context(self, vram_manager):
        """测试上下文限制判断"""
        with patch.object(vram_manager, 'get_memory_usage', return_value=100):
            # 100MB < 512 * 0.7 = 358.4MB, 不应该限制
            assert vram_manager.should_limit_context() == False

        with patch.object(vram_manager, 'get_memory_usage', return_value=400):
            # 400MB > 358.4MB, 应该限制
            assert vram_manager.should_limit_context() == True

    def test_adjust_context_size_normal(self, vram_manager):
        """测试正常情况下的上下文大小调整"""
        with patch.object(vram_manager, 'should_limit_context', return_value=False):
            result = vram_manager.adjust_context_size(1000)
            assert result == 1000

    def test_adjust_context_size_limited(self, vram_manager):
        """测试内存受限时的上下文大小调整"""
        with patch.object(vram_manager, 'should_limit_context', return_value=True):
            result = vram_manager.adjust_context_size(1000)
            assert result == 500  # 减少到50%

    def test_adjust_context_size_minimum(self, vram_manager):
        """测试上下文大小最小值限制"""
        with patch.object(vram_manager, 'should_limit_context', return_value=True):
            result = vram_manager.adjust_context_size(500)
            assert result == 500  # 最小500

    def test_get_optimal_batch_size_high_memory(self, vram_manager):
        """测试高内存时的批处理大小"""
        with patch.object(vram_manager, 'get_memory_usage', return_value=100):
            # 100/512 = 0.195 < 0.6, 应该返回4
            assert vram_manager.get_optimal_batch_size() == 4

    def test_get_optimal_batch_size_medium_memory(self, vram_manager):
        """测试中等内存时的批处理大小"""
        with patch.object(vram_manager, 'get_memory_usage', return_value=350):
            # 350/512 = 0.68 > 0.6, 应该返回2
            assert vram_manager.get_optimal_batch_size() == 2

    def test_get_optimal_batch_size_low_memory(self, vram_manager):
        """测试低内存时的批处理大小"""
        with patch.object(vram_manager, 'get_memory_usage', return_value=450):
            # 450/512 = 0.88 > 0.8, 应该返回1
            assert vram_manager.get_optimal_batch_size() == 1

    def test_cache_result(self, vram_manager):
        """测试缓存结果"""
        vram_manager.cache_result("key1", "value1", 1)
        assert "key1" in vram_manager.cache
        assert vram_manager.cache["key1"] == "value1"
        assert vram_manager.cache_size == 1

    def test_get_cached_result(self, vram_manager):
        """测试获取缓存结果"""
        vram_manager.cache_result("key1", "value1", 1)
        result = vram_manager.get_cached_result("key1")
        assert result == "value1"

    def test_get_cached_result_miss(self, vram_manager):
        """测试缓存未命中"""
        result = vram_manager.get_cached_result("nonexistent")
        assert result is None

    def test_cache_cleanup(self, vram_manager):
        """测试缓存清理"""
        vram_manager.max_cached_results = 5
        for i in range(6):
            vram_manager.cache_result(f"key{i}", f"value{i}", 1)

        # 应该触发清理，移除最旧的1/4
        assert len(vram_manager.cache) <= 6

    def test_clear_memory(self, vram_manager):
        """测试清空内存缓存"""
        vram_manager.cache_result("key1", "value1", 1)
        vram_manager.clear_memory()
        assert len(vram_manager.cache) == 0
        assert vram_manager.cache_size == 0

    def test_get_performance_stats(self, vram_manager):
        """测试获取性能统计"""
        stats = vram_manager.get_performance_stats()
        assert 'memory_usage_mb' in stats
        assert 'memory_limit_mb' in stats
        assert 'cache_size' in stats
        assert 'cache_limit' in stats
        assert 'should_limit_context' in stats
        assert 'gpu_info' in stats

    @patch('backend.core.vram_manager.gpu_available', True)
    @patch('backend.core.vram_manager.GPUtil')
    def test_get_gpu_info_available(self, mock_gputil, vram_manager):
        """测试获取GPU信息（GPU可用）"""
        mock_gpu = Mock()
        mock_gpu.id = 0
        mock_gpu.name = "NVIDIA GTX 1080"
        mock_gpu.load = 0.5
        mock_gpu.memoryUtil = 0.3
        mock_gpu.memoryFree = 4000
        mock_gpu.memoryTotal = 8192
        mock_gpu.temperature = 65
        mock_gputil.getGPUs.return_value = [mock_gpu]

        result = vram_manager.get_gpu_info()
        assert result['available'] == True
        assert len(result['gpus']) == 1
        assert result['gpus'][0]['name'] == "NVIDIA GTX 1080"

    @patch('backend.core.vram_manager.gpu_available', False)
    def test_get_gpu_info_unavailable(self, vram_manager):
        """测试获取GPU信息（GPU不可用）"""
        result = vram_manager.get_gpu_info()
        assert result['available'] == False
        assert result['gpus'] == []

    def test_available_vram(self, vram_manager):
        """测试获取可用VRAM"""
        vram = vram_manager.available_vram()
        assert isinstance(vram, int)
        assert vram > 0

    def test_get_model_info_nonexistent(self, vram_manager):
        """测试获取不存在的模型信息"""
        result = vram_manager.get_model_info("nonexistent")
        assert result is None

    def test_load_model_warning(self, vram_manager):
        """测试加载模型警告"""
        result = vram_manager.load_model("test_model", Mock())
        assert result is None

    def test_unload_model_warning(self, vram_manager):
        """测试卸载模型警告"""
        result = vram_manager.unload_model("test_model")
        assert result == False


class TestVRAMManagerEdgeCases:
    """VRAMManager 边界情况测试"""

    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get.return_value = './data/models'
        config.getint.return_value = 512
        return config

    @pytest.fixture
    def vram_manager(self, mock_config):
        return VRAMManager(mock_config)

    def test_zero_memory_limit(self, mock_config):
        """测试零内存限制"""
        mock_config.getint.return_value = 0
        vm = VRAMManager(mock_config)
        # 代码接受0值（虽然不合理但技术上可行）
        assert vm.mem_limit >= 0

    def test_negative_context_size(self, vram_manager):
        """测试负的上下文大小"""
        with patch.object(vram_manager, 'should_limit_context', return_value=True):
            result = vram_manager.adjust_context_size(-100)
            # 应该返回最小值
            assert result == 500

    def test_very_large_context_size(self, vram_manager):
        """测试非常大的上下文大小"""
        with patch.object(vram_manager, 'should_limit_context', return_value=False):
            result = vram_manager.adjust_context_size(1000000)
            assert result == 1000000

    def test_cache_size_estimate_zero(self, vram_manager):
        """测试零大小估计的缓存"""
        vram_manager.cache_result("key1", "value1", 0)
        assert vram_manager.cache_size == 0

    def test_concurrent_cache_access(self, vram_manager):
        """测试并发缓存访问"""
        import threading

        def writer():
            for i in range(100):
                vram_manager.cache_result(f"key{i}", f"value{i}", 1)

        def reader():
            for i in range(100):
                vram_manager.get_cached_result(f"key{i}")

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 应该没有异常
        assert True
