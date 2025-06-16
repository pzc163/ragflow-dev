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

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


from rag.utils import num_tokens_from_string


class ElementType(Enum):
    """文档元素类型枚举"""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE_BLOCK = "code_block"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    BLOCKQUOTE = "blockquote"
    HORIZONTAL_RULE = "horizontal_rule"
    TEXT = "text"


@dataclass
class DocumentElement:
    """文档元素基类"""

    element_type: ElementType
    content: str
    metadata: Dict[str, Any]
    token_count: int
    line_start: int
    line_end: int

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = num_tokens_from_string(self.content)


@dataclass
class HeadingElement(DocumentElement):
    """标题元素"""

    level: int
    title: str

    def __post_init__(self):
        super().__post_init__()
        self.element_type = ElementType.HEADING


@dataclass
class CodeBlockElement(DocumentElement):
    """代码块元素"""

    language: Optional[str]

    def __post_init__(self):
        super().__post_init__()
        self.element_type = ElementType.CODE_BLOCK


@dataclass
class ListElement(DocumentElement):
    """列表元素"""

    list_type: str  # "ordered" or "unordered"
    items: List[str]

    def __post_init__(self):
        super().__post_init__()
        self.element_type = ElementType.LIST


@dataclass
class TableElement(DocumentElement):
    """表格元素"""

    headers: List[str]
    rows: List[List[str]]

    def __post_init__(self):
        super().__post_init__()
        self.element_type = ElementType.TABLE


class MarkdownStructureAnalyzer:
    """Markdown结构分析器"""

    def __init__(self):
        # 标题模式
        self.heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        # 代码块模式
        self.code_block_pattern = re.compile(r"^```(\w+)?\n(.*?)^```$", re.MULTILINE | re.DOTALL)
        # 列表模式
        self.unordered_list_pattern = re.compile(r"^(\s*)[-*+]\s+(.+)$", re.MULTILINE)
        self.ordered_list_pattern = re.compile(r"^(\s*)(\d+)\.\s+(.+)$", re.MULTILINE)
        # 表格模式 (简化版，完整版在后面实现)
        self.table_pattern = re.compile(r"^\|.*\|$", re.MULTILINE)
        # 图片模式
        self.image_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")
        # 引用模式
        self.blockquote_pattern = re.compile(r"^>\s+(.+)$", re.MULTILINE)
        # 水平线模式
        self.horizontal_rule_pattern = re.compile(r"^(-{3,}|\*{3,}|_{3,})$", re.MULTILINE)

    def analyze(self, content: str) -> List[DocumentElement]:
        """分析Markdown内容，返回结构化元素列表"""
        lines = content.split("\n")
        elements = []
        i = 0

        while i < len(lines):
            element, lines_consumed = self._parse_line(lines, i)
            if element:
                elements.append(element)
            i += lines_consumed

        return elements

    def _parse_line(self, lines: List[str], start_index: int) -> Tuple[Optional[DocumentElement], int]:
        """解析单行，返回元素和消耗的行数"""
        line = lines[start_index]

        # 1. 检查标题
        heading_match = self.heading_pattern.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            return HeadingElement(
                element_type=ElementType.HEADING, content=line, metadata={"level": level, "title": title}, token_count=0, line_start=start_index, line_end=start_index, level=level, title=title
            ), 1

        # 2. 检查代码块
        if line.strip().startswith("```"):
            return self._parse_code_block(lines, start_index)

        # 3. 检查列表
        if self.unordered_list_pattern.match(line) or self.ordered_list_pattern.match(line):
            return self._parse_list(lines, start_index)

        # 4. 检查表格
        if self.table_pattern.match(line):
            return self._parse_table(lines, start_index)

        # 5. 检查引用
        if self.blockquote_pattern.match(line):
            return self._parse_blockquote(lines, start_index)

        # 6. 检查水平线
        if self.horizontal_rule_pattern.match(line.strip()):
            return DocumentElement(element_type=ElementType.HORIZONTAL_RULE, content=line, metadata={}, token_count=0, line_start=start_index, line_end=start_index), 1

        # 7. 默认作为段落处理
        return self._parse_paragraph(lines, start_index)

    def _parse_code_block(self, lines: List[str], start_index: int) -> Tuple[Optional[CodeBlockElement], int]:
        """解析代码块"""
        start_line = lines[start_index]
        language_match = re.match(r"^```(\w+)?", start_line.strip())
        language = language_match.group(1) if language_match else None

        content_lines = [start_line]
        i = start_index + 1

        while i < len(lines):
            line = lines[i]
            content_lines.append(line)
            if line.strip() == "```":
                break
            i += 1

        content = "\n".join(content_lines)
        return CodeBlockElement(
            element_type=ElementType.CODE_BLOCK, content=content, metadata={"language": language}, token_count=0, line_start=start_index, line_end=i, language=language
        ), i - start_index + 1

    def _parse_list(self, lines: List[str], start_index: int) -> Tuple[Optional[ListElement], int]:
        """解析列表"""
        list_lines = []
        items = []
        i = start_index

        # 确定列表类型
        first_line = lines[start_index]
        is_ordered = bool(self.ordered_list_pattern.match(first_line))
        list_type = "ordered" if is_ordered else "unordered"

        # 收集列表项
        current_indent = None
        while i < len(lines):
            line = lines[i]

            # 检查是否是列表项
            if is_ordered:
                match = self.ordered_list_pattern.match(line)
            else:
                match = self.unordered_list_pattern.match(line)

            if match:
                indent = len(match.group(1)) if match.group(1) else 0
                if current_indent is None:
                    current_indent = indent
                elif indent != current_indent:
                    # 不同缩进级别，结束当前列表
                    break

                item_text = match.group(3) if is_ordered else match.group(2)
                items.append(item_text.strip())
                list_lines.append(line)
            elif line.strip() == "":
                # 空行，继续
                list_lines.append(line)
            else:
                # 非列表行，结束列表
                break

            i += 1

        content = "\n".join(list_lines)
        return ListElement(
            element_type=ElementType.LIST, content=content, metadata={"list_type": list_type, "items": items}, token_count=0, line_start=start_index, line_end=i - 1, list_type=list_type, items=items
        ), i - start_index

    def _parse_table(self, lines: List[str], start_index: int) -> Tuple[Optional[TableElement], int]:
        """解析表格"""
        table_lines = []
        i = start_index

        # 收集所有表格行
        while i < len(lines) and self.table_pattern.match(lines[i]):
            table_lines.append(lines[i])
            i += 1

        if len(table_lines) < 2:  # 至少需要标题行和分隔行
            return None, 1

        # 解析表格结构
        headers = [cell.strip() for cell in table_lines[0].split("|")[1:-1]]
        rows = []

        for line in table_lines[2:]:  # 跳过分隔行
            row = [cell.strip() for cell in line.split("|")[1:-1]]
            rows.append(row)

        content = "\n".join(table_lines)
        return TableElement(
            element_type=ElementType.TABLE, content=content, metadata={"headers": headers, "rows": rows}, token_count=0, line_start=start_index, line_end=i - 1, headers=headers, rows=rows
        ), i - start_index

    def _parse_blockquote(self, lines: List[str], start_index: int) -> Tuple[Optional[DocumentElement], int]:
        """解析引用块"""
        quote_lines = []
        i = start_index

        while i < len(lines) and self.blockquote_pattern.match(lines[i]):
            quote_lines.append(lines[i])
            i += 1

        content = "\n".join(quote_lines)
        return DocumentElement(element_type=ElementType.BLOCKQUOTE, content=content, metadata={}, token_count=0, line_start=start_index, line_end=i - 1), i - start_index

    def _parse_paragraph(self, lines: List[str], start_index: int) -> Tuple[Optional[DocumentElement], int]:
        """解析段落"""
        if not lines[start_index].strip():
            return None, 1  # 跳过空行

        paragraph_lines = []
        i = start_index

        while i < len(lines):
            line = lines[i]

            # 遇到空行或特殊结构时停止
            if (
                line.strip() == ""
                or self.heading_pattern.match(line)
                or line.strip().startswith("```")
                or self.unordered_list_pattern.match(line)
                or self.ordered_list_pattern.match(line)
                or self.table_pattern.match(line)
                or self.blockquote_pattern.match(line)
                or self.horizontal_rule_pattern.match(line.strip())
            ):
                break

            paragraph_lines.append(line)
            i += 1

        if not paragraph_lines:
            return None, 1

        content = "\n".join(paragraph_lines)
        return DocumentElement(element_type=ElementType.PARAGRAPH, content=content, metadata={}, token_count=0, line_start=start_index, line_end=i - 1), i - start_index


class SemanticMarkdownChunker:
    """语义感知的Markdown分块器"""

    def __init__(self, max_tokens: int = 128, delimiter: str = "\n!?。；！？"):
        self.max_tokens = max_tokens
        self.delimiter = delimiter
        self.analyzer = MarkdownStructureAnalyzer()

    def chunk(self, content: str) -> List[Dict[str, Any]]:
        """对Markdown内容进行语义分块"""
        # 1. 结构分析
        elements = self.analyzer.analyze(content)

        # 2. 智能分块
        chunks = self._create_semantic_chunks(elements)

        return chunks

    def _create_semantic_chunks(self, elements: List[DocumentElement]) -> List[Dict[str, Any]]:
        """创建语义分块"""
        chunks = []
        current_chunk = []
        current_tokens = 0

        for element in elements:
            # 检查元素是否可以分割
            if self._is_splittable(element):
                # 可分割元素的处理
                if current_tokens + element.token_count <= self.max_tokens:
                    # 可以添加到当前块
                    current_chunk.append(element)
                    current_tokens += element.token_count
                else:
                    # 需要创建新块
                    if current_chunk:
                        chunks.append(self._finalize_chunk(current_chunk))
                    current_chunk = [element]
                    current_tokens = element.token_count
            else:
                # 不可分割元素的处理
                if current_chunk:
                    chunks.append(self._finalize_chunk(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # 处理超大不可分割元素
                if element.token_count > self.max_tokens:
                    sub_chunks = self._split_large_element(element)
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(self._finalize_chunk([element]))

        # 处理最后的块
        if current_chunk:
            chunks.append(self._finalize_chunk(current_chunk))

        return chunks

    def _is_splittable(self, element: DocumentElement) -> bool:
        """判断元素是否可以分割"""
        # 代码块、表格不能分割
        if element.element_type in [ElementType.CODE_BLOCK, ElementType.TABLE]:
            return False

        # 短列表不分割
        if element.element_type == ElementType.LIST and element.token_count < self.max_tokens * 0.8:
            return False

        return True

    def _split_large_element(self, element: DocumentElement) -> List[Dict[str, Any]]:
        """分割超大元素"""
        if element.element_type == ElementType.PARAGRAPH:
            return self._split_paragraph(element)
        elif element.element_type == ElementType.LIST:
            return self._split_list(element)
        else:
            # 其他类型强制分割
            return [self._finalize_chunk([element])]

    def _split_paragraph(self, element: DocumentElement) -> List[Dict[str, Any]]:
        """分割长段落"""
        # 使用分隔符分割
        sentences = re.split(f"[{self.delimiter}]", element.content)
        chunks = []
        current_text = ""
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = num_tokens_from_string(sentence)

            if current_tokens + sentence_tokens <= self.max_tokens:
                current_text += sentence + " "
                current_tokens += sentence_tokens
            else:
                if current_text:
                    chunk_element = DocumentElement(
                        element_type=ElementType.PARAGRAPH,
                        content=current_text.strip(),
                        metadata=element.metadata.copy(),
                        token_count=current_tokens,
                        line_start=element.line_start,
                        line_end=element.line_end,
                    )
                    chunks.append(self._finalize_chunk([chunk_element]))

                current_text = sentence + " "
                current_tokens = sentence_tokens

        if current_text:
            chunk_element = DocumentElement(
                element_type=ElementType.PARAGRAPH, content=current_text.strip(), metadata=element.metadata.copy(), token_count=current_tokens, line_start=element.line_start, line_end=element.line_end
            )
            chunks.append(self._finalize_chunk([chunk_element]))

        return chunks

    def _split_list(self, element: ListElement) -> List[Dict[str, Any]]:
        """分割长列表"""
        chunks = []
        current_items = []
        current_tokens = 0

        for item in element.items:
            item_tokens = num_tokens_from_string(item)

            if current_tokens + item_tokens <= self.max_tokens:
                current_items.append(item)
                current_tokens += item_tokens
            else:
                if current_items:
                    chunk_element = ListElement(
                        element_type=ElementType.LIST,
                        content=self._recreate_list_content(current_items, element.list_type),
                        metadata=element.metadata.copy(),
                        token_count=current_tokens,
                        line_start=element.line_start,
                        line_end=element.line_end,
                        list_type=element.list_type,
                        items=current_items,
                    )
                    chunks.append(self._finalize_chunk([chunk_element]))

                current_items = [item]
                current_tokens = item_tokens

        if current_items:
            chunk_element = ListElement(
                element_type=ElementType.LIST,
                content=self._recreate_list_content(current_items, element.list_type),
                metadata=element.metadata.copy(),
                token_count=current_tokens,
                line_start=element.line_start,
                line_end=element.line_end,
                list_type=element.list_type,
                items=current_items,
            )
            chunks.append(self._finalize_chunk([chunk_element]))

        return chunks

    def _recreate_list_content(self, items: List[str], list_type: str) -> str:
        """重新创建列表内容"""
        lines = []
        for i, item in enumerate(items):
            if list_type == "ordered":
                lines.append(f"{i + 1}. {item}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)

    def _finalize_chunk(self, elements: List[DocumentElement]) -> Dict[str, Any]:
        """完成分块，返回标准格式"""
        content_parts = []
        total_tokens = 0
        element_types = []

        for element in elements:
            content_parts.append(element.content)
            total_tokens += element.token_count
            element_types.append(element.element_type.value)

        content = "\n".join(content_parts)

        return {"content": content, "token_count": total_tokens, "element_types": element_types, "metadata": {"elements_count": len(elements), "structure_preserved": True}}
