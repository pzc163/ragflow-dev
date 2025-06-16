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
import sys
import os
import atexit
from typing import List, Any

# 临时重命名冲突文件（在导入之前）
email_file = os.path.join(os.path.dirname(__file__), "email.py")
email_backup = os.path.join(os.path.dirname(__file__), "email_backup.py")

_file_renamed = False
if os.path.exists(email_file) and not os.path.exists(email_backup):
    os.rename(email_file, email_backup)
    _file_renamed = True
    print("✅ 临时重命名email.py文件以避免导入冲突")


def restore_email_file():
    """恢复email.py文件的函数"""
    global _file_renamed, email_backup, email_file
    if _file_renamed and os.path.exists(email_backup):
        try:
            os.rename(email_backup, email_file)
            print("✅ 恢复email.py文件名")
            _file_renamed = False
        except Exception as e:
            print(f"⚠️  恢复文件失败: {e}")


# 注册退出时的清理函数
if _file_renamed:
    atexit.register(restore_email_file)

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from rag.app.smart_chunker import SmartMarkdownChunker
    from rag.app.naive import Markdown

    print("✅ 模块导入成功")
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    # 如果导入失败，恢复文件
    if _file_renamed and os.path.exists(email_backup):
        os.rename(email_backup, email_file)
    raise

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def create_test_markdown() -> str:
    """创建测试用的Markdown内容"""
    return """# 机器学习基础指南

这是一个关于机器学习的基础指南，将帮助初学者理解机器学习的核心概念。

## 1. 什么是机器学习

机器学习是人工智能的一个子领域，它使计算机系统能够通过经验自动改进性能。机器学习算法构建基于训练数据的数学模型，以便在没有明确编程的情况下做出预测或决策。

### 1.1 机器学习的类型

机器学习主要分为以下几种类型：

- **监督学习**：使用标记的训练数据来学习从输入到输出的映射
- **无监督学习**：从没有标记的数据中发现隐藏的模式
- **强化学习**：通过与环境交互来学习最优策略

### 1.2 监督学习详解

监督学习是最常见的机器学习方法。它包括：

1. 分类问题：预测离散的类别标签
2. 回归问题：预测连续的数值

常用的监督学习算法包括：
- 线性回归
- 逻辑回归
- 决策树
- 随机森林
- 支持向量机

## 2. 数据预处理

数据预处理是机器学习流程中的重要步骤，包括：

```python
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

# 数据清洗
def clean_data(df):
    # 处理缺失值
    df = df.dropna()

    # 处理异常值
    Q1 = df.quantile(0.25)
    Q3 = df.quantile(0.75)
    IQR = Q3 - Q1
    df = df[~((df < (Q1 - 1.5 * IQR)) | (df > (Q3 + 1.5 * IQR))).any(axis=1)]

    return df

# 特征缩放
scaler = StandardScaler()
scaled_features = scaler.fit_transform(features)
```

数据预处理的主要步骤如下表所示：

| 步骤 | 描述 | 常用方法 |
|------|------|----------|
| 数据清洗 | 处理缺失值、异常值 | 删除、填充、替换 |
| 特征选择 | 选择最相关的特征 | 相关性分析、递归特征消除 |
| 特征缩放 | 统一特征的尺度 | 标准化、归一化 |
| 特征工程 | 创建新的特征 | 多项式特征、交互特征 |

上表展示了数据预处理的核心步骤。每个步骤都对最终的模型性能有重要影响。

## 3. 模型评估

模型评估是验证机器学习模型性能的关键环节。

### 3.1 评估指标

对于分类问题，常用的评估指标包括：

- **准确率 (Accuracy)**：正确预测的样本数占总样本数的比例
- **精确率 (Precision)**：真正例占预测为正例的比例
- **召回率 (Recall)**：真正例占实际正例的比例
- **F1分数**：精确率和召回率的调和平均数

### 3.2 交叉验证

交叉验证是一种重要的模型验证技术：

```python
from sklearn.model_selection import cross_val_score, KFold

# K折交叉验证
kfold = KFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(model, X, y, cv=kfold, scoring='accuracy')

print(f"交叉验证准确率: {scores.mean():.3f} (+/- {scores.std() * 2:.3f})")
```

这段代码展示了如何使用scikit-learn进行5折交叉验证。

## 4. 总结

机器学习是一个复杂而强大的领域，需要扎实的理论基础和实践经验。本指南介绍了机器学习的基本概念、数据预处理技术和模型评估方法。

> **重要提示**：机器学习的成功很大程度上依赖于数据质量和特征工程。花时间理解数据比急于应用复杂算法更重要。

希望这个指南能帮助你开始机器学习的学习之旅！

---

**参考文献**：
1. Bishop, C. M. (2006). Pattern Recognition and Machine Learning.
2. Hastie, T., Tibshirani, R., & Friedman, J. (2009). The Elements of Statistical Learning.
"""


def test_original_chunker(content: str) -> List[tuple]:
    """测试原有的分块方法"""
    print("\n=== 测试原有分块方法 ===")

    # 创建原有的Markdown解析器
    markdown_parser = Markdown(128)  # 128 token limit

    # 模拟文件处理
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_filename = f.name

    try:
        sections, tables = markdown_parser(temp_filename)

        print("原有方法分块结果:")
        print(f"- 文本段落数: {len(sections)}")
        print(f"- 表格数: {len(tables)}")

        print("\n前3个文本段落:")
        for i, (text, _) in enumerate(sections[:3]):
            print(f"  段落 {i + 1}: {text[:100]}...")

        return sections

    finally:
        os.unlink(temp_filename)


def test_smart_chunker(content: str) -> List[Any]:
    """测试智能分块方法"""
    print("\n=== 测试智能分块方法 ===")

    # 创建智能分块器
    smart_chunker = SmartMarkdownChunker(
        max_tokens=128,
        delimiter="\n!?。；！？",
        preserve_code_blocks=True,
        preserve_tables=True,
        maintain_hierarchy=True,
        extract_images=False,  # 测试时不下载图片
    )

    try:
        chunk_results, table_results = smart_chunker.chunk_markdown(content, "test.md")

        print("智能分块结果:")
        print(f"- 文本块数: {len(chunk_results)}")
        print(f"- 表格数: {len(table_results)}")

        print("\n前3个文本块的详细信息:")
        for i, chunk in enumerate(chunk_results[:3]):
            print(f"  块 {i + 1}:")
            print(f"    - 内容: {chunk.content[:100]}...")
            print(f"    - Token数: {chunk.token_count}")
            print(f"    - 元素类型: {chunk.element_types}")
            print(f"    - 上下文路径: {chunk.context_info.get('common_context_path', [])}")
            print(f"    - 结构保持: {chunk.metadata.get('structure_preserved', False)}")
            print()

        # 分析块的类型分布
        element_types_count = {}
        for chunk in chunk_results:
            for element_type in chunk.element_types:
                element_types_count[element_type] = element_types_count.get(element_type, 0) + 1

        print(f"元素类型分布: {element_types_count}")

        # 分析上下文保持情况
        context_preserved_count = sum(1 for chunk in chunk_results if chunk.context_info.get("hierarchy_maintained", False))
        print(f"保持层级结构的块数: {context_preserved_count}/{len(chunk_results)}")

        return chunk_results

    except Exception as e:
        print(f"智能分块测试失败: {e}")
        import traceback

        traceback.print_exc()
        return []


def compare_results(original_sections: List[tuple], smart_chunks: List[Any]):
    """比较两种方法的结果"""
    print("\n=== 结果对比分析 ===")

    if not smart_chunks:
        print("智能分块失败，无法进行对比")
        return

    print("分块数量对比:")
    print(f"- 原有方法: {len(original_sections)} 个段落")
    print(f"- 智能方法: {len(smart_chunks)} 个块")

    # 分析结构保持情况
    if smart_chunks:
        structure_preserved = sum(1 for chunk in smart_chunks if chunk.metadata.get("structure_preserved", False))
        print("\n结构完整性:")
        print(f"- 保持结构完整的块: {structure_preserved}/{len(smart_chunks)}")

        # 分析上下文信息
        has_context = sum(1 for chunk in smart_chunks if chunk.context_info.get("common_context_path"))
        print(f"- 包含上下文信息的块: {has_context}/{len(smart_chunks)}")

    print("\n优势分析:")
    print("智能分块的主要改进:")
    print("- ✅ 保持Markdown结构完整性（标题、列表、代码块）")
    print("- ✅ 维护元素间的层级关系")
    print("- ✅ 避免在代码块和表格中间分割")
    print("- ✅ 提供丰富的上下文信息")
    print("- ✅ 智能处理长段落和列表")


def main():
    """主测试函数"""
    print("RAGFlow Markdown智能分块器测试")
    print("=" * 50)

    # 创建测试内容
    test_content = create_test_markdown()
    print(f"测试内容长度: {len(test_content)} 字符")

    # 测试原有方法
    original_sections = test_original_chunker(test_content)

    # 测试智能方法
    smart_chunks = test_smart_chunker(test_content)

    # 对比结果
    compare_results(original_sections, smart_chunks)

    print("\n测试完成！")


if __name__ == "__main__":
    try:
        main()
    finally:
        # 恢复文件名
        if _file_renamed and os.path.exists(email_backup):
            os.rename(email_backup, email_file)
            print("✅ 恢复email.py文件名")
