# MinerU与RAGFlow集成使用指南

## 概述

本指南介绍如何在RAGFlow中使用MinerU HTTP服务进行PDF文档解析。MinerU是一个高效的文档解析工具，能够准确识别文档的布局、表格、图像等结构化信息。

## 架构说明

### 集成组件

1. **MinerUHttpParser** (`deepdoc/parser/mineru_http_parser.py`)
   - HTTP客户端，负责与MinerU服务通信
   - 处理文件上传和结果解析
   - 支持回退到默认解析器

2. **MinerU应用模块** (`rag/app/mineru.py`)
   - 实现RAGFlow的chunking接口
   - 集成文档结构分析和分块逻辑
   - 支持表格和图像处理

3. **任务执行器集成** (`rag/svr/task_executor.py`)
   - 在FACTORY中注册MinerU解析器
   - 支持异步任务处理

## 配置说明

### 环境变量配置

在启动RAGFlow之前，设置以下环境变量：

```bash
# MinerU服务端点
export MINERU_ENDPOINT="http://localhost:8888/file_parse"

# 请求超时时间（秒）
export MINERU_TIMEOUT="600"

# 是否启用回退到默认解析器
export MINERU_FALLBACK="true"

# MinerU解析方法 (auto, ocr, txt)
export MINERU_PARSE_METHOD="auto"
```

### 代码配置

也可以在代码中动态配置：

```python
from deepdoc.parser.mineru_http_parser import create_mineru_parser

config = {
    "endpoint": "http://your-mineru-server:8888/file_parse",
    "timeout": 600,
    "fallback_to_default": True,
    "parse_method": "auto",
    "return_layout": True,
    "return_info": True,
    "return_content_list": True
}

parser = create_mineru_parser(config)
```

## 使用方法

### 1. 在RAGFlow中选择MinerU解析器

在RAGFlow的Web界面中：

1. 创建新的知识库
2. 上传PDF文档
3. 在解析器选择中选择 "MinerU"
4. 开始解析

### 2. 程序化调用

```python
from rag.app.mineru import chunk

def callback(progress=None, msg=""):
    print(f"进度: {progress}, 消息: {msg}")

# 解析PDF文件
result = chunk(
    filename="document.pdf",
    binary=None,  # 或提供文件的二进制内容
    from_page=0,
    to_page=100000,
    lang="Chinese",
    callback=callback
)

print(f"生成了 {len(result)} 个文档块")
```

### 3. 高级配置

```python
from rag.app.mineru import chunk

# 使用自定义配置
result = chunk(
    filename="document.pdf",
    lang="Chinese",
    callback=callback,
    # MinerU特定参数
    mineru_endpoint="http://custom-server:8888/file_parse",
    mineru_timeout=300,
    fallback_to_default=True,
    parse_method="ocr",  # 强制使用OCR
    return_layout=True,
    return_info=True
)
```

## MinerU服务部署

### 使用Docker部署MinerU

```bash
# 拉取MinerU镜像
docker pull mineruproject/mineru:latest

# 运行MinerU服务
docker run -d \
  --name mineru-service \
  -p 8888:8888 \
  -v /path/to/models:/app/models \
  mineruproject/mineru:latest
```

### 验证MinerU服务

```bash
# 检查服务状态
curl -X GET http://localhost:8888/health

# 测试文档解析
curl -X POST \
  -F "file=@test.pdf" \
  -F "parse_method=auto" \
  http://localhost:8888/file_parse
```

## 特性说明

### 支持的功能

1. **文档结构识别**
   - 自动识别标题、段落、表格
   - 保留文档层次结构
   - 支持多列布局

2. **表格处理**
   - 表格内容提取
   - HTML/Markdown格式输出
   - 表格位置信息保留

3. **图像处理**
   - 图像位置识别
   - 图像描述生成
   - 图像内容标记

4. **多语言支持**
   - 中文文档优化
   - 英文文档支持
   - 混合语言处理

### 解析方法选项

- **auto**: 自动选择最佳解析方法
- **ocr**: 强制使用OCR技术
- **txt**: 提取纯文本内容

## 故障排除

### 常见问题

1. **连接超时**
   ```
   解决方案: 增加MINERU_TIMEOUT值或检查网络连接
   ```

2. **解析失败**
   ```
   解决方案: 确保MINERU_FALLBACK=true以启用回退机制
   ```

3. **服务不可用**
   ```
   解决方案: 检查MinerU服务是否正常运行
   curl http://localhost:8888/health
   ```

### 日志查看

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看详细的解析日志
result = chunk(filename="document.pdf", callback=callback)
```

### 性能优化

1. **调整超时时间**
   - 大文档需要更长的处理时间
   - 根据文档大小调整timeout

2. **选择合适的解析方法**
   - 文字清晰的PDF使用"txt"模式
   - 扫描件或图像PDF使用"ocr"模式
   - 不确定时使用"auto"模式

3. **批量处理**
   ```python
   # 并发处理多个文档
   import asyncio
   from concurrent.futures import ThreadPoolExecutor

   async def process_documents(file_list):
       with ThreadPoolExecutor(max_workers=3) as executor:
           tasks = [
               asyncio.get_event_loop().run_in_executor(
                   executor, chunk, filename
               ) for filename in file_list
           ]
           return await asyncio.gather(*tasks)
   ```

## 测试集成

运行集成测试脚本：

```bash
cd /path/to/ragflow
python test_mineru_integration.py
```

测试覆盖以下方面：
- 模块导入测试
- 配置验证
- 解析器注册检查
- 功能可用性验证

## API参考

### chunk函数参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| filename | str | 必需 | 文件路径或名称 |
| binary | bytes | None | 文件二进制内容 |
| from_page | int | 0 | 起始页码 |
| to_page | int | 100000 | 结束页码 |
| lang | str | "Chinese" | 语言设置 |
| callback | function | None | 进度回调函数 |

### 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| endpoint | str | localhost:8888 | MinerU服务地址 |
| timeout | int | 600 | 请求超时时间 |
| fallback_to_default | bool | True | 是否启用回退 |
| parse_method | str | "auto" | 解析方法 |
| return_layout | bool | True | 返回布局信息 |
| return_info | bool | True | 返回详细信息 |

## 最佳实践

1. **生产环境部署**
   - 使用负载均衡器分发MinerU请求
   - 设置合理的超时和重试机制
   - 监控MinerU服务健康状态

2. **资源管理**
   - 限制并发处理的文档数量
   - 定期清理临时文件
   - 监控内存和CPU使用

3. **错误处理**
   - 总是启用fallback机制
   - 记录详细的错误日志
   - 提供用户友好的错误信息

## 更新日志

- **v1.0.0**: 初始版本，支持基本的PDF解析
- **v1.1.0**: 添加表格和图像处理支持
- **v1.2.0**: 优化性能和错误处理
- **v1.3.0**: 支持批量处理和异步操作

## 贡献指南

欢迎提交问题和改进建议到项目仓库。在提交代码时，请确保：

1. 遵循现有的代码风格
2. 添加适当的测试用例
3. 更新相关文档
4. 通过所有集成测试

## 许可证

本集成模块遵循Apache 2.0许可证。
