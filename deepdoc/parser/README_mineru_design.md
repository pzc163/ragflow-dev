# MinerU 模块化设计方案

## 🎯 设计理念

本方案采用**完全独立的模块化设计**，在不修改任何原有代码的基础上，为 RAGFlow 集成 MinerU HTTP 解析服务。

### 核心原则

1. **零侵入性**: 不修改 `rag/app/naive.py` 等原有核心文件
2. **职责分离**: 解析器层只负责格式转换，应用层负责 chunking 等后处理
3. **完全兼容**: 提供与原有接口完全兼容的 API
4. **智能回退**: 内置多层回退机制确保系统稳定性

## 📁 架构设计

```
深度文档解析 (deepdoc/)
├── parser/
│   ├── pdf_parser.py           # 原有 PDF 解析器（未修改）
│   ├── markdown_parser.py      # 原有 Markdown 解析器（未修改）
│   └── mineru_http_parser.py   # 新增：MinerU HTTP 解析器层
│
应用层处理 (rag/app/)
├── naive.py                    # 原有应用逻辑（完全未修改）
└── mineru.py                   # 新增：MinerU 专用应用层

示例和文档 (examples/)
├── mineru_config_example.py    # 基础配置示例
└── mineru_standalone_example.py # 独立模块使用示例
```

## 🔧 组件职责

### 1. 解析器层 (`deepdoc/parser/mineru_http_parser.py`)

**职责**：
- 调用 MinerU HTTP API
- 将 MinerU 返回的 markdown 内容转换为标准的 `(sections, tables)` 格式
- 提供与 `RAGFlowPdfParser` 完全兼容的接口
- 实现智能回退机制

**不负责**：
- ❌ chunking, tokenization, merge 等应用层逻辑
- ❌ 复杂的文档结构分析
- ❌ 与 RAGFlow 业务逻辑的深度集成

### 2. 应用层 (`rag/app/mineru.py`)

**职责**：
- 使用 MinerU 解析器获得 sections 和 tables
- 执行 chunking、tokenization、merge 等后处理
- 提供与 `rag.app.naive.chunk` 兼容的接口
- 实现 MinerU 特有的优化逻辑

**特点**：
- ✅ 完全独立，不依赖对原有文件的修改
- ✅ 与 `naive.py` 提供相同的功能接口
- ✅ 针对 MinerU 特点进行优化

## 🚀 使用方式

### 方式一：直接使用 MinerU 模块（推荐）

```python
from rag.app import mineru

# 配置 MinerU
parser_config = {
    "chunk_token_num": 128,
    "delimiter": "\n!?。；！？",
    "mineru_config": {
        "endpoint": "http://172.19.0.3:8081/file_parse",
        "timeout": 600,
        "enable_mineru": True
    }
}

# 使用 MinerU 处理文档
results = mineru.chunk(
    filename="document.pdf",
    lang="Chinese",
    parser_config=parser_config,
    fallback_to_plain=True
)
```

### 方式二：解析器层直接使用

```python
from deepdoc.parser.mineru_http_parser import MinerUHttpParser

# 创建解析器
parser = MinerUHttpParser(mineru_config={
    "endpoint": "http://172.19.0.3:8081/file_parse",
    "enable_mineru": True
})

# 获得原始的 sections 和 tables
sections, tables = parser("document.pdf")
```

### 方式三：作为服务使用

```python
from rag.app.mineru import create_mineru_processor, is_mineru_available

# 检查服务可用性
if is_mineru_available():
    processor = create_mineru_processor()
    # 使用处理器...
```

## 🛡️ 回退机制

### 多层回退策略

1. **MinerU HTTP 服务** → 2. **原有 RAGFlow PDF 解析器** → 3. **简单文本解析器**

```python
# 配置回退
parser_config = {
    "mineru_config": {
        "endpoint": "http://172.19.0.3:8081/file_parse",
        "enable_mineru": True  # 可以通过此开关禁用 MinerU
    }
}

# 启用回退机制
results = mineru.chunk(
    filename="document.pdf",
    parser_config=parser_config,
    fallback_to_plain=True  # 启用最终回退
)
```

### 回退触发条件

- MinerU 服务不可达
- API 调用超时
- 返回结果格式异常
- 配置中 `enable_mineru=False`

## ⚙️ 配置管理

### 配置优先级

**kwargs > parser_config.mineru_config > parser_config > settings 默认值**

```python
# 示例：多种配置来源
parser_config = {
    "mineru_endpoint": "http://config-level:8081/file_parse",
    "mineru_config": {
        "endpoint": "http://inner-config:8081/file_parse",
        "timeout": 300
    }
}

# kwargs 参数具有最高优先级
results = mineru.chunk(
    filename="document.pdf",
    parser_config=parser_config,
    mineru_endpoint="http://kwargs-level:8081/file_parse",  # 最高优先级
    mineru_timeout=900
)
```

### 配置选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `endpoint` | `http://172.19.0.3:8081/file_parse` | MinerU 服务地址 |
| `timeout` | `600` | 请求超时时间（秒） |
| `parse_method` | `"auto"` | 解析方法：auto/ocr/txt |
| `enable_mineru` | `True` | 是否启用 MinerU |
| `return_layout` | `True` | 是否返回布局信息 |
| `return_info` | `True` | 是否返回详细信息 |
| `return_content_list` | `True` | 是否返回内容列表 |

## 🔍 与原有方案的对比

| 方面 | 原有方案 | MinerU 模块化方案 |
|------|----------|-------------------|
| **代码侵入性** | 需修改核心文件 | 零侵入，完全独立 |
| **维护成本** | 影响原有逻辑 | 独立维护，风险隔离 |
| **功能兼容性** | 可能破坏兼容性 | 完全兼容原有接口 |
| **回退机制** | 复杂实现 | 内置多层回退 |
| **职责分离** | 混合在一起 | 清晰的分层架构 |
| **测试难度** | 需要完整集成测试 | 可独立单元测试 |

## 📊 性能特点

### 优势

1. **专门优化**: 针对 MinerU 输出特点优化
2. **智能缓存**: 支持结果缓存机制
3. **并发处理**: 支持批量文档处理
4. **资源控制**: 独立的资源管理

### 监控指标

```python
# 内置性能监控
from rag.app.mineru import chunk

def monitor_callback(progress=None, msg=""):
    print(f"进度: {progress:.1%}, 状态: {msg}")

results = chunk(
    filename="document.pdf",
    callback=monitor_callback,  # 监控回调
    parser_config=config
)
```

## 🧪 测试策略

### 单元测试

```python
# 测试解析器层
def test_mineru_parser():
    parser = MinerUHttpParser(test_config)
    sections, tables = parser("test.pdf")
    assert len(sections) > 0

# 测试应用层
def test_mineru_chunking():
    results = mineru.chunk("test.pdf", parser_config=test_config)
    assert len(results) > 0
```

### 集成测试

```python
# 测试回退机制
def test_fallback():
    invalid_config = {"endpoint": "http://invalid:8081/file_parse"}
    results = mineru.chunk("test.pdf",
                          parser_config={"mineru_config": invalid_config},
                          fallback_to_plain=True)
    assert len(results) > 0  # 应该通过回退成功
```

## 🚢 部署指南

### 1. 基础部署

```bash
# 只需要确保 MinerU 服务运行
docker run -p 8081:8081 mineru-service:latest
```

### 2. 配置文件

```python
# config/mineru_settings.py
MINERU_ENDPOINT = "http://172.19.0.3:8081/file_parse"
MINERU_TIMEOUT = 600
MINERU_PARSE_METHOD = "auto"
MINERU_FALLBACK = True
```

### 3. 环境变量

```bash
export MINERU_ENDPOINT="http://172.19.0.3:8081/file_parse"
export MINERU_TIMEOUT=600
export MINERU_ENABLE=true
```

## 🔧 故障排除

### 常见问题

1. **MinerU 服务连接失败**
   ```python
   from rag.app.mineru import is_mineru_available
   if not is_mineru_available():
       print("MinerU 服务不可用，检查网络和服务状态")
   ```

2. **配置优先级混乱**
   ```python
   from rag.app.mineru import _get_mineru_config
   final_config = _get_mineru_config(parser_config, **kwargs)
   print("最终配置:", final_config)
   ```

3. **回退机制未生效**
   ```python
   # 确保启用回退
   results = mineru.chunk(
       filename="document.pdf",
       fallback_to_plain=True  # 关键参数
   )
   ```

## 📈 未来扩展

### 1. 支持更多格式

```python
# 扩展支持其他文档格式
class MinerUDocxParser(MinerUHttpParser):
    def __call__(self, filename, **kwargs):
        # 实现 DOCX 支持
        pass
```

### 2. 缓存机制

```python
# 添加结果缓存
@cache_result
def cached_mineru_parse(filename, config_hash):
    return mineru.chunk(filename, parser_config=config)
```

### 3. 批量处理

```python
# 批量文档处理
def batch_process(filenames, parser_config):
    results = []
    for filename in filenames:
        result = mineru.chunk(filename, parser_config=parser_config)
        results.append(result)
    return results
```

## ✅ 总结

这个模块化设计方案实现了：

1. **零侵入集成**: 不修改任何原有代码
2. **清晰职责分离**: 解析器层 + 应用层的明确划分
3. **完全兼容性**: 与原有接口 100% 兼容
4. **智能回退**: 多层回退机制确保稳定性
5. **灵活配置**: 支持多种配置来源和优先级
6. **独立维护**: 风险隔离，便于测试和部署

这种设计既满足了集成 MinerU 的需求，又保持了系统的稳定性和可维护性。 🎉

# MinerU HTTP 解析器设计文档

## 概述

本文档描述了 MinerU HTTP 解析器的设计架构、功能特性和使用方法。该解析器基于真实的 MinerU HTTP API 实现，提供了对 PDF 文档的高质量解析，特别是在表格、图片和复杂布局处理方面表现优异。

## 核心特性

### 🚀 主要功能
1. **基于真实 API**：完全基于 MinerU 的真实 HTTP API (`/file_parse`) 实现
2. **智能回退机制**：MinerU 失败时自动回退到 RAGFlow 原生解析器
3. **完全兼容**：与现有 RAGFlow 生态系统无缝集成
4. **模块化设计**：解析器层和应用层分离，职责清晰
5. **🖼️ 智能图片处理**：提取、描述、关联PDF中的图片内容
6. **📊 表格优化**：专门针对表格内容的结构化处理

### 🖼️ 图片处理功能

#### 核心能力
- **自动图片提取**：从 MinerU API 获取 base64 编码的图片
- **图片描述生成**：智能生成图片内容描述
- **尺寸优化**：自动调整图片尺寸，节省存储空间
- **视觉模型集成**：支持集成视觉模型生成高质量描述
- **上下文关联**：将图片描述与周围文本内容关联

#### 图片处理流程
```
PDF文档 → MinerU API → 图片Base64数据 → 解码处理 → 描述生成 → 集成到文档结构
```

#### 配置选项
```python
mineru_config = {
    "return_images": True,               # 启用图片获取
    "process_images": True,              # 启用图片处理
    "generate_image_descriptions": True, # 生成图片描述
    "max_image_size": (800, 800),       # 最大图片尺寸
    "use_vision_model": True,           # 使用视觉模型
}
```

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────┐
│              应用层 (rag/app/mineru.py)    │
│  • 文档分块 (chunking)                     │
│  • 标记化 (tokenization)                   │
│  • 合并策略 (merging)                      │
│  • 上下文构建                              │
└─────────────────────────────────────────┘
                        ↕
┌─────────────────────────────────────────┐
│        解析器层 (deepdoc/parser/mineru)    │
│  • HTTP API 调用                         │
│  • 响应格式转换                            │
│  • 图片处理                               │
│  • 回退机制                               │
└─────────────────────────────────────────┘
                        ↕
┌─────────────────────────────────────────┐
│           MinerU HTTP API               │
│  • /file_parse 端点                     │
│  • 真实的模型推理                         │
│  • 多格式输出                            │
└─────────────────────────────────────────┘
```

### 图片处理架构

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   MinerU API    │───→│   图片解码模块    │───→│   描述生成模块    │
│  (Base64图片)    │    │  • Base64解码     │    │  • 规则描述       │
│                 │    │  • 格式转换       │    │  • 视觉模型       │
└──────────────────┘    │  • 尺寸调整       │    │  • 内容分析       │
                       └──────────────────┘    └──────────────────┘
                                ↓
                       ┌──────────────────┐
                       │   内容集成模块    │
                       │  • 文档结构分析   │
                       │  • 上下文关联     │
                       │  • 段落组织       │
                       └──────────────────┘
```

## 真实 API 集成

### 端点信息
- **URL**: `http://host:port/file_parse`
- **方法**: POST (multipart/form-data)
- **超时**: 600秒（可配置）

### 请求参数
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `file` | File | 必需 | PDF文件 |
| `parse_method` | String | "auto" | 解析方法: auto/ocr/txt |
| `return_layout` | Boolean | false | 返回布局信息 |
| `return_info` | Boolean | false | 返回中间信息 |
| `return_content_list` | Boolean | true | 返回结构化内容 |
| `return_images` | Boolean | true | 返回图片数据 |
| `is_json_md_dump` | Boolean | false | 是否保存文件 |
| `output_dir` | String | "output" | 输出目录 |

### 响应格式
```json
{
  "md_content": "markdown文本内容",
  "layout": {...},           // 布局信息 (可选)
  "info": {...},            // 中间处理信息 (可选)
  "content_list": [...],    // 结构化内容列表 (可选)
  "images": {              // 图片数据 (可选)
    "page_1.jpg": "data:image/jpeg;base64,xxx",
    "figure_2.png": "data:image/png;base64,yyy"
  }
}
```

## 使用方法

### 基础使用

```python
from deepdoc.parser.mineru_http_parser import MinerUHttpParser

# 基础配置
config = {
    "endpoint": "http://172.19.0.3:8081/file_parse",
    "enable_mineru": True
}

parser = MinerUHttpParser(mineru_config=config)
sections, tables = parser("document.pdf")
```

### 图片处理增强

```python
# 启用图片处理
config_with_images = {
    "endpoint": "http://172.19.0.3:8081/file_parse",
    "return_images": True,
    "process_images": True,
    "generate_image_descriptions": True,
    "max_image_size": (800, 800),
    "use_vision_model": True,
    "enable_mineru": True
}

parser = MinerUHttpParser(mineru_config=config_with_images)
sections, tables = parser("document_with_images.pdf")

# sections 现在包含图片描述文本
# 例如：("高分辨率横向图表（1200×600像素）", "")
```

### 应用层集成

```python
from rag.app.mineru import chunk

# 使用应用层接口
result = chunk(
    filename="document.pdf",
    parser_config={
        "chunk_token_num": 128,
        "mineru_config": {
            "endpoint": "http://172.19.0.3:8081/file_parse",
            "process_images": True,
            "generate_image_descriptions": True
        }
    }
)
```

## 配置参数详解

### MinerU API 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `endpoint` | str | 必需 | MinerU API 地址 |
| `timeout` | int | 600 | 请求超时时间(秒) |
| `parse_method` | str | "auto" | 解析模式: auto/ocr/txt |
| `return_layout` | bool | false | 返回布局推理结果 |
| `return_info` | bool | false | 返回中间处理信息 |
| `return_content_list` | bool | true | 返回结构化内容列表 |
| `return_images` | bool | true | 返回图片Base64数据 |

### 图片处理参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `process_images` | bool | true | 是否处理图片 |
| `generate_image_descriptions` | bool | true | 是否生成图片描述 |
| `max_image_size` | tuple | (800, 800) | 最大图片尺寸(宽,高) |
| `use_vision_model` | bool | true | 是否使用视觉模型 |

### 控制参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_mineru` | bool | true | 是否启用MinerU |
| `fallback_to_plain` | bool | true | 失败时是否回退 |

## 性能优化

### 图片处理优化

1. **智能尺寸调整**
   ```python
   # 大图片自动压缩，保持比例
   if image.width > max_width or image.height > max_height:
       image = resize_keep_ratio(image, max_size)
   ```

2. **批量处理**
   ```python
   # 并行处理多张图片
   for i, (filename, base64_data) in enumerate(images_data.items()):
       process_image_async(filename, base64_data)
   ```

3. **内存管理**
   ```python
   # 及时释放图片内存
   try:
       image = process_image(data)
       description = generate_description(image)
   finally:
       del image  # 释放内存
   ```

### API 调用优化

1. **连接复用**: 使用 Session 复用 HTTP 连接
2. **超时控制**: 根据文档大小动态调整超时时间
3. **重试机制**: 网络异常时的指数退避重试

## 错误处理

### 分层错误处理

```python
try:
    # MinerU API 调用
    response = requests.post(endpoint, ...)
except requests.RequestException:
    # 网络层错误 → 回退
    return fallback_parser(filename)
except json.JSONDecodeError:
    # 响应解析错误 → 回退
    return fallback_parser(filename)
except Exception as e:
    # 其他错误 → 记录并回退
    logger.error(f"MinerU parsing failed: {e}")
    return fallback_parser(filename)
```

### 图片处理错误

```python
def process_image_safe(base64_data, filename):
    try:
        image = decode_base64_image(base64_data)
        description = generate_description(image)
        return {"image": image, "description": description}
    except Exception as e:
        logger.warning(f"Image processing failed for {filename}: {e}")
        return {"description": f"图片: {filename} (处理失败)"}
```

## 回退机制

### 三级回退策略

1. **Level 1**: MinerU HTTP API
2. **Level 2**: RAGFlow DeepDOC 解析器
3. **Level 3**: 简单文本解析器

```python
def parse_with_fallback(filename):
    try:
        return mineru_parse(filename)
    except MinerUException:
        try:
            return deepdoc_parse(filename)
        except DeepDOCException:
            return plain_text_parse(filename)
```

## 测试与验证

### 功能测试

```bash
# 运行基础测试
python examples/mineru_standalone_example.py

# 运行图片处理测试
python examples/mineru_image_processing_example.py

# 运行配置测试
python examples/mineru_config_example.py
```

### 性能测试

```python
import time

def benchmark_parsing(files, config):
    results = []
    for file in files:
        start = time.time()
        sections, tables = parser(file)
        duration = time.time() - start
        results.append({
            "file": file,
            "duration": duration,
            "sections": len(sections),
            "tables": len(tables)
        })
    return results
```

## 未来扩展

### 计划功能

1. **🔮 高级视觉模型**
   - 集成 GPT-4V 等先进视觉模型
   - 支持图表内容的详细分析
   - 表格和图形的结构化提取

2. **📈 性能优化**
   - 异步图片处理
   - 智能缓存机制
   - 批量文档处理

3. **🎯 精准关联**
   - 图片与文本的语义关联
   - 基于位置的上下文分析
   - 跨页面内容关联

4. **🛠️ 开发工具**
   - 可视化调试界面
   - 性能分析工具
   - 配置向导

### 扩展接口

```python
class AdvancedMinerUParser(MinerUHttpParser):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vision_model = kwargs.get('vision_model')
        self.semantic_analyzer = kwargs.get('semantic_analyzer')

    def process_with_semantics(self, filename):
        # 语义增强处理
        pass

    def extract_structured_data(self, filename):
        # 结构化数据提取
        pass
```

## 最佳实践

### 配置建议

1. **生产环境**
   ```python
   production_config = {
       "endpoint": "http://mineru-service:8081/file_parse",
       "timeout": 900,
       "parse_method": "auto",
       "process_images": True,
       "max_image_size": (1024, 1024),
       "use_vision_model": True,
       "enable_mineru": True
   }
   ```

2. **开发环境**
   ```python
   dev_config = {
       "endpoint": "http://localhost:8081/file_parse",
       "timeout": 300,
       "parse_method": "auto",
       "process_images": False,  # 开发时可禁用加速测试
       "enable_mineru": True
   }
   ```

### 监控指标

- **成功率**: MinerU 解析成功率
- **回退率**: 回退到原生解析器的比例
- **处理时间**: 平均文档处理时间
- **图片处理**: 图片处理成功率和耗时
- **错误类型**: 各类错误的分布

## 贡献指南

### 代码结构

```
deepdoc/parser/
├── mineru_http_parser.py     # 核心解析器
├── README_mineru_design.md   # 设计文档
└── __init__.py

rag/app/
├── mineru.py                 # 应用层接口
└── ...

examples/
├── mineru_standalone_example.py        # 基础示例
├── mineru_image_processing_example.py  # 图片处理示例
├── mineru_config_example.py           # 配置示例
└── ...
```

### 提交规范

- 遵循现有代码风格
- 添加适当的错误处理
- 包含相应的测试用例
- 更新相关文档

---

**版本**: v2.0.0
**更新日期**: 2025-06-10
**作者**: 社恐患者杨老师
