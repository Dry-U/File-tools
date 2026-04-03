"""
依赖注入函数 - 线程安全的组件访问
"""

import os
import stat
import threading
import urllib.parse
from pathlib import Path
from fastapi import Depends
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def get_rate_limiter(config_loader=None):
    """获取或初始化限流器"""
    from backend.api.main import get_rate_limiter as main_get_rate_limiter

    # 直接调用 main.py 中的 get_rate_limiter 函数
    return main_get_rate_limiter(config_loader)


# 全局状态引用（由 main.py 初始化）- 线程安全访问
_app = None
_app_lock = threading.Lock()


def set_app(app):
    """设置全局应用实例"""
    global _app
    with _app_lock:
        _app = app


def get_app():
    """获取全局应用实例"""
    with _app_lock:
        return _app


def get_config_loader():
    """获取配置加载器（单例）"""
    if _app is None:
        # 如果_app未初始化，返回一个默认的ConfigLoader
        return ConfigLoader()
    if not hasattr(_app.state, "config_loader"):
        _app.state.config_loader = ConfigLoader()
    return _app.state.config_loader


def get_index_manager(config_loader: ConfigLoader = Depends(get_config_loader)):
    """获取索引管理器"""
    if _app is None:
        # 如果_app未初始化，创建一个新的IndexManager实例
        from backend.core.index_manager import IndexManager

        return IndexManager(config_loader)
    if not hasattr(_app.state, "index_manager"):
        from backend.core.index_manager import IndexManager

        _app.state.index_manager = IndexManager(config_loader)
    return _app.state.index_manager


def get_search_engine(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager=Depends(get_index_manager),
):
    """获取搜索引擎"""
    if _app is None:
        # 如果_app未初始化，创建一个新的SearchEngine实例
        from backend.core.search_engine import SearchEngine

        return SearchEngine(index_manager, config_loader)
    if not hasattr(_app.state, "search_engine"):
        from backend.core.search_engine import SearchEngine

        _app.state.search_engine = SearchEngine(index_manager, config_loader)
    return _app.state.search_engine


def get_file_scanner(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager=Depends(get_index_manager),
):
    """获取文件扫描器"""
    if _app is None:
        # 如果_app未初始化，创建一个新的FileScanner实例
        from backend.core.file_scanner import FileScanner

        return FileScanner(config_loader, None, index_manager)
    if not hasattr(_app.state, "file_scanner"):
        from backend.core.file_scanner import FileScanner

        _app.state.file_scanner = FileScanner(config_loader, None, index_manager)
    return _app.state.file_scanner


def get_rag_pipeline(
    config_loader: ConfigLoader = Depends(get_config_loader),
    search_engine=Depends(get_search_engine),
):
    """获取RAG管道（可选，禁用时返回None）"""
    if _app is None:
        # 如果_app未初始化，按需创建RAGPipeline实例
        if config_loader.getboolean("ai_model", "enabled", False):
            from backend.core.model_manager import ModelManager
            from backend.core.rag_pipeline import RAGPipeline

            model_manager = ModelManager(config_loader)
            logger.info("RAG管道初始化完成")
            return RAGPipeline(model_manager, config_loader, search_engine)
        else:
            return None
    if not hasattr(_app.state, "rag_pipeline"):
        if config_loader.getboolean("ai_model", "enabled", False):
            from backend.core.model_manager import ModelManager
            from backend.core.rag_pipeline import RAGPipeline

            model_manager = ModelManager(config_loader)
            _app.state.rag_pipeline = RAGPipeline(
                model_manager, config_loader, search_engine
            )
            logger.info("RAG管道初始化完成")
        else:
            _app.state.rag_pipeline = None
    return _app.state.rag_pipeline


def get_file_monitor(
    config_loader: ConfigLoader = Depends(get_config_loader),
    index_manager=Depends(get_index_manager),
    file_scanner=Depends(get_file_scanner),
):
    """获取文件监控器"""
    if _app is None:
        # 如果_app未初始化，创建一个新的FileMonitor实例
        from backend.core.file_monitor import FileMonitor

        file_monitor = FileMonitor(config_loader, index_manager, file_scanner)
        if config_loader.getboolean("monitor", "enabled", False):
            file_monitor.start_monitoring()
            logger.info("文件监控已启动")
        return file_monitor
    if not hasattr(_app.state, "file_monitor"):
        from backend.core.file_monitor import FileMonitor

        _app.state.file_monitor = FileMonitor(
            config_loader, index_manager, file_scanner
        )
        if config_loader.getboolean("monitor", "enabled", False):
            _app.state.file_monitor.start_monitoring()
            logger.info("文件监控已启动")
    return _app.state.file_monitor


def get_is_path_allowed():
    """返回 is_path_allowed 函数作为依赖注入"""
    from backend.api.dependencies import is_path_allowed as _is_path_allowed

    return _is_path_allowed


def get_resolve_path_if_allowed():
    """返回 resolve_path_if_allowed 函数作为依赖注入"""
    from backend.api.dependencies import resolve_path_if_allowed as _resolve_path_if_allowed

    return _resolve_path_if_allowed


def is_path_allowed(path: str, config_loader: ConfigLoader) -> bool:
    """
    检查路径是否在允许范围内，防止路径遍历攻击

    安全特性：
    1. 使用 Path.resolve() 解析符号链接和相对路径
    2. 使用 Path.relative_to() 确保路径在允许目录内
    3. 检查非法字符和路径遍历模式
    4. 检查空字节注入攻击
    5. 检查 URL 编码的路径遍历
    6. 检查符号链接
    """
    if not path or not isinstance(path, str):
        return False

    # 检查空字节注入攻击
    if "\x00" in path:
        logger.warning(f"路径包含空字节: {path[:50]}...")
        return False

    # URL 解码检查 - 防止编码的路径遍历攻击
    try:
        decoded_path = urllib.parse.unquote(path)
        double_decoded = urllib.parse.unquote(decoded_path)
        # 检查解码后的路径是否包含遍历模式
        for decoded in [decoded_path, double_decoded]:
            if ".." in decoded or "//" in decoded or "/./" in decoded:
                logger.warning(f"路径包含编码的遍历模式: {path[:50]}...")
                return False
    except Exception as e:
        logger.warning(f"URL 解码失败: {path[:50]}... - {e}")
        return False

    # 标准化路径 - 去除引号
    path = path.strip('"').strip("'")

    # 检查明显的路径遍历模式（在解码后再次检查）
    if ".." in path or path.startswith("//"):
        logger.warning(f"路径包含遍历模式: {path[:50]}...")
        return False

    # 检查绝对路径下的路径遍历模式（如 C:\Windows\..\secret.txt）
    normalized_check = os.path.normpath(path)
    if ".." in normalized_check:
        logger.warning(f"路径包含规范化后的遍历模式: {path[:50]}...")
        return False

    try:
        # 使用 resolve() 解析符号链接和相对路径，获取真实绝对路径
        # resolve() 会跟随符号链接，所以我们可以直接检查是否为符号链接
        original_path = Path(path)

        # 检查是否为符号链接（在 resolve 之前检查）
        try:
            if original_path.is_symlink():
                logger.warning(f"路径是符号链接，拒绝访问: {path[:50]}...")
                return False
        except (OSError, ValueError):
            # 如果无法检查符号链接状态，继续处理
            pass

        file_path = original_path.resolve()

        # 再次检查 resolve 后的路径是否为符号链接
        # 这可以捕获指向符号链接的快捷方式
        try:
            if file_path.is_symlink():
                logger.warning(f"解析后的路径是符号链接，拒绝访问: {file_path}")
                return False
        except (OSError, ValueError):
            pass

        # 注意：不在这里检查 exists() 以避免 TOCTOU 竞态条件
        # 让后续的文件操作自己处理不存在的情况
    except (OSError, ValueError) as e:
        logger.warning(f"路径解析失败: {path[:50]}... - {e}")
        return False

    # 获取允许的扫描路径
    scan_paths = config_loader.get("file_scanner", "scan_paths", "")
    if not scan_paths:
        logger.warning("未配置扫描路径，拒绝所有文件访问")
        return False

    # 构建允许的路径列表
    allowed_paths = []
    if isinstance(scan_paths, str):
        path_list = [p.strip() for p in scan_paths.split(";") if p.strip()]
    elif isinstance(scan_paths, list):
        path_list = scan_paths
    else:
        path_list = []

    for sp in path_list:
        sp = str(sp).strip()
        if sp:
            try:
                allowed_path = Path(sp).resolve()
                if allowed_path.exists() and allowed_path.is_dir():
                    allowed_paths.append(allowed_path)
            except (OSError, ValueError):
                logger.debug(f"无效的允许路径: {sp}")
                continue

    if not allowed_paths:
        logger.warning("没有有效的允许路径")
        return False

    # 使用 relative_to 检查路径是否在允许范围内
    # 这比 startswith 更安全，因为 "C:\allowed\file.txt" 不会匹配 "C:\allowed_malicious\file.txt"
    for allowed_path in allowed_paths:
        try:
            file_path.relative_to(allowed_path)
            return True
        except ValueError:
            # 路径不在此允许目录内，继续检查下一个
            continue

    # 安全日志：不泄露完整路径
    safe_path_name = file_path.name if len(file_path.parts) > 0 else "unknown"
    logger.warning(f"路径不在允许范围内: ...{safe_path_name}")
    return False


def resolve_path_if_allowed(path: str, config_loader: ConfigLoader) -> Path | None:
    """
    检查路径是否在允许范围内，如果允许则返回解析后的 Path 对象。

    这是 is_path_allowed 的增强版本，返回解析后的路径以避免 TOCTOU 问题。
    调用方应直接使用返回的路径，而不是重新解析。

    Args:
        path: 要检查的路径
        config_loader: 配置加载器

    Returns:
        解析后的 Path 对象（如果允许），否则返回 None
    """
    if not path or not isinstance(path, str):
        return None

    # 检查空字节注入攻击
    if "\x00" in path:
        logger.warning(f"路径包含空字节: {path[:50]}...")
        return None

    # URL 解码检查
    try:
        decoded_path = urllib.parse.unquote(path)
        double_decoded = urllib.parse.unquote(decoded_path)
        for decoded in [decoded_path, double_decoded]:
            if ".." in decoded or "//" in decoded or "/./" in decoded:
                logger.warning(f"路径包含编码的遍历模式: {path[:50]}...")
                return None
    except Exception as e:
        logger.warning(f"URL 解码失败: {path[:50]}... - {e}")
        return None

    # 标准化路径
    path = path.strip('"').strip("'")

    # 检查路径遍历模式
    if ".." in path or path.startswith("//"):
        logger.warning(f"路径包含遍历模式: {path[:50]}...")
        return None

    normalized_check = os.path.normpath(path)
    if ".." in normalized_check:
        logger.warning(f"路径包含规范化后的遍历模式: {path[:50]}...")
        return None

    try:
        original_path = Path(path)

        # 检查符号链接
        try:
            if original_path.is_symlink():
                logger.warning(f"路径是符号链接，拒绝访问: {path[:50]}...")
                return None
        except (OSError, ValueError):
            pass

        file_path = original_path.resolve()

        # 再次检查 resolve 后的符号链接
        try:
            if file_path.is_symlink():
                logger.warning(f"解析后的路径是符号链接，拒绝访问: {file_path}")
                return None
        except (OSError, ValueError):
            pass
    except (OSError, ValueError) as e:
        logger.warning(f"路径解析失败: {path[:50]}... - {e}")
        return None

    # 获取允许的扫描路径
    scan_paths = config_loader.get("file_scanner", "scan_paths", "")
    if not scan_paths:
        logger.warning("未配置扫描路径，拒绝所有文件访问")
        return None

    # 构建允许的路径列表
    allowed_paths = []
    if isinstance(scan_paths, str):
        path_list = [p.strip() for p in scan_paths.split(";") if p.strip()]
    elif isinstance(scan_paths, list):
        path_list = scan_paths
    else:
        path_list = []

    for sp in path_list:
        sp = str(sp).strip()
        if sp:
            try:
                allowed_path = Path(sp).resolve()
                if allowed_path.exists() and allowed_path.is_dir():
                    allowed_paths.append(allowed_path)
            except (OSError, ValueError):
                logger.debug(f"无效的允许路径: {sp}")
                continue

    if not allowed_paths:
        logger.warning("没有有效的允许路径")
        return None

    # 检查路径是否在允许范围内
    for allowed_path in allowed_paths:
        try:
            file_path.relative_to(allowed_path)
            return file_path  # 返回解析后的路径
        except ValueError:
            continue

    safe_path_name = file_path.name if len(file_path.parts) > 0 else "unknown"
    logger.warning(f"路径不在允许范围内: ...{safe_path_name}")
    return None


# O_NOFOLLOW 标志（防止通过符号链接跟踪读取文件）
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_RDONLY = os.O_RDONLY


def safe_read_file(
    file_path: str, config_loader: ConfigLoader, max_size: int = 10 * 1024 * 1024
) -> bytes:
    """安全读取文件内容，防止符号链接跟踪攻击（TOCTOU 防护）

    使用 O_NOFOLLOW 标志打开文件描述符，确保读取的是真实文件而非符号链接。
    这消除了检查路径和读取文件之间的竞态条件窗口。

    Args:
        file_path: 要读取的文件路径
        config_loader: 配置加载器（用于路径白名单验证）
        max_size: 最大允许读取的字节数（默认 10MB）

    Returns:
        文件内容的字节串

    Raises:
        PermissionError: 路径不在允许范围内
        FileNotFoundError: 文件不存在
        IsADirectoryError: 路径是目录
        ValueError: 文件过大
        OSError: 读取失败
    """
    if not is_path_allowed(file_path, config_loader):
        raise PermissionError("路径不在允许的访问范围内")

    path = Path(file_path)

    # 检查是否为符号链接（在打开描述符之前）
    if path.is_symlink():
        raise PermissionError("不允许读取符号链接")

    # 使用 O_NOFOLLOW 原子性地打开文件（如果操作系统支持）
    if _O_NOFOLLOW:
        fd = os.open(str(path), _O_RDONLY | _O_NOFOLLOW)
        try:
            # 验证打开的文件不是符号链接
            st = os.fstat(fd)
            if stat.S_ISLNK(st.st_mode):
                os.close(fd)
                raise PermissionError("检测到符号链接，拒绝读取")
            # 检查文件大小
            if st.st_size > max_size:
                os.close(fd)
                raise ValueError(f"文件过大: {st.st_size} 字节（限制 {max_size} 字节）")
            # 从文件描述符读取
            return os.read(fd, max_size)
        finally:
            os.close(fd)
    else:
        # Windows 不支持 O_NOFOLLOW，使用额外检查
        st = os.stat(str(path))
        if stat.S_ISLNK(st.st_mode):
            raise PermissionError("检测到符号链接，拒绝读取")
        if st.st_size > max_size:
            raise ValueError(f"文件过大: {st.st_size} 字节（限制 {max_size} 字节）")
        with open(str(path), "rb") as f:
            return f.read(max_size)
