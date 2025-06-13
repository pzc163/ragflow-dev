# MinerU 项目命名规范

## 概述

为了保持代码的一致性和可维护性，我们已经统一了 MinerU 相关的命名规范。

## 核心命名规范

### 1. 类名和别名

#### 实际类名
```python
# 在 deepdoc/parser/mineru_markdown_parser.py 中
class MinerUMarkdownParser:
    """MinerU Markdown 专用解析器"""
```

#### 标准别名
```python
# 在 deepdoc/parser/__init__.py 中
from .mineru_markdown_parser import MinerUMarkdownParser as MinerUParser

__all__ = [
    "MinerUParser",  # 对外统一使用此名称
    # ... 其他解析器
]
```

#### 使用原则
- **对外接口**：统一使用 `MinerUParser`
- **内部实现**：保持 `MinerUMarkdownParser`
- **导入时**：优先使用 `from deepdoc.parser import MinerUParser`

### 2. 变量命名

#### 解析器实例
```python
# ✅ 推荐用法
mineru_parser = create_mineru_markdown_parser(config)
mineru_parser = MinerUParser(config)

# ❌ 避免使用
markdown_parser = create_mineru_markdown_parser(config)  # 可能与标准 Markdown 解析器混淆
```

#### 函数命名
```python
# ✅ 推荐用法
def get_mineru_parser(config) -> MinerUParser:
    """获取 MinerU 解析器实例"""

def create_mineru_processor(config) -> Dict:
    """创建 MinerU 处理器"""

# ❌ 避免使用
def get_mineru_markdown_parser(config):  # 太长且不一致
```

### 3. 任务和配置命名

#### 任务类型标识
```python
# 在 task_service.py 中
task["parser_type"] = "mineru_markdown"  # 保留，说明底层实现
task["parser_id"] = "mineru"            # 标准标识符
```

#### 配置键名
```python
parser_config = {
    "mineru_config": {...},      # MinerU 专用配置
    "mineru_fallback": True,     # 回退机制配置
    "mineru_endpoint": "...",    # API 端点配置
    "mineru_timeout": 600        # 超时配置
}
```

## 导入规范

### 标准导入方式

#### 1. 基础导入
```python
# 推荐：使用标准别名
from deepdoc.parser import MinerUParser

# 或者：直接导入工厂函数
from deepdoc.parser.mineru_markdown_parser import create_mineru_markdown_parser
```

#### 2. 应用层导入
```python
# 在 rag/app/mineru.py 中
from deepdoc.parser import MinerUParser
from deepdoc.parser.mineru_markdown_parser import create_mineru_markdown_parser
```

#### 3. 服务层导入
```python
# 在 api/db/services/task_service.py 中
from deepdoc.parser import PdfParser, MinerUParser
```

### 避免的导入方式

```python
# ❌ 避免：直接导入内部类名
from deepdoc.parser.mineru_markdown_parser import MinerUMarkdownParser

# ❌ 避免：别名不一致
from deepdoc.parser import MinerUParser as MinerUMarkdownParser
```

## 函数和方法命名

### 公共 API 函数

```python
# ✅ 推荐的函数名
def get_mineru_parser(config=None) -> MinerUParser:
    """获取 MinerU 解析器实例"""

def is_mineru_service_available() -> bool:
    """检查 MinerU 服务可用性"""

def get_mineru_status() -> Dict:
    """获取 MinerU 服务状态"""

def create_mineru_processor(config=None) -> Dict:
    """创建 MinerU 处理器"""
```

### 内部辅助函数

```python
# ✅ 推荐的内部函数名
def _get_mineru_config(parser_config, **kwargs):
    """获取 MinerU 配置"""

def _check_mineru_service_availability():
    """检查 MinerU 服务可用性"""

def _create_dummy_parser():
    """创建虚拟解析器"""
```

## 类型注解规范

### 函数签名
```python
from typing import Optional, Dict, Any, List, Tuple
from deepdoc.parser import MinerUParser

def get_mineru_parser(config: Optional[Dict[str, Any]] = None) -> MinerUParser:
    """类型注解使用标准别名"""

def analyze_markdown_structure(sections: List, mineru_parser: MinerUParser) -> List[int]:
    """参数类型注解保持一致"""
```

### 变量注解
```python
# ✅ 推荐
mineru_parser: MinerUParser = get_mineru_parser(config)
config: Dict[str, Any] = _get_mineru_config(parser_config)

# ❌ 避免
markdown_parser: MinerUMarkdownParser = get_mineru_parser(config)
```

## 文档字符串规范

### 类文档
```python
class MinerUMarkdownParser:
    """
    MinerU Markdown 专用解析器

    专门处理 MinerU API 返回的 Markdown 格式文档
    核心功能：PDF → MinerU API → Markdown → 结构化数据
    """
```

### 函数文档
```python
def get_mineru_parser(config: Optional[Dict[str, Any]] = None) -> MinerUParser:
    """
    获取 MinerU 解析器实例

    Args:
        config: MinerU 配置字典，包含 API 端点、超时等设置

    Returns:
        MinerUParser: 配置好的 MinerU 解析器实例

    Example:
        >>> parser = get_mineru_parser({"api_timeout": 300})
        >>> sections, tables = parser.parse("document.pdf")
    """
```

## 配置规范

### 配置键命名
```python
# ✅ 推荐的配置键名
MINERU_CONFIG_KEYS = {
    "api_endpoint": "MinerU API 端点",
    "api_timeout": "API 超时时间",
    "parse_method": "解析方法",
    "process_images": "是否处理图片",
    "return_content_list": "是否返回内容列表",
    "mineru_fallback": "回退机制开关",
    "enable_debug": "调试模式开关"
}
```

### 配置验证
```python
def validate_mineru_config(config: Dict[str, Any]) -> bool:
    """验证 MinerU 配置的有效性"""
    required_keys = ["api_endpoint"]
    return all(key in config for key in required_keys)
```

## 错误处理规范

### 异常命名
```python
class MinerUConfigError(ValueError):
    """MinerU 配置错误"""

class MinerUServiceError(RuntimeError):
    """MinerU 服务错误"""

class MinerUParsingError(Exception):
    """MinerU 解析错误"""
```

### 错误消息
```python
# ✅ 推荐的错误消息格式
"MinerU 服务不可用，请检查服务状态"
"MinerU API 调用失败: {error_details}"
"MinerU 解析器初始化失败: {config_error}"
```

## 日志规范

### 日志记录器命名
```python
logger = logging.getLogger(__name__)  # 使用模块名

# 或者使用专门的记录器
mineru_logger = logging.getLogger("rag.app.mineru")
```

### 日志消息格式
```python
logger.info("MinerU 解析器初始化完成")
logger.warning("MinerU 服务不可用，将使用回退机制")
logger.error(f"MinerU API 调用失败: {error}")
logger.debug(f"MinerU 配置: {config}")
```

## 总结

通过统一的命名规范，我们确保了：

1. **一致性**: 所有 MinerU 相关代码使用统一的命名约定
2. **清晰性**: 名称含义明确，避免混淆
3. **可维护性**: 代码结构清晰，易于维护和扩展
4. **兼容性**: 与 RAGFlow 现有代码风格保持一致

这些规范应该在所有 MinerU 相关的新代码中严格遵循。
