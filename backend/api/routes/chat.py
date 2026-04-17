"""
聊天/对话相关路由
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.api.dependencies import (
    get_config_loader,
    get_rag_pipeline,
)
from backend.api.dependencies import (
    get_rate_limiter as rate_limiter_dependency,
)
from backend.api.models import ChatRequest, ChatResponse
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.utils.network import get_client_ip

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    rag_pipeline=Depends(get_rag_pipeline),
    config_loader: ConfigLoader = Depends(get_config_loader),
    limiter=Depends(rate_limiter_dependency),
):
    """与RAG系统进行对话

    Args:
        request: 对话请求，包含查询字符串和可选的会话ID

    Returns:
        对话响应，包含AI回答和相关文档来源

    Raises:
        HTTPException: 当对话失败或限流触发时
    """
    # 限流检查
    if config_loader.getboolean("security", "rate_limiter.enabled", True):
        # 获取客户端IP（使用安全方式）
        client_ip = get_client_ip(http_request, config_loader)
        max_req = config_loader.getint("security", "rate_limiter.chat_limit", 10)
        window = config_loader.getint("security", "rate_limiter.chat_window", 60)
        if not limiter.is_allowed(
            f"chat:{client_ip}", max_requests=max_req, window=window
        ):
            raise HTTPException(status_code=429, detail="对话过于频繁，请稍后再试")

    # 检查RAG管道是否就绪，如果正在初始化则等待
    if not rag_pipeline:
        if not config_loader.getboolean("ai_model", "enabled", False):
            return {
                "answer": (
                    "AI 问答功能未启用。请前往 设置 → 接入模式 中配置并启用 AI 模型。"
                ),
                "sources": [],
            }

        # 如果正在后台初始化，使用 asyncio.Event 等待
        _app = http_request.app
        if getattr(_app.state, "rag_initializing", False):
            import asyncio

            try:
                # 使用事件等待，最多10秒
                await asyncio.wait_for(
                    getattr(_app.state, "rag_ready_event", asyncio.Event()).wait(),
                    timeout=10.0,
                )
                if _app.state.rag_pipeline:
                    rag_pipeline = _app.state.rag_pipeline
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=("AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。"),
                    )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=503, detail="RAG管道初始化超时，请稍后再试"
                )
        else:
            raise HTTPException(
                status_code=500,
                detail="AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。",
            )

    try:
        query = request.query
        session_id = request.session_id

        if not query:
            raise HTTPException(status_code=400, detail="查询不能为空")

        if len(query) > 2000:
            raise HTTPException(status_code=400, detail="查询长度不能超过2000字符")

        result = rag_pipeline.query(query, session_id=session_id)
        return ChatResponse(**result)
    except HTTPException:
        raise  # 重新抛出 HTTPException，保持原始状态码
    except Exception as e:
        logger.error(f"对话错误: {str(e)}")
        raise HTTPException(status_code=500, detail="对话处理失败，请稍后重试") from e


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    rag_pipeline=Depends(get_rag_pipeline),
    config_loader: ConfigLoader = Depends(get_config_loader),
    limiter=Depends(rate_limiter_dependency),
):
    """以 SSE 形式流式返回 RAG 对话结果

    Args:
        request: 对话请求，包含查询字符串和可选的会话 ID

    Returns:
        StreamingResponse，按行发送 ``data: {json}\\n\\n`` 事件

    Raises:
        HTTPException: 当限流触发或 RAG 管道不可用时
    """
    # 限流检查（与非流式端点保持一致）
    if config_loader.getboolean("security", "rate_limiter.enabled", True):
        client_ip = get_client_ip(http_request, config_loader)
        max_req = config_loader.getint("security", "rate_limiter.chat_limit", 10)
        window = config_loader.getint("security", "rate_limiter.chat_window", 60)
        if not limiter.is_allowed(
            f"chat:{client_ip}", max_requests=max_req, window=window
        ):
            raise HTTPException(status_code=429, detail="对话过于频繁，请稍后再试")

    # 检查 RAG 管道是否就绪，如果正在初始化则等待
    if not rag_pipeline:
        if not config_loader.getboolean("ai_model", "enabled", False):

            async def _disabled_stream():
                payload = {
                    "type": "answer",
                    "content": (
                        "AI 问答功能未启用。"
                        "请前往 设置 → 接入模式 中配置并启用 AI 模型。"
                    ),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                empty_sources = {"type": "sources", "content": []}
                yield (f"data: {json.dumps(empty_sources, ensure_ascii=False)}\n\n")

            return StreamingResponse(_disabled_stream(), media_type="text/event-stream")

        _app = http_request.app
        if getattr(_app.state, "rag_initializing", False):
            import asyncio

            try:
                await asyncio.wait_for(
                    getattr(_app.state, "rag_ready_event", asyncio.Event()).wait(),
                    timeout=10.0,
                )
                if _app.state.rag_pipeline:
                    rag_pipeline = _app.state.rag_pipeline
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=("AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。"),
                    )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=503, detail="RAG管道初始化超时，请稍后再试"
                )
        else:
            raise HTTPException(
                status_code=500,
                detail="AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。",
            )

    query = request.query
    session_id = request.session_id

    if not query:
        raise HTTPException(status_code=400, detail="查询不能为空")

    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="查询长度不能超过2000字符")

    def event_generator():
        try:
            for event in rag_pipeline.query_stream(query, session_id=session_id):
                yield f"data: {event}\n\n"
        except Exception as exc:
            logger.error(f"流式对话错误: {exc}")
            err_payload = {
                "type": "error",
                "content": "对话处理失败，请稍后重试",
            }
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def get_sessions(rag_pipeline=Depends(get_rag_pipeline)):
    """获取所有聊天会话列表"""
    if not rag_pipeline:
        return {"sessions": []}

    try:
        sessions = rag_pipeline.get_all_sessions()
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"获取会话错误: {str(e)}")
        return {"sessions": []}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, rag_pipeline=Depends(get_rag_pipeline)):
    """删除特定会话"""
    if not rag_pipeline:
        raise HTTPException(
            status_code=500,
            detail="AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。",
        )

    try:
        success = rag_pipeline.clear_session(session_id)
        if success:
            return {"status": "success", "message": "会话已删除"}
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except HTTPException:
        raise  # 重新抛出 HTTPException，保持原始状态码
    except Exception as e:
        logger.error(f"删除会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail="删除会话失败，请稍后重试")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, rag_pipeline=Depends(get_rag_pipeline)):
    """获取特定会话的消息列表"""
    if not rag_pipeline:
        raise HTTPException(
            status_code=500,
            detail="AI 问答服务未就绪，请前往 设置 → 接入模式 检查配置。",
        )

    try:
        messages = rag_pipeline.chat_db.get_session_messages(session_id)
        return {"session_id": session_id, "messages": messages}
    except Exception as e:
        logger.error(f"获取会话消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话消息失败: {str(e)}")
