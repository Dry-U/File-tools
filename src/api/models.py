# src/api/models.py
from pydantic import BaseModel
from typing import List, Optional

class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str
    file_filter: Optional[List[str]] = None  # 可选文件过滤

class QueryResponse(BaseModel):
    """查询响应模型"""
    answer: str
    sources: List[str]