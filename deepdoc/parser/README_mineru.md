# MinerU HTTP 解析器

## 概述

MinerU HTTP 解析器是 RAGFlow 项目的一个扩展组件，提供与原有 PDF 解析器完全兼容的接口，同时内置了 MinerU HTTP API 调用和智能回退机制。它能够在不修改现有代码的情况下，为 RAGFlow 提供更高质量的 PDF 解析能力。

## 核心特性

- **完全兼容**: 继承自 `RAGFlowPdfParser`，提供完全一致的接口
- **智能回退**: MinerU 解析失败时自动回退到原有 PDF 解析器
- **零修改集成**: 可以直接替换现有的 PDF 解析器类，无需修改调用代码
- **高质量解析**: 利用 MinerU 的先进 PDF 解析能力
- **灵活配置**: 支持运行时启用/禁用 MinerU
- **完整错误处理**: 优雅处理各种异常情况

## 设计架构

```
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│   用户调用      │───▶│  MinerUHttpParser   │───▶│ 原有RAGFlow处理  │
│ (无需修改代码)  │    │                     │    │      流程        │
└─────────────────┘    └─────────────────────┘    └──────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   MinerU API    │
                       │    (优先尝试)    │
                       └─────────────────┘
                                │
                          ❌ 失败时 ▼
                       ┌─────────────────┐
                       │ 原有PDF解析器   │
                       │   (自动回退)    │
                       └─────────────────┘
```

## 快速开始

### 1. 基本配置

```python
mineru_config = {
    "endpoint": "http://172.19.0.3:8081/file_parse",
    "timeout": 600,
    "parse_method": "auto",
    "enable_mineru": True  # 可以用来快速禁用
}
```

### 2. 直接替换使用（推荐）

最简单的使用方式，只需要替换解析器类：

```python
from deepdoc.parser.mineru_http_parser import MinerUHttpParser

# 创建解析器（内置回退机制）
parser = MinerUHttpParser(mineru_config=mineru_config)

# 完全兼容原有接口
sections, tables = parser(
    filename="document.pdf",
    from_page=0,
    to_page=100000,
    callback=progress_callback
)
```

### 3. 在 RAGFlow 框架中使用

通过临时替换类的方式集成到现有系统：

```python
import rag.app.naive as naive_module
from deepdoc.parser.mineru_http_parser import MinerUHttpParser

# 保存原有类
original_pdf_class = naive_module.Pdf

# 创建包装类
class MinerUPdf(MinerUHttpParser):
    def __init__(self):
        super().__init__(mineru_config=mineru_config)

# 临时替换
naive_module.Pdf = MinerUPdf

try:
    # 正常调用现有函数，无需修改任何代码
    results = chunk(filename="document.pdf", ...)
finally:
    # 恢复原有类
    naive_module.Pdf = original_pdf_class
```

## 配置选项

### 核心配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `endpoint` | str | 必需 | MinerU HTTP 服务地址 |
| `enable_mineru` | bool | True | 是否启用 MinerU（快速开关） |
| `timeout` | int | 600 | HTTP 请求超时时间（秒） |

### MinerU 特定配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `parse_method` | str | "auto" | 解析方法："auto", "ocr", "txt" |
| `return_layout` | bool | True | 是否返回布局信息 |
| `return_info` | bool | True | 是否返回详细信息 |
| `return_content_list` | bool | True | 是否返回内容列表 |

## 智能回退机制

解析器会在以下情况自动回退到原有 PDF 解析器：

1. **配置错误**: MinerU 端点未配置或配置错误
2. **网络问题**: HTTP 请求超时或连接失败
3. **服务异常**: MinerU 服务返回错误状态
4. **内容异常**: 返回空内容或格式错误
5. **手动禁用**: `enable_mineru` 设置为 False

回退过程：
- 记录警告日志（不会中断程序）
- 使用原有 `RAGFlowPdfParser` 继续处理
- 保持完全相同的返回格式

## 使用场景

### 场景1: 新项目直接使用

```python
from deepdoc.parser.mineru_http_parser import create_mineru_parser

parser = create_mineru_parser(mineru_config=config)
sections, tables = parser("document.pdf")
```

### 场景2: 现有项目零修改升级

```python
# 原有代码
from deepdoc.parser.pdf_parser import RAGFlowPdfParser
parser = RAGFlowPdfParser()

# 升级后代码（只需修改这一行）
from deepdoc.parser.mineru_http_parser import MinerUHttpParser
parser = MinerUHttpParser(mineru_config=config)

# 其他代码无需任何修改
sections, tables = parser(filename, ...)
```

### 场景3: 临时测试和对比

```python
# 快速禁用 MinerU 进行对比测试
config_disabled = config.copy()
config_disabled["enable_mineru"] = False

parser = MinerUHttpParser(mineru_config=config_disabled)
# 此时会直接使用原有解析器
```

## 性能优化

### 1. 合理设置超时时间

```python
# 根据文档大小调整
config = {
    "timeout": 300,  # 小文档
    # "timeout": 1200,  # 大文档
}
```

### 2. 选择合适的解析方法

```python
config = {
    "parse_method": "auto",    # 智能选择（推荐）
    # "parse_method": "ocr",   # 强制OCR（扫描件）
    # "parse_method": "txt",   # 纯文本提取（速度快）
}
```

### 3. 缓存和复用

```python
# 创建解析器实例并复用
parser = MinerUHttpParser(mineru_config=config)

# 处理多个文档
for filename in filenames:
    sections, tables = parser(filename)
```

## 故障排除

### 1. 检查 MinerU 服务状态

```python
import requests

try:
    response = requests.get("http://172.19.0.3:8081/health", timeout=5)
    print(f"MinerU 服务状态: {response.status_code}")
except Exception as e:
    print(f"MinerU 服务不可用: {e}")
```

### 2. 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 或者只启用 MinerU 相关日志
logger = logging.getLogger('deepdoc.parser.mineru_http_parser')
logger.setLevel(logging.DEBUG)
```

### 3. 测试回退机制

```python
# 使用无效端点测试
test_config = {
    "endpoint": "http://invalid:8081/parse",
    "enable_mineru": True
}

parser = MinerUHttpParser(mineru_config=test_config)
# 应该会自动回退到原有解析器
```

### 4. 常见错误解决

**错误**: `ConnectionError: HTTPConnectionPool timeout`
```python
# 解决方案1: 增加超时时间
config["timeout"] = 1200

# 解决方案2: 检查网络连接
# 解决方案3: 临时禁用 MinerU
config["enable_mineru"] = False
```

**错误**: `JSONDecodeError: Expecting value`
```python
# 通常是 MinerU 服务异常，会自动回退
# 检查 MinerU 服务日志
```

## 高级用法

### 1. 自定义回调处理

```python
def smart_callback(progress=None, msg=""):
    if "MinerU" in msg:
        print(f"🚀 {msg}")
    elif "回退" in msg or "fallback" in msg.lower():
        print(f"⚠️  {msg}")
    else:
        print(f"📄 {msg}")

parser = MinerUHttpParser(mineru_config=config)
sections, tables = parser("document.pdf", callback=smart_callback)
```

### 2. 批量处理

```python
def batch_process(filenames, config):
    parser = MinerUHttpParser(mineru_config=config)
    results = []

    for filename in filenames:
        try:
            sections, tables = parser(filename)
            results.append({
                "filename": filename,
                "sections": len(sections),
                "tables": len(tables),
                "status": "success"
            })
        except Exception as e:
            results.append({
                "filename": filename,
                "error": str(e),
                "status": "failed"
            })

    return results
```

### 3. 动态配置切换

```python
class AdaptiveMinerUParser:
    def __init__(self, primary_config, fallback_config):
        self.primary_parser = MinerUHttpParser(mineru_config=primary_config)
        self.fallback_parser = MinerUHttpParser(mineru_config=fallback_config)
        self.use_fallback = False

    def parse(self, filename, **kwargs):
        parser = self.fallback_parser if self.use_fallback else self.primary_parser

        try:
            return parser(filename, **kwargs)
        except Exception:
            if not self.use_fallback:
                self.use_fallback = True
                return self.fallback_parser(filename, **kwargs)
            raise
```

## 版本兼容性

- **RAGFlow**: 完全兼容当前版本
- **MinerU**: 支持 HTTP API 的版本
- **Python**: >= 3.7

## 许可证

遵循 RAGFlow 项目的开源许可证。
