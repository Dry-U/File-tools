"""
配置管理相关路由
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.api.dependencies import get_config_loader
from backend.api.models import (
    AIModelConfigValidator,
    RAGConfigValidator,
    SearchConfigValidator,
)
from backend.utils.app_paths import app_paths
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _preserve_existing_api_keys(config_loader: ConfigLoader, body: dict) -> None:
    """避免前端提交空密钥时覆盖已存储密钥。"""
    ai_model = body.get("ai_model")
    if not isinstance(ai_model, dict):
        return

    api_config = ai_model.get("api")
    if not isinstance(api_config, dict):
        return

    existing_single_key = config_loader.get("ai_model", "api.api_key", "")
    existing_provider_keys = {
        "siliconflow": config_loader.get("ai_model", "api.keys.siliconflow", ""),
        "deepseek": config_loader.get("ai_model", "api.keys.deepseek", ""),
        "custom": config_loader.get("ai_model", "api.keys.custom", ""),
    }

    incoming_single_key = api_config.get("api_key")
    if incoming_single_key in ("", None):
        api_config["api_key"] = existing_single_key

    incoming_keys = api_config.get("keys")
    if not isinstance(incoming_keys, dict):
        api_config["keys"] = existing_provider_keys
        return

    merged_keys = {}
    for provider, existing_value in existing_provider_keys.items():
        incoming_value = incoming_keys.get(provider)
        if incoming_value in ("", None, "***"):
            merged_keys[provider] = existing_value
        else:
            merged_keys[provider] = incoming_value
    api_config["keys"] = merged_keys


def mask_key(key: str) -> str:
    """掩码 API key，保留前4位和后4位，中间用 *** 代替"""
    if not key or len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


def _migrate_old_config(config_loader: ConfigLoader):
    """向后兼容：将旧配置迁移到新结构"""
    # 检查是否有旧配置
    old_interface_type = config_loader.get("ai_model", "interface_type", None)
    old_api_url = config_loader.get("ai_model", "api_url", None)
    old_api_key = config_loader.get("ai_model", "api_key", None)
    old_api_model = config_loader.get("ai_model", "api_model", None)

    if old_interface_type:
        # 迁移到新模式
        new_mode = "api" if old_interface_type == "api" else "local"
        config_loader.set("ai_model", "mode", new_mode)

        if old_api_url:
            if new_mode == "api":
                config_loader.set("ai_model", "api.api_url", old_api_url)
            else:
                config_loader.set("ai_model", "local.api_url", old_api_url)

        if old_api_key and new_mode == "api":
            config_loader.set("ai_model", "api.api_key", old_api_key)

        if old_api_model and new_mode == "api":
            config_loader.set("ai_model", "api.model_name", old_api_model)

        # 删除旧配置
        # 注意：这里假设ConfigLoader支持删除操作，如果不支持需要修改
        logger.info("配置已从旧版本迁移到新结构")


def _has_index_data(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_dir():
            return False
        for item in path.iterdir():
            if item.name.startswith("."):
                continue
            return True
    except Exception:
        return False
    return False


def _detect_index_path_migration_notice(config_loader: ConfigLoader) -> str:
    """检测旧索引目录存在数据但新目录为空的场景，返回一次性提示文案。"""
    try:
        expected_data_dir = (app_paths.user_data_dir / "data").resolve()
        expected_tantivy = (expected_data_dir / "tantivy_index").resolve()
        expected_hnsw = (expected_data_dir / "hnsw_index").resolve()
        expected_meta = (expected_data_dir / "metadata").resolve()

        current_tantivy = Path(
            str(config_loader.get("index", "tantivy_path", expected_tantivy))
        ).expanduser()
        current_hnsw = Path(
            str(config_loader.get("index", "hnsw_path", expected_hnsw))
        ).expanduser()
        current_meta = Path(
            str(config_loader.get("index", "metadata_path", expected_meta))
        ).expanduser()

        old_data_dir = (app_paths.app_dir / "data").resolve()
        old_tantivy = (old_data_dir / "tantivy_index").resolve()
        old_hnsw = (old_data_dir / "hnsw_index").resolve()
        old_meta = (old_data_dir / "metadata").resolve()

        if old_data_dir == expected_data_dir:
            return ""

        old_has_data = any(
            _has_index_data(p) for p in (old_tantivy, old_hnsw, old_meta)
        )
        current_has_data = any(
            _has_index_data(p) for p in (current_tantivy, current_hnsw, current_meta)
        )

        if old_has_data and not current_has_data:
            msg = (
                f"Detected old index directory {old_data_dir} has historical data, "
                f"but current index directory {expected_data_dir} is empty. "
                f"You may migrate the old index or rebuild via Directory Management."
            )
            return msg
    except Exception:
        return ""
    return ""


@router.post("/config")
async def update_config(
    request: Request, config_loader: ConfigLoader = Depends(get_config_loader)
):
    """更新配置并保存到文件"""
    try:
        body = await request.json()

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="配置数据必须是JSON对象")

        # 向后兼容：将旧字段映射到当前生效字段
        rag_payload = body.get("rag")
        if isinstance(rag_payload, dict):
            # max_history_turns from top_k
            if "max_history_turns" not in rag_payload and "top_k" in rag_payload:
                rag_payload["max_history_turns"] = rag_payload.get("top_k")
            # max_history_chars from context_length
            cond1 = "max_history_chars" not in rag_payload
            cond2 = "context_length" in rag_payload
            has_ctx = cond1 and cond2
            if has_ctx:
                rag_payload["max_history_chars"] = rag_payload.get("context_length")

        local_model_payload = body.get("local_model")
        ai_model_payload = body.get("ai_model")
        if isinstance(local_model_payload, dict):
            if not isinstance(ai_model_payload, dict):
                body["ai_model"] = {}
                ai_model_payload = body["ai_model"]
            if not isinstance(ai_model_payload.get("local"), dict):
                ai_model_payload["local"] = {}
            if "api_url" in local_model_payload:
                if "api_url" not in ai_model_payload["local"]:
                    ai_model_payload["local"]["api_url"] = local_model_payload.get(
                        "api_url"
                    )

        _preserve_existing_api_keys(config_loader, body)

        def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
            """将嵌套字典扁平化为点号分隔的键"""
            items: list[tuple[str, Any]] = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        # 验证配置数据
        validated_data: dict[str, Any] = {}
        if "ai_model" in body:
            try:
                validated_data["ai_model"] = AIModelConfigValidator(**body["ai_model"])
            except ValidationError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"ai_model配置验证失败: {str(e)}",
                )

        if "rag" in body:
            try:
                validated_data["rag"] = RAGConfigValidator(**body["rag"])
            except ValidationError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"rag配置验证失败: {str(e)}",
                )

        if "search" in body:
            try:
                validated_data["search"] = SearchConfigValidator(**body["search"])
            except ValidationError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"search配置验证失败: {str(e)}",
                )

        # 支持的配置节
        valid_sections = {
            "ai_model": {"flat": True},
            "rag": {"flat": True},
            "search": {"flat": True},
        }

        updated_sections = []
        for section, validator_model in validated_data.items():
            if section in valid_sections:
                values = validator_model.model_dump()
                flattened = flatten_dict(values)
                for key, value in flattened.items():
                    if key == "api.api_key" and "api.keys" in flattened:
                        continue
                    config_loader.set(section, key, value)
                updated_sections.append(section)

        # 处理旧格式的 ai_model 更新（向后兼容）
        if "ai_model" in body and "ai_model" not in validated_data:
            try:
                AIModelConfigValidator(**body["ai_model"])
            except ValidationError:
                pass  # 忽略无效数据

        if updated_sections:
            success = config_loader.save()
            if success:
                save_warnings = []
                if hasattr(config_loader, "pop_last_save_warnings"):
                    try:
                        save_warnings = config_loader.pop_last_save_warnings()
                    except Exception:
                        save_warnings = []
                if save_warnings is None:
                    save_warnings = []
                elif isinstance(save_warnings, str):
                    save_warnings = [save_warnings]
                elif isinstance(save_warnings, (list, tuple, set)):
                    try:
                        save_warnings = list(save_warnings)
                    except TypeError:
                        save_warnings = []
                else:
                    save_warnings = []
                save_warnings = [
                    str(item).strip() for item in save_warnings if str(item).strip()
                ]

                # 如果AI模型配置变更，异步触发RAGPipeline重新初始化
                if "ai_model" in updated_sections:
                    import threading

                    def reload_in_background():
                        try:
                            # 延迟导入避免循环导入
                            from backend.api.main import app

                            if (
                                hasattr(app.state, "rag_pipeline")
                                and app.state.rag_pipeline
                            ):
                                app.state.rag_pipeline.reload_model_manager()
                                logger.info("RAGPipeline ModelManager已重新加载")
                        except Exception as e:
                            logger.warning(f"重新加载ModelManager时出错: {e}")
                            # 出错时清除rag_pipeline，下次请求时会重新创建
                            try:
                                from backend.api.main import app

                                app.state.rag_pipeline = None
                            except ImportError:
                                pass

                    # 在后台线程中执行重新加载，不阻塞响应
                    reload_thread = threading.Thread(
                        target=reload_in_background, daemon=True
                    )
                    reload_thread.start()

                if save_warnings:
                    parts = ["配置已保存，但存在注意事项："]
                    parts.extend(save_warnings)
                    warning_msg = "；".join(parts)
                    return {
                        "status": "warning",
                        "message": warning_msg,
                        "updated_sections": updated_sections,
                    }
                else:
                    return {
                        "status": "success",
                        "message": "配置已保存",
                        "updated_sections": updated_sections,
                    }
            else:
                raise HTTPException(status_code=500, detail="保存配置文件失败")
        else:
            return {"status": "warning", "message": "没有有效的配置项需要更新"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新配置错误")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/config")
async def get_config(config_loader: ConfigLoader = Depends(get_config_loader)):
    """获取当前配置"""
    try:
        # 向后兼容：检查并迁移旧配置
        _migrate_old_config(config_loader)

        # 新配置结构 - 支持local/api模式
        mode = config_loader.get("ai_model", "mode", "local")
        provider = config_loader.get("ai_model", "api.provider", "siliconflow")

        # 获取多provider keys (已掩码)
        keys = {
            "siliconflow": mask_key(
                config_loader.get("ai_model", "api.keys.siliconflow", "")
            ),
            "deepseek": mask_key(
                config_loader.get("ai_model", "api.keys.deepseek", "")
            ),
            "custom": mask_key(config_loader.get("ai_model", "api.keys.custom", "")),
        }

        # 向后兼容：如果没有新结构，从旧配置加载
        if not any(keys.values()):
            old_key = config_loader.get("ai_model", "api.api_key", "")
            if old_key:
                keys[provider] = mask_key(old_key)

        config = {
            "ai_model": {
                "enabled": config_loader.getboolean("ai_model", "enabled", False),
                "mode": mode,
                "system_prompt": config_loader.get("ai_model", "system_prompt", ""),
                "local": {
                    "api_url": config_loader.get(
                        "ai_model",
                        "local.api_url",
                        "http://localhost:8000/v1/chat/completions",
                    ),
                    "max_context": config_loader.getint(
                        "ai_model", "local.max_context", 4096
                    ),
                    "max_tokens": config_loader.getint(
                        "ai_model", "local.max_tokens", 512
                    ),
                },
                "api": {
                    "provider": provider,
                    "api_url": config_loader.get(
                        "ai_model",
                        "api.api_url",
                        "https://api.siliconflow.cn/v1/chat/completions",
                    ),
                    "api_key": "",  # 不返回 key 以保护隐私
                    "model_name": config_loader.get(
                        "ai_model", "api.model_name", "deepseek-ai/DeepSeek-V2.5"
                    ),
                    "max_context": config_loader.getint(
                        "ai_model", "api.max_context", 8192
                    ),
                    "max_tokens": config_loader.getint(
                        "ai_model", "api.max_tokens", 2048
                    ),
                    "keys": {},  # 不返回 keys 以保护隐私
                },
                "security": {
                    "verify_ssl": config_loader.getboolean(
                        "ai_model", "security.verify_ssl", True
                    ),
                    "timeout": config_loader.getint(
                        "ai_model", "security.timeout", 120
                    ),
                    "retry_count": config_loader.getint(
                        "ai_model", "security.retry_count", 2
                    ),
                },
                # 采样参数
                "sampling": {
                    "temperature": config_loader.getfloat(
                        "ai_model", "sampling.temperature", 0.7
                    ),
                    "top_p": config_loader.getfloat("ai_model", "sampling.top_p", 0.9),
                    "top_k": config_loader.getint("ai_model", "sampling.top_k", 40),
                    "min_p": config_loader.getfloat("ai_model", "sampling.min_p", 0.05),
                    "max_tokens": config_loader.getint(
                        "ai_model", "sampling.max_tokens", 2048
                    ),
                    "seed": config_loader.getint("ai_model", "sampling.seed", -1),
                },
                # 惩罚参数
                "penalties": {
                    "repeat_penalty": config_loader.getfloat(
                        "ai_model", "penalties.repeat_penalty", 1.1
                    ),
                    "frequency_penalty": config_loader.getfloat(
                        "ai_model", "penalties.frequency_penalty", 0.0
                    ),
                    "presence_penalty": config_loader.getfloat(
                        "ai_model", "penalties.presence_penalty", 0.0
                    ),
                },
            },
            "rag": {
                "max_history_turns": config_loader.getint(
                    "rag",
                    "max_history_turns",
                    config_loader.getint("rag", "top_k", 3),
                ),
                "max_history_chars": config_loader.getint(
                    "rag",
                    "max_history_chars",
                    config_loader.getint("rag", "context_length", 1000),
                ),
            },
            "file_scanner": {
                "scan_paths": config_loader.get("file_scanner", "scan_paths", []),
            },
            "migration_notice": _detect_index_path_migration_notice(config_loader),
        }
        scan_paths = config["file_scanner"]["scan_paths"]  # type: ignore[index]
        if isinstance(scan_paths, str):
            config["file_scanner"]["scan_paths"] = [  # type: ignore[index]
                p.strip() for p in scan_paths.split(";") if p.strip()
            ]
        elif isinstance(scan_paths, list):
            config["file_scanner"]["scan_paths"] = [  # type: ignore[index]
                str(p).strip() for p in scan_paths if str(p).strip()
            ]
        else:
            config["file_scanner"]["scan_paths"] = []  # type: ignore[index]
        # 兼容旧前端字段读取；写入统一走 max_history_*。
        config["rag"]["top_k"] = config["rag"]["max_history_turns"]  # type: ignore[index]
        config["rag"]["context_length"] = config["rag"]["max_history_chars"]  # type: ignore[index]
        return config
    except Exception as e:
        logger.exception("获取配置错误")
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.get("/model/test")
async def test_model_connection(
    config_loader: ConfigLoader = Depends(get_config_loader),
):
    """测试模型API连接"""
    try:
        from backend.core.model_manager import ModelManager

        model_manager = ModelManager(config_loader)
        result = model_manager.test_connection()
        model_manager.close()

        return result
    except Exception as e:
        logger.exception("测试连接错误")
        return {"status": "error", "error": str(e)}
