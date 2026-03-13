"""
网络工具函数 - 安全地获取和验证客户端 IP
"""
import re
from fastapi import Request


def get_client_ip(request: Request, config_loader) -> str:
    """
    安全地获取客户端 IP 地址

    安全考虑：
    1. 只在配置明确信任代理时才使用 X-Forwarded-For 头
    2. 验证 IP 地址格式
    3. 防止 IP 头伪造攻击
    """
    # 检查是否信任代理
    trust_proxy = config_loader.getboolean('security', 'trust_proxy', False)

    if trust_proxy:
        # 优先使用 X-Real-IP（如果配置允许）
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            if is_valid_ip(real_ip):
                return real_ip

        # 使用 X-Forwarded-For（取第一个有效IP，这是原始客户端IP）
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            # 取第一个 IP（最接近客户端的）
            ips = [ip.strip() for ip in forwarded_for.split(',')]
            for ip in ips:
                if is_valid_ip(ip):
                    return ip

    # 默认使用直接连接的客户端 IP
    if request.client:
        return request.client.host

    return "unknown"


def is_valid_ip(ip: str) -> bool:
    """验证 IP 地址格式是否有效"""
    if not ip or not isinstance(ip, str):
        return False

    # 基本格式检查
    if len(ip) > 45:  # IPv6 最大长度
        return False

    # 检查非法字符
    if any(c in ip for c in [';', '|', '&', '$', '`', ' ', '\t', '\n', '\r']):
        return False

    # IPv4 验证
    ipv4_pattern = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    if ipv4_pattern.match(ip):
        return True

    # IPv6 验证（简化版）
    ipv6_pattern = re.compile(r'^([0-9a-fA-F:]+)$')
    if ipv6_pattern.match(ip) and ':' in ip:
        return True

    return False
