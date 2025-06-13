# MinerU 简化集成架构

## 🎯 核心理念

MinerU 的核心价值是将 PDF 转换为高质量的 Markdown 内容。我们的集成方案专注于这一核心价值，避免过度复杂化。

```
输入 PDF → MinerU API → 高质量 Markdown → RAGFlow 处理 → 结构化文档块
```

## 🏗️ 架构设计

### 两层清晰分工

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (rag/app/mineru.py)                │
│  • 使用 MinerU 解析器                                        │
│  • RAGFlow 标准的 chunking, tokenization                   │
│  • 与 naive.py 完全兼容的 API                               │
│  • 智能回退机制                                             │
└─────────────────────────────────────────────────────────────┘
                               ⬇
┌─────────────────────────────────────────────────────────────┐
│              解析器层 (deepdoc/parser/mineru_http_parser.py) │
│  • 调用 MinerU HTTP API                                    │
│  • PDF → Markdown 转换                                     │
│  • Markdown → sections + tables 解析                      │
│  • 自动回退到原解析器                                       │
└─────────────────────────────────────────────────────────────┘
                               ⬇
┌─────────────────────────────────────────────────────────────┐
│                    MinerU HTTP API                         │
│  • 接收: PDF 文件                                          │
│  • 输出: md_content (Markdown)                             │
│  • 专业的模型推理服务                                       │
└─────────────────────────────────────────────────────────────┘
```

### 职责分离

| 层级 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **MinerU API** | PDF → Markdown 转换 | PDF 文件 | Markdown 文本 |
| **解析器层** | Markdown 结构化 | Markdown | sections + tables |
| **应用层** | RAGFlow 标准处理 | sections + tables | 文档块 |

## 📝 核心接口

### 1. 解析器层接口

```python
from deepdoc.parser.mineru_http_parser import MinerUHttpParser

# 简化配置
config = {
    "endpoint": "http://172.19.0.3:8081/file_parse",
    "timeout": 600,
    "parse_method": "auto",  # auto/ocr/txt
    "enable_mineru": True
}

parser = MinerUHttpParser(mineru_config=config)
sections, tables = parser("document.pdf")
```

### 2. 应用层接口

```python
from rag.app.mineru import chunk

# 与 naive.chunk 完全相同的接口
result = chunk(
    filename="document.pdf",
    parser_config={
        "chunk_token_num": 128,
        "delimiter": "\n!?。；！？",
        "mineru_endpoint": "http://172.19.0.3:8081/file_parse",
        "enable_mineru": True
    }
)
```

## 🔧 配置系统

### 三级配置优先级

```
kwargs 参数 > parser_config > settings 默认值
```

### 配置示例

```python
# 1. 环境变量配置 (settings.py)
MINERU_ENDPOINT = "http://172.19.0.3:8081/file_parse"
MINERU_TIMEOUT = 600
MINERU_PARSE_METHOD = "auto"
MINERU_FALLBACK = True

# 2. 解析器配置
parser_config = {
    "mineru_endpoint": "http://custom:8081/file_parse",  # 覆盖环境变量
    "mineru_timeout": 900,
    "parse_method": "ocr",
    "chunk_token_num": 256
}

# 3. 运行时参数
result = chunk(
    "document.pdf",
    parser_config=parser_config,
    mineru_endpoint="http://runtime:8081/file_parse"  # 最高优先级
)
```

## 🛡️ 错误处理和回退

### 自动回退机制

```python
def mineru_parse():
    try:
        # 1. 尝试 MinerU
        return mineru_api_call()
    except Exception as e:
        logger.warning(f"MinerU failed: {e}")
        # 2. 自动回退到原解析器
        return fallback_parser()
```

### 回退触发条件

- MinerU 服务不可用
- 网络超时
- API 返回错误
- 返回空内容
- 手动禁用 (`enable_mineru: False`)

### 用户体验

- ✅ **无感知**: 用户不需要处理 MinerU 失败
- ✅ **保证可用**: 总是能得到解析结果
- ✅ **自动降级**: 自动使用备选方案
- ✅ **透明日志**: 记录回退原因

## 📊 处理流程

### 完整流程图

```
📄 PDF 文件
    ⬇
🔄 MinerU API 调用
    ⬇
📝 Markdown 内容
    ⬇
🔍 解析 sections 和 tables
    ⬇
📊 RAGFlow 表格处理
    ⬇
✂️ RAGFlow 文本分块
    ⬇
🏷️ RAGFlow 标记化
    ⬇
📦 结构化文档块
```

### 关键步骤说明

1. **MinerU 转换**: PDF → 高质量 Markdown
2. **结构解析**: Markdown → 段落 + 表格
3. **标准处理**: 复用 RAGFlow 成熟逻辑
4. **输出格式**: 与原有系统完全兼容

## 🚀 使用方法

### 基础使用

```python
from rag.app.mineru import chunk

# 最简单的用法
result = chunk("document.pdf")

# 带配置的用法
config = {
    "chunk_token_num": 128,
    "mineru_endpoint": "http://172.19.0.3:8081/file_parse"
}
result = chunk("document.pdf", parser_config=config)
```

### 零修改迁移

```python
# 原来的代码
from rag.app.naive import chunk
result = chunk("document.pdf", parser_config=config)

# 新代码 (只需修改 import!)
from rag.app.mineru import chunk  # 唯一改动
result = chunk("document.pdf", parser_config=config)  # 其他完全相同
```

### 临时禁用 MinerU

```python
# 方法1: 配置禁用
config = {"enable_mineru": False}
result = chunk("document.pdf", parser_config=config)

# 方法2: 环境变量
# 设置 MINERU_FALLBACK=false
```

## 🎛️ 配置参考

### MinerU 专用配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mineru_endpoint` | str | `http://172.19.0.3:8081/file_parse` | MinerU API 端点 |
| `mineru_timeout` | int | `600` | 请求超时时间(秒) |
| `parse_method` | str | `auto` | 解析方法: auto/ocr/txt |
| `enable_mineru` | bool | `True` | 是否启用 MinerU |

### RAGFlow 标准配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `chunk_token_num` | int | `128` | 分块大小(tokens) |
| `delimiter` | str | `\n!?。；！？` | 分块分隔符 |
| `from_page` | int | `0` | 起始页码 |
| `to_page` | int | `100000` | 结束页码 |

## 🔍 调试和监控

### 日志配置

```python
import logging
logging.getLogger('deepdoc.parser.mineru_http_parser').setLevel(logging.DEBUG)
```

### 健康检查

```python
from rag.app.mineru import is_mineru_available

if is_mineru_available():
    print("✅ MinerU 服务可用")
else:
    print("❌ MinerU 服务不可用，将使用回退解析器")
```

### 进度监控

```python
def progress_callback(progress=None, msg=""):
    if progress:
        print(f"进度: {progress:.1%}")
    if msg:
        print(f"状态: {msg}")

result = chunk("document.pdf", callback=progress_callback)
```

## 🎯 最佳实践

### 1. 配置管理

```python
# 推荐：环境变量 + 配置文件
# .env
MINERU_ENDPOINT=http://172.19.0.3:8081/file_parse
MINERU_TIMEOUT=600

# config.py
PARSER_CONFIG = {
    "chunk_token_num": 128,
    "delimiter": "\n!?。；！？",
    "enable_mineru": True
}
```

### 2. 错误处理

```python
try:
    result = chunk("document.pdf", parser_config=config)
except Exception as e:
    logger.error(f"文档处理失败: {e}")
    # 应用级错误处理
```

### 3. 性能优化

```python
# 批量处理时复用解析器实例
from rag.app.mineru import get_mineru_parser_instance

parser = get_mineru_parser_instance(config)
for pdf_file in pdf_files:
    sections, tables = parser(pdf_file)
```

## 📈 性能特点

### 优势

- ✅ **高质量**: MinerU 提供更好的 PDF 解析
- ✅ **稳定性**: 自动回退保证可用性
- ✅ **兼容性**: 与现有系统完全兼容
- ✅ **简洁性**: 清晰的架构和接口

### 适用场景

- 🎯 **主要场景**: 需要高质量 PDF 解析的场景
- 🎯 **备选场景**: MinerU 不可用时的自动回退
- 🎯 **迁移场景**: 从现有解析器无缝升级

### 注意事项

- ⚠️ **网络依赖**: 需要 MinerU 服务可访问
- ⚠️ **格式限制**: 当前专注于 PDF 文件
- ⚠️ **超时设置**: 根据文档大小调整超时时间

## 🔄 版本升级

### 从复杂版本迁移

如果你使用的是之前复杂的 MinerU 集成方案：

```python
# 旧的复杂配置
old_config = {
    "return_layout": True,
    "return_info": True,
    "return_content_list": True,
    "return_images": True,
    "process_images": True,
    "generate_image_descriptions": True,
    # ... 更多复杂配置
}

# 新的简化配置
new_config = {
    "mineru_endpoint": "http://172.19.0.3:8081/file_parse",
    "parse_method": "auto",
    "enable_mineru": True
}
```

### 配置迁移指南

| 旧配置项 | 新配置项 | 说明 |
|---------|---------|------|
| `return_*` | 移除 | 专注核心功能 |
| `process_images` | 移除 | 由 RAGFlow 处理 |
| `generate_image_descriptions` | 移除 | 简化架构 |
| `endpoint` | `mineru_endpoint` | 更清晰的命名 |

## 💡 总结

MinerU 简化集成方案的核心价值：

1. **专注核心**: MinerU 专注 PDF → Markdown 转换
2. **复用成熟**: 充分利用 RAGFlow 现有逻辑
3. **简洁可靠**: 清晰架构 + 自动回退
4. **零修改集成**: 完全兼容现有 API
5. **渐进式采用**: 可以逐步启用和测试

这个方案解决了之前代码过于复杂的问题，让 MinerU 集成变得简单、可靠、易维护。
