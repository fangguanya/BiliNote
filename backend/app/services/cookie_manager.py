import json
from pathlib import Path
from typing import Optional, Dict
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CookieConfigManager:
    def __init__(self, filepath: str = "config/downloader.json"):
        self.path = Path(filepath)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> Dict[str, Dict[str, str]]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Dict[str, str]]):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, platform: str) -> Optional[str]:
        data = self._read()
        cookie = data.get(platform, {}).get("cookie")
        if cookie:
            logger.debug(f"🍪 获取{platform}的cookie: 长度={len(cookie)}, 预览={cookie[:50]}...")
        else:
            logger.debug(f"🔍 {platform}没有保存的cookie")
        return cookie

    def set(self, platform: str, cookie: str):
        logger.info(f"💾 保存{platform}的cookie: 长度={len(cookie)}")
        logger.debug(f"🔍 Cookie内容: {cookie}")
        
        data = self._read()
        data[platform] = {"cookie": cookie}
        self._write(data)
        
        # 验证保存是否成功
        saved_cookie = self.get(platform)
        if saved_cookie and saved_cookie == cookie:
            logger.info(f"✅ {platform} cookie保存验证成功")
        else:
            logger.error(f"❌ {platform} cookie保存验证失败")

    def delete(self, platform: str):
        logger.info(f"🗑️ 删除{platform}的cookie")
        data = self._read()
        if platform in data:
            del data[platform]
            self._write(data)
            logger.info(f"✅ {platform} cookie删除成功")
        else:
            logger.warning(f"⚠️ {platform} 没有cookie需要删除")

    def list_all(self) -> Dict[str, str]:
        data = self._read()
        return {k: v.get("cookie", "") for k, v in data.items()}

    def exists(self, platform: str) -> bool:
        return self.get(platform) is not None