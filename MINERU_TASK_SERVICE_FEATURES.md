# MinerU 任务服务集成功能

## 概述

`task_service.py` 已成功集成 MinerU 解析器支持，提供了完整的 PDF → Markdown → RAGFlow 处理流程的任务管理功能。

## 新增功能

### 1. MinerU 任务创建 (`queue_tasks`)

**特点：**
- 📄 专门针对 PDF 文件的验证和处理
- 🔍 MinerU 服务可用性检查
- 📊 智能文件大小评估和任务优化
- 🔄 自动回退机制支持
- ⚡ 单任务处理整个文档（不分页）

**处理逻辑：**
```python
elif doc["parser_id"] == "mineru":
    # 1. 文件类型验证
    # 2. 服务可用性检查
    # 3. PDF 文件验证
    # 4. 任务元数据设置
    # 5. 优先级调整
```

**任务元数据：**
- `parser_type`: "mineru_markdown"
- `total_pages`: 实际 PDF 页数
- `file_size`: 文件大小（字节）
- `service_available`: 服务状态
- `estimated_time`: "short"/"medium"/"long"
- `timeout_multiplier`: 超时倍数

### 2. 服务可用性检查

**功能：** `_check_mineru_service_availability()`
- ✅ 自动检测 MinerU 服务状态
- 🔧 支持回退机制配置
- 📝 详细的错误信息记录

### 3. 任务优先级智能调整

**策略：**
- 🚀 小文件（<10MB）：提高优先级
- ⚖️ 中等文件（10-50MB）：正常优先级
- 🐌 大文件（>50MB）：降低优先级
- ⚠️ 服务不可用：降低优先级

### 4. MinerU 任务详情查询

**功能：** `TaskService.get_mineru_task_details(task_id)`

**返回信息：**
```python
{
    "id": "任务ID",
    "doc_id": "文档ID",
    "progress": 0.75,
    "is_completed": False,
    "is_running": True,
    "chunk_count": 42,
    "chunk_list": ["chunk1", "chunk2", ...],
    "estimated_remaining_seconds": 120,
    "total_pages": 25,
    "file_size": 5242880
}
```

### 5. 任务统计分析

**功能：** `get_mineru_task_stats(tenant_id=None)`

**统计数据：**
- 📈 任务数量统计（总计/完成/运行中/失败）
- 📄 文档数量和文件大小统计
- 📊 完成率和平均文件大小
- 📋 可读性强的摘要信息

## 配置选项

### MinerU 配置参数

```python
parser_config = {
    "mineru_fallback": True,      # 启用回退机制
    "mineru_config": {            # MinerU 特定配置
        "api_endpoint": "http://172.19.0.3:8081/file_parse",
        "api_timeout": 600,
        "parse_method": "auto",
        "return_content_list": True,
        "process_images": True
    }
}
```

### 文件大小阈值

- **小文件**: < 10MB (优先处理)
- **中等文件**: 10MB - 50MB (正常处理)
- **大文件**: > 50MB (降低优先级)

## 使用示例

### 创建 MinerU 任务

```python
from api.db.services.task_service import queue_tasks

doc = {
    "id": "doc123",
    "parser_id": "mineru",
    "type": "pdf",
    "name": "document.pdf",
    "size": 15728640,  # 15MB
    "parser_config": {
        "mineru_fallback": True,
        "mineru_config": {
            "process_images": True,
            "return_content_list": True
        }
    }
}

queue_tasks(doc, "bucket_name", "document.pdf", priority=0)
```

### 查询任务详情

```python
from api.db.services.task_service import TaskService

# 获取 MinerU 任务详情
task_details = TaskService.get_mineru_task_details("task_id_123")
if task_details:
    print(f"任务进度: {task_details['progress']:.1%}")
    print(f"生成块数: {task_details['chunk_count']}")
```

### 获取统计信息

```python
from api.db.services.task_service import get_mineru_task_stats

# 获取全局统计
stats = get_mineru_task_stats()
print(stats["summary"])

# 获取特定租户统计
tenant_stats = get_mineru_task_stats("tenant_123")
```

## 与原有系统的兼容性

### 完全兼容的接口
- ✅ `queue_tasks()` 函数接口保持不变
- ✅ 任务数据库模型保持兼容
- ✅ 进度更新机制保持一致
- ✅ 块重用优化机制正常工作

### 新增的 MinerU 特定功能
- 🆕 服务可用性检查
- 🆕 智能优先级调整
- 🆕 任务详情查询
- 🆕 统计分析功能

## 错误处理和回退机制

### 1. 文件验证失败
```python
# 自动抛出详细错误信息
raise ValueError(f"PDF 文件验证失败: {str(e)}")
```

### 2. 服务不可用
```python
# 根据配置决定回退或失败
if fallback_enabled:
    logger.warning("MinerU 服务不可用，将回退到标准解析器")
else:
    raise RuntimeError("MinerU 服务不可用且未启用回退机制")
```

### 3. 任务执行失败
- 🔄 自动重试机制（最多3次）
- 📝 详细的错误日志记录
- 🔧 可配置的回退策略

## 性能优化

### 1. 任务优先级管理
- 小文件优先处理，提高整体吞吐量
- 大文件降低优先级，避免阻塞队列

### 2. 服务状态缓存
- 避免频繁的服务可用性检查
- 智能的回退决策

### 3. 块重用机制
- 完全兼容原有的块重用优化
- 基于配置摘要的智能匹配

## 监控和调试

### 日志记录
- 🔍 详细的处理步骤记录
- ⚠️ 服务状态变化警告
- 📊 性能指标记录

### 统计监控
- 📈 实时任务状态统计
- 📊 处理性能分析
- 🎯 成功率监控

## 未来扩展

### 可能的改进方向
1. **动态负载均衡**: 根据服务负载自动调整任务分发
2. **批量处理优化**: 支持多文档批量提交到 MinerU
3. **智能重试策略**: 基于错误类型的差异化重试
4. **性能预测**: 基于历史数据预测处理时间
5. **资源监控**: 集成系统资源监控和自动调节

这个集成为 RAGFlow 提供了强大的 MinerU 支持，同时保持了系统的稳定性和可扩展性。
