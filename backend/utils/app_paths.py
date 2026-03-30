r"""
应用路径管理模块

负责管理应用的各种路径：
- 用户数据目录（配置、日志、索引等）
- 应用资源目录（打包后的静态文件）
- 确保目录存在并可写
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AppPaths:
    """应用路径管理器"""

    APP_NAME = "FileTools"
    APP_AUTHOR = "DryU"  # Windows 上用于组织文件夹

    def __init__(self):
        self._user_data_dir: Optional[Path] = None
        self._config_dir: Optional[Path] = None
        self._log_dir: Optional[Path] = None
        self._data_dir: Optional[Path] = None
        self._cache_dir: Optional[Path] = None

    @property
    def is_frozen(self) -> bool:
        """检查应用是否已打包（PyInstaller）"""
        return getattr(sys, "frozen", False)

    @property
    def app_dir(self) -> Path:
        """获取应用所在目录"""
        if self.is_frozen:
            # PyInstaller 打包后的路径
            return Path(sys.executable).parent
        else:
            # 开发环境
            return Path(__file__).parent.parent.parent

    @property
    def user_data_dir(self) -> Path:
        r"""
        获取用户数据目录

        平台路径：
        - Windows: %APPDATA%\FileTools (C:\Users\<user>\AppData\Roaming\FileTools)
        - macOS: ~/Library/Application Support/FileTools
        - Linux: ~/.config/FileTools
        """
        if self._user_data_dir is None:
            self._user_data_dir = self._get_user_data_dir()
            self._ensure_dir(self._user_data_dir)
        return self._user_data_dir

    def _get_user_data_dir(self) -> Path:
        """根据平台获取用户数据目录"""
        if sys.platform == "win32":
            # Windows: %APPDATA%
            base = os.environ.get("APPDATA")
            if base:
                return Path(base) / self.APP_NAME
            else:
                return Path.home() / "AppData" / "Roaming" / self.APP_NAME

        elif sys.platform == "darwin":
            # macOS
            return Path.home() / "Library" / "Application Support" / self.APP_NAME

        else:
            # Linux 和其他 Unix
            base = os.environ.get("XDG_DATA_HOME")
            if base:
                return Path(base) / self.APP_NAME.lower()
            else:
                return Path.home() / ".config" / self.APP_NAME.lower()

    @property
    def config_path(self) -> Path:
        """获取配置文件路径"""
        if self._config_dir is None:
            self._config_dir = self.user_data_dir / "config.yaml"
        return self._config_dir

    @property
    def log_dir(self) -> Path:
        """获取日志目录"""
        if self._log_dir is None:
            self._log_dir = self.user_data_dir / "logs"
            self._ensure_dir(self._log_dir)
        return self._log_dir

    @property
    def data_dir(self) -> Path:
        """获取数据目录（索引、元数据等）"""
        if self._data_dir is None:
            self._data_dir = self.user_data_dir / "data"
            self._ensure_dir(self._data_dir)
            # 创建子目录
            self._ensure_dir(self._data_dir / "tantivy_index")
            self._ensure_dir(self._data_dir / "hnsw_index")
            self._ensure_dir(self._data_dir / "metadata")
            self._ensure_dir(self._data_dir / "cache")
            self._ensure_dir(self._data_dir / "temp")
        return self._data_dir

    @property
    def cache_dir(self) -> Path:
        """获取缓存目录"""
        if self._cache_dir is None:
            # 优先使用系统缓存目录
            if sys.platform == "win32":
                base = os.environ.get("LOCALAPPDATA")
                if base:
                    self._cache_dir = Path(base) / self.APP_NAME / "Cache"
                else:
                    self._cache_dir = self.user_data_dir / "cache"
            elif sys.platform == "darwin":
                self._cache_dir = Path.home() / "Library" / "Caches" / self.APP_NAME
            else:
                base = os.environ.get("XDG_CACHE_HOME")
                if base:
                    self._cache_dir = Path(base) / self.APP_NAME.lower()
                else:
                    self._cache_dir = Path.home() / ".cache" / self.APP_NAME.lower()

            self._ensure_dir(self._cache_dir)
        return self._cache_dir

    @property
    def frontend_dir(self) -> Optional[Path]:
        """
        获取前端资源目录

        开发环境: 项目根目录/frontend
        打包后: 应用目录/_internal/frontend 或 MEIPASS 临时目录
        """
        if self.is_frozen:
            # PyInstaller 打包后的路径
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                # 单文件模式：临时解压目录
                frontend = Path(meipass) / "frontend"
                if frontend.exists():
                    return frontend

            # 单目录模式：应用目录下的 _internal
            internal = self.app_dir / "_internal"
            if internal.exists():
                frontend = internal / "frontend"
                if frontend.exists():
                    return frontend

            # 直接在应用目录下
            frontend = self.app_dir / "frontend"
            if frontend.exists():
                return frontend
        else:
            # 开发环境
            frontend = self.app_dir / "frontend"
            if frontend.exists():
                return frontend

        return None

    def _ensure_dir(self, path: Path) -> None:
        """确保目录存在"""
        path.mkdir(parents=True, exist_ok=True)

    def init_user_data(self, default_config_path: Optional[Path] = None) -> None:
        """
        初始化用户数据目录

        如果配置文件不存在，从模板复制默认配置
        """
        # 确保所有目录存在
        _ = self.user_data_dir
        _ = self.log_dir
        _ = self.data_dir
        _ = self.cache_dir

        # 如果配置文件不存在，创建默认配置
        if not self.config_path.exists():
            self._create_default_config(default_config_path)

        logger.info(f"[AppPaths] 用户数据目录: {self.user_data_dir}")
        logger.info(f"[AppPaths] 配置文件: {self.config_path}")
        logger.info(f"[AppPaths] 日志目录: {self.log_dir}")
        logger.info(f"[AppPaths] 数据目录: {self.data_dir}")

    def _create_default_config(self, template_path: Optional[Path] = None) -> None:
        """创建默认配置文件"""
        # 尝试从模板复制
        if template_path and template_path.exists():
            shutil.copy2(template_path, self.config_path)
            return

        # 尝试从应用目录的模板复制
        if self.is_frozen:
            # 单目录模式：_internal/templates/config.yaml
            internal = self.app_dir / "_internal"
            if internal.exists():
                template = internal / "templates" / "config.yaml"
            else:
                template = self.app_dir / "templates" / "config.yaml"
            if template.exists():
                shutil.copy2(template, self.config_path)
                return

        # 尝试从项目根目录复制
        dev_config = self.app_dir / "config.yaml"
        if dev_config.exists():
            shutil.copy2(dev_config, self.config_path)
            return

        # 创建最小默认配置
        default_config = """# FileTools 默认配置
system:
  app_name: 智能文件检索与问答系统
  version: 1.0.0
  log_level: INFO
  log_dir: logs
  data_dir: data
  cache_dir: cache
  temp_dir: temp

file_scanner:
  scan_paths: []
  max_file_size: 100
  scan_threads: 4
  recursive: true

index:
  tantivy_path: ./data/tantivy_index
  hnsw_path: ./data/hnsw_index
  metadata_path: ./data/metadata

search:
  text_weight: 0.6
  vector_weight: 0.4
  max_results: 50

monitor:
  enabled: true
  debounce_time: 0.5

ai_model:
  enabled: false
  mode: api
  api:
    provider: siliconflow
    model_name: deepseek-ai/DeepSeek-V2.5
  sampling:
    temperature: 0.7
    max_tokens: 2048
"""
        self.config_path.write_text(default_config, encoding="utf-8")

    def get_relative_path(self, path: Path) -> str:
        """获取相对于用户数据目录的路径（用于配置中存储）"""
        try:
            return str(path.relative_to(self.user_data_dir))
        except ValueError:
            return str(path)


# 全局实例
app_paths = AppPaths()


def get_app_paths() -> AppPaths:
    """获取应用路径管理器实例"""
    return app_paths


if __name__ == "__main__":
    # 测试
    paths = AppPaths()
    logger.info(f"应用目录: {paths.app_dir}")
    logger.info(f"用户数据目录: {paths.user_data_dir}")
    logger.info(f"配置文件: {paths.config_path}")
    logger.info(f"日志目录: {paths.log_dir}")
    logger.info(f"数据目录: {paths.data_dir}")
    logger.info(f"缓存目录: {paths.cache_dir}")
    logger.info(f"前端目录: {paths.frontend_dir}")
    logger.info(f"是否打包: {paths.is_frozen}")
