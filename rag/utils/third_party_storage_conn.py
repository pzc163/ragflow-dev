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
import requests
from io import BytesIO
from typing import Optional, Any
from rag import settings
from rag.utils import singleton


@singleton
class RAGFlowThirdPartyStorage:
    """
    第三方文件管理接口连接器

    该类实现了与RAGFlow存储接口兼容的所有方法，
    可以接入任何支持RESTful API的第三方文件存储服务。
    """

    def __init__(self):
        self.session = None
        self.base_url = None
        self.api_key = None
        self.timeout = 30
        self.__open__()

    def __open__(self):
        """初始化第三方存储连接"""
        try:
            if self.session:
                self.__close__()
        except Exception:
            pass

        try:
            # 从配置中获取第三方存储设置
            self.base_url = settings.THIRD_PARTY_STORAGE.get("base_url")
            self.api_key = settings.THIRD_PARTY_STORAGE.get("api_key")
            self.timeout = settings.THIRD_PARTY_STORAGE.get("timeout", 30)

            # 初始化HTTP会话
            self.session = requests.Session()

            # 设置认证头
            if self.api_key:
                self.session.headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

            logging.info(f"Successfully connected to third-party storage: {self.base_url}")

        except Exception as e:
            logging.exception(f"Failed to connect to third-party storage: {e}")
            raise

    def __close__(self):
        """关闭连接"""
        if self.session:
            self.session.close()
        self.session = None

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        发起HTTP请求的统一方法

        Args:
            method: HTTP方法 (GET, POST, PUT, DELETE)
            endpoint: API端点
            **kwargs: 额外的请求参数

        Returns:
            requests.Response: HTTP响应对象
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(method=method, url=url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {method} {url} - {e}")
            raise

    def health(self) -> bool:
        """
        健康检查

        Returns:
            bool: 服务是否正常
        """
        try:
            # 尝试上传和删除一个测试文件
            test_bucket = "health_check"
            test_filename = "health_test.txt"
            test_data = b"health_check_data"

            # 上传测试文件
            self.put(test_bucket, test_filename, test_data)

            # 检查文件是否存在
            exists = self.obj_exist(test_bucket, test_filename)

            # 清理测试文件
            if exists:
                self.rm(test_bucket, test_filename)

            return exists

        except Exception as e:
            logging.error(f"Health check failed: {e}")
            return False

    def put(self, bucket: str, filename: str, binary: bytes) -> Any:
        """
        上传文件

        Args:
            bucket: 存储桶名称
            filename: 文件名
            binary: 文件二进制数据

        Returns:
            Any: 上传响应结果
        """
        for attempt in range(3):
            try:
                # 构建上传请求
                files = {"file": (filename, BytesIO(binary), "application/octet-stream")}

                params = {"bucket": bucket, "filename": filename}

                response = self._make_request(method="POST", endpoint="/api/v1/files/upload", files=files, params=params)

                logging.info(f"Successfully uploaded {bucket}/{filename}")
                return response.json()

            except Exception as e:
                logging.error(f"Upload attempt {attempt + 1} failed for {bucket}/{filename}: {e}")
                if attempt == 2:  # 最后一次尝试
                    raise
                time.sleep(1)

    def get(self, bucket: str, filename: str) -> Optional[bytes]:
        """
        下载文件

        Args:
            bucket: 存储桶名称
            filename: 文件名

        Returns:
            Optional[bytes]: 文件二进制数据，失败返回None
        """
        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="GET", endpoint="/api/v1/files/download", params=params)

            return response.content

        except Exception as e:
            logging.error(f"Download failed for {bucket}/{filename}: {e}")
            return None

    def rm(self, bucket: str, filename: str) -> bool:
        """
        删除文件

        Args:
            bucket: 存储桶名称
            filename: 文件名

        Returns:
            bool: 删除是否成功
        """
        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="DELETE", endpoint="/api/v1/files/delete", params=params)  # noqa: F841

            logging.info(f"Successfully deleted {bucket}/{filename}")
            return True

        except Exception as e:
            logging.error(f"Delete failed for {bucket}/{filename}: {e}")
            return False

    def obj_exist(self, bucket: str, filename: str) -> bool:
        """
        检查文件是否存在

        Args:
            bucket: 存储桶名称
            filename: 文件名

        Returns:
            bool: 文件是否存在
        """
        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="HEAD", endpoint="/api/v1/files/exists", params=params)

            # 根据HTTP状态码判断文件是否存在
            return response.status_code == 200

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return False
            else:
                logging.error(f"Error checking existence of {bucket}/{filename}: {e}")
                return False
        except Exception as e:
            logging.error(f"Error checking existence of {bucket}/{filename}: {e}")
            return False

    def get_presigned_url(self, bucket: str, filename: str, expires: int) -> Optional[str]:
        """
        获取预签名URL

        Args:
            bucket: 存储桶名称
            filename: 文件名
            expires: 过期时间（秒）

        Returns:
            Optional[str]: 预签名URL，失败返回None
        """
        for attempt in range(3):
            try:
                params = {"bucket": bucket, "filename": filename, "expires": expires}

                response = self._make_request(method="POST", endpoint="/api/v1/files/presigned-url", json=params)

                result = response.json()
                return result.get("presigned_url")

            except Exception as e:
                logging.error(f"Presigned URL attempt {attempt + 1} failed for {bucket}/{filename}: {e}")
                if attempt == 2:
                    break
                time.sleep(1)

        return None

    def remove_bucket(self, bucket: str) -> bool:
        """
        删除整个存储桶

        Args:
            bucket: 存储桶名称

        Returns:
            bool: 删除是否成功
        """
        try:
            params = {"bucket": bucket}

            response = self._make_request(method="DELETE", endpoint="/api/v1/buckets/delete", params=params)  # noqa: F841

            logging.info(f"Successfully removed bucket {bucket}")
            return True

        except Exception as e:
            logging.error(f"Remove bucket failed for {bucket}: {e}")
            return False

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True) -> list:
        """
        列出对象

        Args:
            bucket: 存储桶名称
            prefix: 对象前缀
            recursive: 是否递归列出

        Returns:
            list: 对象列表
        """
        try:
            params = {"bucket": bucket, "prefix": prefix, "recursive": recursive}

            response = self._make_request(method="GET", endpoint="/api/v1/objects/list", params=params)

            result = response.json()
            return result.get("objects", [])

        except Exception as e:
            logging.error(f"List objects failed for bucket {bucket}: {e}")
            return []

    def get_object_info(self, bucket: str, filename: str) -> dict:
        """
        获取对象信息

        Args:
            bucket: 存储桶名称
            filename: 文件名

        Returns:
            dict: 对象信息
        """
        try:
            params = {"bucket": bucket, "filename": filename}

            response = self._make_request(method="GET", endpoint="/api/v1/files/info", params=params)

            return response.json()

        except Exception as e:
            logging.error(f"Get object info failed for {bucket}/{filename}: {e}")
            return {}
