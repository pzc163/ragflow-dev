# RAGFlow第三方文件存储接口集成指南

## 📋 概述

RAGFlow支持接入第三方文件管理接口来替换默认的Minio存储方案。通过统一的存储抽象层，你可以轻松地将任何支持RESTful API的第三方文件存储服务集成到RAGFlow中。

## 🏗️ 架构设计

RAGFlow采用了**工厂模式**和**策略模式**来实现存储后端的抽象化：

```
RAGFlow应用层
    ↓
存储工厂（StorageFactory）
    ↓
存储接口实现（Storage Implementation）
    ↓
第三方存储服务
```

### 核心组件

1. **StorageFactory** - 存储工厂类，负责创建存储实例
2. **Storage接口** - 定义了所有存储操作的标准接口
3. **第三方存储连接器** - 实现存储接口的具体类
4. **配置管理** - 通过配置文件管理不同存储服务的参数

## 🚀 快速开始

### 1. 创建第三方存储连接器

RAGFlow已经提供了一个通用的第三方存储连接器，支持大多数RESTful API：

- `rag/utils/third_party_storage_conn.py` - 基础连接器
- `rag/utils/third_party_storage_adapter.py` - 增强版适配器（推荐）

### 2. 配置第三方存储服务

创建配置文件 `conf/third_party_storage.yml`：

```yaml
# 基础配置
base_url: "https://your-storage-api.example.com"
api_key: "your-api-key-here"
timeout: 30

# 认证配置
auth:
  type: "bearer"              # 支持: bearer, basic, api_key
  token: "your-bearer-token"

# API端点配置
endpoints:
  upload: "/api/v1/files/upload"
  download: "/api/v1/files/download"
  delete: "/api/v1/files/delete"
  exists: "/api/v1/files/exists"
  presigned_url: "/api/v1/files/presigned-url"
```

### 3. 启用第三方存储

设置环境变量：

```bash
export STORAGE_IMPL=THIRD_PARTY
```

或在Docker环境中更新 `.env` 文件：

```env
STORAGE_IMPL=THIRD_PARTY
```

### 4. 测试配置

运行测试脚本验证配置：

```bash
python test_third_party_storage.py
```

## 📖 详细配置说明

### 认证配置

#### Bearer Token认证
```yaml
auth:
  type: "bearer"
  token: "your-bearer-token"
```

#### 基础认证
```yaml
auth:
  type: "basic"
  username: "your-username"
  password: "your-password"
```

#### API Key认证
```yaml
auth:
  type: "api_key"
  api_key: "your-api-key"
  api_key_header: "X-API-Key"
```

### API端点配置

```yaml
endpoints:
  upload: "/api/v1/files/upload"           # 文件上传
  download: "/api/v1/files/download"       # 文件下载
  delete: "/api/v1/files/delete"           # 文件删除
  exists: "/api/v1/files/exists"           # 文件存在检查
  info: "/api/v1/files/info"               # 文件信息
  presigned_url: "/api/v1/files/presigned-url"  # 预签名URL
  list_objects: "/api/v1/objects/list"     # 对象列表
  bucket_delete: "/api/v1/buckets/delete"  # 存储桶删除
```

### 高级配置

```yaml
# 请求配置
request:
  max_retries: 3              # 最大重试次数
  retry_delay: 1              # 重试延迟（秒）
  chunk_size: 8192            # 上传/下载块大小

# 缓存配置
advanced:
  enable_cache: true          # 启用缓存
  cache_ttl: 3600            # 缓存TTL（秒）

# 监控配置
monitoring:
  enable_metrics: true        # 启用指标收集
  performance_tracking: true  # 启用性能跟踪
```

## 🔌 API接口规范

第三方存储服务需要实现以下API接口：

### 文件上传
```http
POST /api/v1/files/upload
Content-Type: multipart/form-data

Parameters:
- file: 文件数据
- bucket: 存储桶名称
- filename: 文件名

Response:
{
  "status": "success",
  "file_url": "https://example.com/files/bucket/filename"
}
```

### 文件下载
```http
GET /api/v1/files/download?bucket=bucket_name&filename=file_name

Response:
文件二进制数据
```

### 文件删除
```http
DELETE /api/v1/files/delete?bucket=bucket_name&filename=file_name

Response:
{
  "status": "success"
}
```

### 文件存在检查
```http
HEAD /api/v1/files/exists?bucket=bucket_name&filename=file_name

Response:
200 OK (文件存在)
404 Not Found (文件不存在)
```

### 预签名URL
```http
POST /api/v1/files/presigned-url
Content-Type: application/json

{
  "bucket": "bucket_name",
  "filename": "file_name",
  "expires": 3600
}

Response:
{
  "presigned_url": "https://example.com/presigned-url"
}
```

## 🔧 自定义存储连接器

如果内置的连接器不满足你的需求，可以创建自定义连接器：

### 1. 创建连接器类

```python
from rag.utils import singleton

@singleton
class CustomStorageConnector:
    def __init__(self):
        # 初始化连接
        pass

    def health(self):
        # 健康检查
        pass

    def put(self, bucket: str, filename: str, binary: bytes):
        # 上传文件
        pass

    def get(self, bucket: str, filename: str):
        # 下载文件
        pass

    def rm(self, bucket: str, filename: str):
        # 删除文件
        pass

    def obj_exist(self, bucket: str, filename: str):
        # 检查文件是否存在
        pass

    def get_presigned_url(self, bucket: str, filename: str, expires: int):
        # 获取预签名URL
        pass

    def remove_bucket(self, bucket: str):
        # 删除存储桶
        pass
```

### 2. 注册连接器

在 `rag/utils/storage_factory.py` 中添加：

```python
from your_module import CustomStorageConnector

class Storage(Enum):
    # ... 现有类型
    CUSTOM = 7

class StorageFactory:
    storage_mapping = {
        # ... 现有映射
        Storage.CUSTOM: CustomStorageConnector,
    }
```

### 3. 更新配置

在 `rag/settings.py` 中添加配置支持：

```python
elif STORAGE_IMPL_TYPE == 'CUSTOM':
    CUSTOM_STORAGE = get_base_config("custom_storage", {})
```

## 🔄 存储迁移

### 从Minio迁移到第三方存储

1. **准备迁移工具**

```python
def migrate_storage(source_storage, target_storage, bucket_name):
    """迁移存储数据"""

    # 获取源存储中的所有对象
    objects = source_storage.list_objects(bucket_name)

    for obj in objects:
        # 从源存储下载
        data = source_storage.get(bucket_name, obj['name'])

        if data:
            # 上传到目标存储
            target_storage.put(bucket_name, obj['name'], data)
            print(f"迁移完成: {obj['name']}")
```

2. **执行迁移**

```bash
# 1. 停止RAGFlow服务
docker-compose down

# 2. 运行迁移脚本
python migrate_storage.py

# 3. 更新配置
export STORAGE_IMPL=THIRD_PARTY

# 4. 重启服务
docker-compose up -d
```

## 📊 监控和调试

### 启用调试日志

```yaml
logging:
  enable_debug: true
  log_requests: true
  log_responses: false
```

### 性能监控

```python
from rag.utils.storage_factory import STORAGE_IMPL

# 获取性能指标
if hasattr(STORAGE_IMPL, 'get_metrics'):
    metrics = STORAGE_IMPL.get_metrics()
    print(f"请求总数: {metrics['requests_count']}")
    print(f"成功率: {metrics['success_count'] / metrics['requests_count'] * 100:.2f}%")
    print(f"上传字节数: {metrics['total_bytes_uploaded']}")
    print(f"下载字节数: {metrics['total_bytes_downloaded']}")
```

## 🛠️ 故障排除

### 常见问题

1. **连接失败**
   - 检查base_url是否正确
   - 验证网络连接
   - 确认API服务是否运行

2. **认证失败**
   - 检查API密钥是否有效
   - 确认认证类型配置正确
   - 验证权限设置

3. **上传/下载失败**
   - 检查文件大小限制
   - 验证存储桶权限
   - 确认API端点路径

### 调试步骤

1. **运行健康检查**
```bash
python -c "
from rag.utils.storage_factory import STORAGE_IMPL
print('健康状态:', STORAGE_IMPL.health())
"
```

2. **检查配置**
```bash
python -c "
from rag import settings
print('存储类型:', settings.STORAGE_IMPL_TYPE)
print('配置:', settings.THIRD_PARTY_STORAGE)
"
```

3. **运行完整测试**
```bash
python test_third_party_storage.py
```

## 🔐 安全注意事项

1. **API密钥管理**
   - 使用环境变量存储敏感信息
   - 定期轮换API密钥
   - 限制API密钥权限

2. **网络安全**
   - 使用HTTPS加密传输
   - 配置防火墙规则
   - 启用访问日志

3. **数据保护**
   - 启用传输加密
   - 考虑静态数据加密
   - 实施访问控制

## 📚 示例配置

### 阿里云OSS
```yaml
base_url: "https://oss-cn-hangzhou.aliyuncs.com"
auth:
  type: "bearer"
  token: "your-oss-token"
endpoints:
  upload: "/api/v1/object/upload"
  download: "/api/v1/object/download"
```

### 腾讯云COS
```yaml
base_url: "https://cos.ap-beijing.myqcloud.com"
auth:
  type: "api_key"
  api_key: "your-cos-secret-key"
  api_key_header: "Authorization"
```

### 华为云OBS
```yaml
base_url: "https://obs.cn-north-4.myhuaweicloud.com"
auth:
  type: "basic"
  username: "your-access-key"
  password: "your-secret-key"
```

## 🎯 最佳实践

1. **性能优化**
   - 启用缓存减少API调用
   - 使用连接池
   - 配置合适的超时时间

2. **可靠性**
   - 配置重试机制
   - 实施健康检查
   - 监控错误率

3. **可维护性**
   - 使用版本化的API
   - 记录详细日志
   - 编写测试用例

4. **扩展性**
   - 支持多个存储后端
   - 实施负载均衡
   - 考虑分布式部署

---

## 🤝 支持和贡献

如果你在集成第三方存储时遇到问题，或者想要贡献新的存储连接器，请：

1. 查看现有的[Issues](https://github.com/infiniflow/ragflow/issues)
2. 创建新的Issue描述你的问题
3. 提交Pull Request贡献代码

我们欢迎社区贡献更多的存储后端支持！
