#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import logging
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from io import BytesIO
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rag import settings
from rag.utils import singleton


@singleton
class RAGFlowThirdPartyStorageAdapter:
    """
    增强版第三方文件管理接口适配器

    支持多种认证方式、重试机制、缓存和监控功能
    """

    def __init__(self):
        self.session = None
        self.config = None
        self.cache = {}
        self.metrics = {"requests_count": 0, "success_count": 0, "error_count": 0, "total_bytes_uploaded": 0, "total_bytes_downloaded": 0}
        self.__init_config()
        self.__open__()

    def __init_config(self):
        """初始化配置"""
        self.config = settings.THIRD_PARTY_STORAGE

        # 设置默认值
        self.config.setdefault("timeout", 30)
        self.config.setdefault("request", {})
        self.config["request"].setdefault("max_retries", 3)
        self.config["request"].setdefault("retry_delay", 1)
        self.config["request"].setdefault("chunk_size", 8192)

        # 默认端点配置
        default_endpoints = {
            "upload": "/api/v1/files/upload",
            "download": "/api/v1/files/download",
            "delete": "/api/v1/files/delete",
            "exists": "/api/v1/files/exists",
            "info": "/api/v1/files/info",
            "presigned_url": "/api/v1/files/presigned-url",
            "list_objects": "/api/v1/objects/list",
            "bucket_delete": "/api/v1/buckets/delete",
        }
        self.config.setdefault("endpoints", default_endpoints)

        # 默认响应映射
        default_response_mapping = {
            "success_codes": [200, 201, 204],
            "file_url_field": "file_url",
            "presigned_url_field": "presigned_url",
            "objects_field": "objects",
            "error_message_field": "message",
        }
        self.config.setdefault("response_mapping", default_response_mapping)

    def __open__(self):
        """初始化连接"""
        try:
            if self.session:
                self.__close__()

            # 创建会话
            self.session = requests.Session()

            # 配置重试策略
            retry_strategy = Retry(
                total=self.config["request"]["max_retries"], backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            # 设置认证
            self.__setup_authentication()

            # 设置默认头部
            self.__setup_headers()

            logging.info(f"Successfully connected to third-party storage: {self.config.get('base_url')}")

        except Exception as e:
            logging.exception(f"Failed to connect to third-party storage: {e}")
            raise

    def __close__(self):
        """关闭连接"""
        if self.session:
            self.session.close()
        self.session = None

    def __setup_authentication(self):
        """设置认证"""
        auth_config = self.config.get("auth", {})
        auth_type = auth_config.get("type", "bearer")

        if auth_type == "bearer":
            token = auth_config.get("token") or self.config.get("api_key")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})

        elif auth_type == "basic":
            username = auth_config.get("username")
            password = auth_config.get("password")
            if username and password:
                self.session.auth = (username, password)

        elif auth_type == "api_key":
            api_key = auth_config.get("api_key") or self.config.get("api_key")
            header_name = auth_config.get("api_key_header", "X-API-Key")
            if api_key:
                self.session.headers.update({header_name: api_key})

    def __setup_headers(self):
        """设置请求头"""
        # 设置内容类型
        self.session.headers.update({"User-Agent": "RAGFlow/1.0", "Accept": "application/json"})

        # 添加自定义头部
        custom_headers = self.config.get("custom_headers", {})
        self.session.headers.update(custom_headers)

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """发起HTTP请求"""
        base_url = self.config.get("base_url", "").rstrip("/")
        url = f"{base_url}/{endpoint.lstrip('/')}"

        # 更新指标
        self.metrics["requests_count"] += 1

        try:
            # 设置超时
            kwargs.setdefault("timeout", self.config.get("timeout", 30))

            # 记录请求日志
            if self.config.get("logging", {}).get("log_requests", True):
                logging.debug(f"Making request: {method} {url}")

            response = self.session.request(method=method, url=url, **kwargs)
            response.raise_for_status()

            # 更新成功指标
            self.metrics["success_count"] += 1

            return response

        except requests.exceptions.RequestException as e:
            # 更新错误指标
            self.metrics["error_count"] += 1
            logging.error(f"Request failed: {method} {url} - {e}")
            raise

    def _get_cache_key(self, bucket: str, filename: str, operation: str) -> str:
        """生成缓存键"""
        key_string = f"{bucket}:{filename}:{operation}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if not self.config.get("advanced", {}).get("enable_cache", True):
            return None

        cache_item = self.cache.get(key)
        if cache_item:
            expires_at = cache_item.get("expires_at")
            if expires_at and datetime.now() > expires_at:
                # 缓存过期
                del self.cache[key]
                return None
            return cache_item.get("data")
        return None

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        if not self.config.get("advanced", {}).get("enable_cache", True):
            return

        ttl = self.config.get("advanced", {}).get("cache_ttl", 3600)
        expires_at = datetime.now() + timedelta(seconds=ttl)

        self.cache[key] = {"data": data, "expires_at": expires_at}

    def health(self) -> bool:
        """健康检查"""
        try:
            # 检查基本连接
            response = self._make_request("GET", "/health", allow_redirects=True)
            return response.status_code in self.config["response_mapping"]["success_codes"]

        except Exception as e:
            logging.error(f"Health check failed: {e}")
            return False

    def put(self, bucket: str, filename: str, binary: bytes) -> Any:
        """上传文件"""
        endpoint = self.config["endpoints"]["upload"]

        for attempt in range(self.config["request"]["max_retries"]):
            try:
                # 准备文件数据
                files = {"file": (filename, BytesIO(binary), "application/octet-stream")}

                params = {"bucket": bucket, "filename": filename}

                # 移除Content-Type头部，让requests自动设置
                headers = dict(self.session.headers)
                headers.pop("Content-Type", None)

                response = self._make_request(method="POST", endpoint=endpoint, files=files, params=params, headers=headers)

                # 更新指标
                self.metrics["total_bytes_uploaded"] += len(binary)

                logging.info(f"Successfully uploaded {bucket}/{filename} ({len(binary)} bytes)")
                return response.json() if response.text else {"status": "success"}

            except Exception as e:
                logging.error(f"Upload attempt {attempt + 1} failed for {bucket}/{filename}: {e}")
                if attempt == self.config["request"]["max_retries"] - 1:
                    raise
                time.sleep(self.config["request"]["retry_delay"])

    def get(self, bucket: str, filename: str) -> Optional[bytes]:
        """下载文件"""
        # 检查缓存
        cache_key = self._get_cache_key(bucket, filename, "get")
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data

        endpoint = self.config["endpoints"]["download"]

        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="GET", endpoint=endpoint, params=params)

            data = response.content

            # 更新指标
            self.metrics["total_bytes_downloaded"] += len(data)

            # 缓存数据
            self._set_cache(cache_key, data)

            logging.info(f"Successfully downloaded {bucket}/{filename} ({len(data)} bytes)")
            return data

        except Exception as e:
            logging.error(f"Download failed for {bucket}/{filename}: {e}")
            return None

    def rm(self, bucket: str, filename: str) -> bool:
        """删除文件"""
        endpoint = self.config["endpoints"]["delete"]

        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="DELETE", endpoint=endpoint, params=params)  # noqa: F841

            # 清除缓存
            cache_key = self._get_cache_key(bucket, filename, "get")
            self.cache.pop(cache_key, None)

            logging.info(f"Successfully deleted {bucket}/{filename}")
            return True

        except Exception as e:
            logging.error(f"Delete failed for {bucket}/{filename}: {e}")
            return False

    def obj_exist(self, bucket: str, filename: str) -> bool:
        """检查文件是否存在"""
        # 检查缓存
        cache_key = self._get_cache_key(bucket, filename, "exists")
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result

        endpoint = self.config["endpoints"]["exists"]

        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="HEAD", endpoint=endpoint, params=params)

            exists = response.status_code in self.config["response_mapping"]["success_codes"]

            # 缓存结果
            self._set_cache(cache_key, exists)

            return exists

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self._set_cache(cache_key, False)
                return False
            else:
                logging.error(f"Error checking existence of {bucket}/{filename}: {e}")
                return False
        except Exception as e:
            logging.error(f"Error checking existence of {bucket}/{filename}: {e}")
            return False

    def get_presigned_url(self, bucket: str, filename: str, expires: int) -> Optional[str]:
        """获取预签名URL"""
        endpoint = self.config["endpoints"]["presigned_url"]

        for attempt in range(self.config["request"]["max_retries"]):
            try:
                data = {"bucket": bucket, "filename": filename, "expires": expires}

                response = self._make_request(method="POST", endpoint=endpoint, json=data)

                result = response.json()
                url_field = self.config["response_mapping"]["presigned_url_field"]
                return result.get(url_field)

            except Exception as e:
                logging.error(f"Presigned URL attempt {attempt + 1} failed for {bucket}/{filename}: {e}")
                if attempt == self.config["request"]["max_retries"] - 1:
                    break
                time.sleep(self.config["request"]["retry_delay"])

        return None

    def remove_bucket(self, bucket: str) -> bool:
        """删除存储桶"""
        endpoint = self.config["endpoints"]["bucket_delete"]

        try:
            params = {"bucket": bucket}

            response = self._make_request(method="DELETE", endpoint=endpoint, params=params)  # noqa: F841

            # 清除相关缓存
            keys_to_remove = [key for key in self.cache.keys() if key.startswith(f"{bucket}:")]
            for key in keys_to_remove:
                del self.cache[key]

            logging.info(f"Successfully removed bucket {bucket}")
            return True

        except Exception as e:
            logging.error(f"Remove bucket failed for {bucket}: {e}")
            return False

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True) -> List[Dict]:
        """列出对象"""
        endpoint = self.config["endpoints"]["list_objects"]

        try:
            params = {"bucket": bucket, "prefix": prefix, "recursive": recursive}

            response = self._make_request(method="GET", endpoint=endpoint, params=params)

            result = response.json()
            objects_field = self.config["response_mapping"]["objects_field"]
            return result.get(objects_field, [])

        except Exception as e:
            logging.error(f"List objects failed for bucket {bucket}: {e}")
            return []

    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return self.metrics.copy()

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logging.info("Cache cleared")

    def get_object_info(self, bucket: str, filename: str) -> Dict[str, Any]:
        """获取对象信息"""
        endpoint = self.config["endpoints"]["info"]

        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="GET", endpoint=endpoint, params=params)

            return response.json()

        except Exception as e:
            logging.error(f"Get object info failed for {bucket}/{filename}: {e}")
            return {}
