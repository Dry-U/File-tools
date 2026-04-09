"""
配置管理相关路由
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.api.dependencies import get_config_loader
from backend.api.models import (
    AIModelConfigValidator,
    RAGConfigValidator,
    SearchConfigValidator,
)
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


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


@router.post("/config")
async def update_config(
    request: Request, config_loader: ConfigLoader = Depends(get_config_loader)
):
    """更新配置并保存到文件"""
    try:
        body = await request.json()

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="配置数据必须是JSON对象")

        def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
            """将嵌套字典扁平化为点号分隔的键"""
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        # 验证配置数据
        validated_data = {}
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
            "local_model": {"flat": True},
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
        logger.error(f"更新配置错误: {str(e)}")
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

        # 获取多provider keys
        keys = {
            "siliconflow": config_loader.get("ai_model", "api.keys.siliconflow", ""),
            "deepseek": config_loader.get("ai_model", "api.keys.deepseek", ""),
            "custom": config_loader.get("ai_model", "api.keys.custom", ""),
        }

        # 向后兼容：如果没有新结构，从旧配置加载
        if not any(keys.values()):
            old_key = config_loader.get("ai_model", "api.api_key", "")
            if old_key:
                keys[provider] = old_key

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
                    "api_key": keys.get(provider, ""),  # 当前provider的key
                    "model_name": config_loader.get(
                        "ai_model", "api.model_name", "deepseek-ai/DeepSeek-V2.5"
                    ),
                    "max_context": config_loader.getint(
                        "ai_model", "api.max_context", 8192
                    ),
                    "max_tokens": config_loader.getint(
                        "ai_model", "api.max_tokens", 2048
                    ),
                    "keys": keys,  # 所有provider的keys
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
                    "rag", "max_history_turns", 3
                ),
                "max_history_chars": config_loader.getint(
                    "rag", "max_history_chars", 1000
                ),
            },
        }
        return config
    except Exception as e:
        logger.error(f"获取配置错误: {str(e)}")
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
        logger.error(f"测试连接错误: {str(e)}")
        return {"status": "error", "error": str(e)}
