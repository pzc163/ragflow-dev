from typing import Optional, Any
from .image_platform_storage_adapter import ImagePlatformStorageAdapter
from api import settings


class ImagePlatformStorageClient:
    """
    影像管理平台文件存储连接器（业务入口）
    """

    def __init__(self, config: dict = None):
        # 优先使用传入的config，否则自动读取settings.IMAGE_PLATFORM_STORAGE
        if config is None:
            config = settings.IMAGE_PLATFORM_STORAGE
        if not config:
            raise ValueError("缺少影像平台存储配置")
        self.base_url = config.get("base_url")
        self.app_id = config.get("app_id")
        self.app_key = config.get("app_key")
        if not self.base_url or not self.app_id or not self.app_key:
            raise ValueError("配置缺少 base_url、app_id 或 app_key")

    def put(self, file_path: str, tp_cd: Optional[str] = None, tp_path: Optional[str] = None, comments: str = "") -> Optional[Any]:
        adapter = ImagePlatformStorageAdapter(self.base_url, self.app_id, self.app_key)
        return adapter.upload_file(file_path, tp_cd, tp_path, comments)

    def get(self, file_id: str, save_path: str) -> bool:
        adapter = ImagePlatformStorageAdapter(self.base_url, self.app_id, self.app_key)
        return adapter.download_file(file_id, save_path)
