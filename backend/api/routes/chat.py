"""
聊天/对话相关路由
"""

from fastapi import APIRouter, HTTPException, Request, Depends

from backend.api.models import ChatRequest, ChatResponse
from backend.utils.config_loader import ConfigLoader
from backend.utils.logger import get_logger
from backend.utils.network import get_client_ip
from backend.api.dependencies import (
    get_rag_pipeline,
    get_config_loader,
    get_rate_limiter,
)

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    rag_pipeline=Depends(get_rag_pipeline),
    config_loader: ConfigLoader = Depends(get_config_loader),
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
    limiter = get_rate_limiter()
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
                "answer": "AI问答功能未启用。请在配置文件中设置 ai_model.enabled = true。",
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
                    raise HTTPException(status_code=503, detail="RAG管道初始化失败")
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=503, detail="RAG管道初始化超时，请稍后再试"
                )
        else:
            raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        query = request.query
        session_id = request.session_id

        if not query:
            raise HTTPException(status_code=400, detail="查询不能为空")

        result = rag_pipeline.query(query, session_id=session_id)
        return ChatResponse(**result)
    except HTTPException:
        raise  # 重新抛出 HTTPException，保持原始状态码
    except Exception as e:
        logger.error(f"对话错误: {str(e)}")
        raise HTTPException(status_code=500, detail="对话处理失败，请稍后重试") from e


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
        raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        success = rag_pipeline.clear_session(session_id)
        if success:
            return {"status": "success", "message": "会话已删除"}
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        logger.error(f"删除会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, rag_pipeline=Depends(get_rag_pipeline)):
    """获取特定会话的消息列表"""
    if not rag_pipeline:
        raise HTTPException(status_code=500, detail="RAG管道未初始化")

    try:
        messages = rag_pipeline.chat_db.get_session_messages(session_id)
        return {"session_id": session_id, "messages": messages}
    except Exception as e:
        logger.error(f"获取会话消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话消息失败: {str(e)}")
