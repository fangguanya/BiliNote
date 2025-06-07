"""
认证相关异常
"""


class AuthRequiredException(Exception):
    """需要认证异常"""
    
    def __init__(self, platform: str, message: str = None):
        self.platform = platform
        self.message = message or f"{platform}平台需要登录认证"
        super().__init__(self.message)


class AuthFailedException(Exception):
    """认证失败异常"""
    
    def __init__(self, platform: str, message: str = None):
        self.platform = platform
        self.message = message or f"{platform}平台认证失败"
        super().__init__(self.message) 