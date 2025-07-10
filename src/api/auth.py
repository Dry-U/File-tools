# src/api/auth.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader

logger = setup_logger()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # 假设有登录端点

SECRET_KEY = "your-secret-key"  # 生产中从环境变量或config加载
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效凭证")
        return {"username": username, "role": payload.get("role", "user")}
    except JWTError as e:
        logger.error(f"JWT验证失败: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效凭证")