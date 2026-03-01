"""测试工具函数"""
import time
import asyncio
import functools
from typing import Callable, Any, Optional
from pathlib import Path
import tempfile
import os


def create_test_file(
    content: str,
    filename: str = "test.txt",
    directory: Optional[Path] = None,
    encoding: str = "utf-8"
) -> Path:
    """
    创建临时测试文件

    Args:
        content: 文件内容
        filename: 文件名
        directory: 目标目录（默认为临时目录）
        encoding: 文件编码

    Returns:
        创建的文件路径
    """
    if directory is None:
        directory = Path(tempfile.mkdtemp())

    file_path = directory / filename
    file_path.write_text(content, encoding=encoding)
    return file_path


def create_test_binary_file(
    size: int,
    filename: str = "test.bin",
    directory: Optional[Path] = None
) -> Path:
    """
    创建临时二进制测试文件

    Args:
        size: 文件大小（字节）
        filename: 文件名
        directory: 目标目录

    Returns:
        创建的文件路径
    """
    if directory is None:
        directory = Path(tempfile.mkdtemp())

    file_path = directory / filename
    file_path.write_bytes(os.urandom(size))
    return file_path


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.1
) -> bool:
    """
    异步等待条件满足

    Args:
        condition: 条件函数
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        是否在超时前满足条件
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition():
            return True
        await asyncio.sleep(interval)
    return False


def measure_performance(
    func: Optional[Callable] = None,
    *,
    threshold_ms: Optional[float] = None,
    iterations: int = 1
) -> Callable:
    """
    性能测量装饰器

    Args:
        func: 被装饰的函数
        threshold_ms: 性能阈值（毫秒），超过则发出警告
        iterations: 迭代次数

    Returns:
        装饰器函数
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs) -> Any:
            total_time = 0
            result = None

            for _ in range(iterations):
                start = time.perf_counter()
                result = f(*args, **kwargs)
                end = time.perf_counter()
                total_time += (end - start) * 1000  # 转换为毫秒

            avg_time = total_time / iterations
            print(f"{f.__name__}: {avg_time:.2f}ms (avg over {iterations} iterations)")

            if threshold_ms and avg_time > threshold_ms:
                print(f"WARNING: {f.__name__} exceeded threshold of {threshold_ms}ms")

            return result

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs) -> Any:
            total_time = 0
            result = None

            for _ in range(iterations):
                start = time.perf_counter()
                result = await f(*args, **kwargs)
                end = time.perf_counter()
                total_time += (end - start) * 1000

            avg_time = total_time / iterations
            print(f"{f.__name__}: {avg_time:.2f}ms (avg over {iterations} iterations)")

            if threshold_ms and avg_time > threshold_ms:
                print(f"WARNING: {f.__name__} exceeded threshold of {threshold_ms}ms")

            return result

        if asyncio.iscoroutinefunction(f):
            return async_wrapper
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def assert_dict_subset(subset: dict, superset: dict) -> bool:
    """
    检查字典是否为另一个字典的子集

    Args:
        subset: 期望包含的子集
        superset: 被检查的超集

    Returns:
        是否包含
    """
    for key, value in subset.items():
        if key not in superset:
            return False
        if superset[key] != value:
            return False
    return True


def create_mock_file_stats(
    size: int = 1024,
    modified: float = 1700000000.0,
    created: float = 1700000000.0
) -> os.stat_result:
    """
    创建模拟的文件统计信息

    Args:
        size: 文件大小
        modified: 修改时间
        created: 创建时间

    Returns:
        模拟的 stat_result
    """
    # 使用 namedtuple 模拟 stat_result
    from collections import namedtuple
    StatResult = namedtuple('StatResult', ['st_size', 'st_mtime', 'st_ctime'])
    return StatResult(st_size=size, st_mtime=modified, st_ctime=created)
