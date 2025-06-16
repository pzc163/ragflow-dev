import os
import json
import logging
import requests
from typing import Optional, Dict, Any

class ImagePlatformStorageAdapter:
    """
    影像管理平台文件存储适配器
    """

    def __init__(self, base_url: str, app_id: str, app_key: str):
        if not base_url.startswith('http'):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头")
        self.base_url = base_url.rstrip('/')
        self.app_id = app_id
        self.app_key = app_key

    def upload_file(self, file_path: str, tp_cd: Optional[str] = None, tp_path: Optional[str] = None, comments: str = "") -> Optional[Dict[str, Any]]:
        """
        上传单个文件到影像平台
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件未找到: {file_path}")

        api_url = f"{self.base_url}/nvp/upload2"
        file_name = os.path.basename(file_path)
        file_format = file_name.split('.')[-1] if '.' in file_name else ''

        attachment_data = {
            "type": "file",
            "oriNm": file_name,
            "format": file_format,
            "comments": comments,
            "entries": [
                {"name": "fileName", "value": file_name},
                {"name": "catalog", "value": self.app_id}
            ]
        }

        files = {
            'file': (file_name, open(file_path, 'rb')),
            'attachment': (None, json.dumps(attachment_data)),
            'key': (None, self.app_key),
            'tpCd': (None, str(tp_cd) if tp_cd else ''),
            'tpPath': (None, tp_path if tp_path else '')
        }

        try:
            response = requests.post(api_url, files=files, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"文件上传失败: {e}")
            return None

    def download_file(self, file_id: str, save_path: str) -> bool:
        """
        根据文件ID下载文件
        """
        api_url = f"{self.base_url}/thumbnailImage/{file_id}"
        params = {
            'app': self.app_id,
            'key': self.app_key
        }
        try:
            with requests.get(api_url, params=params, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"文件下载失败: {e}")
            return False

    def delete_file(self, file_id: str) -> bool:
        """
        影像平台没有标准的删除接口，如有请补充实现
        """
        logging.warning("影像平台API文档未提供删除接口，如有请补充实现。")
        return False 