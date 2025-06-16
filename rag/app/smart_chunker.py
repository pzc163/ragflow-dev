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
import re
import requests
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from functools import reduce
from io import BytesIO

from markdown import markdown
from PIL import Image

from rag.utils import num_tokens_from_string
from rag.nlp import concat_img


@dataclass
class ChunkResult:
    """分块结果类"""

    content: str
    token_count: int
    element_types: List[str]
    context_info: Dict[str, Any]
    images: Optional[List[Image.Image]]
    tables: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class SmartMarkdownChunker:
    """智能Markdown分块器"""

    def __init__(
        self, max_tokens: int = 128, delimiter: str = "\n!?。；！？", preserve_code_blocks: bool = True, preserve_tables: bool = True, maintain_hierarchy: bool = True, extract_images: bool = True
    ):
        """
        初始化智能分块器

        Args:
            max_tokens: 最大token数
            delimiter: 分隔符
            preserve_code_blocks: 是否保持代码块完整性
            preserve_tables: 是否保持表格完整性
            maintain_hierarchy: 是否维护层级结构
            extract_images: 是否提取图片
        """
        self.max_tokens = max_tokens
        self.delimiter = delimiter
        self.preserve_code_blocks = preserve_code_blocks
        self.preserve_tables = preserve_tables
        self.maintain_hierarchy = maintain_hierarchy
        self.extract_images = extract_images

        # 导入需要的类（避免循环导入）
        from .semantic_markdown_chunker import MarkdownStructureAnalyzer, SemanticMarkdownChunker
        from .context_manager import MarkdownContextManager

        # 初始化组件
        self.structure_analyzer = MarkdownStructureAnalyzer()
        self.context_manager = MarkdownContextManager()
        self.semantic_chunker = SemanticMarkdownChunker(max_tokens, delimiter)

        # 图片URL模式
        self.image_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")

    def chunk_markdown(self, content: str, filename: str = "") -> Tuple[List[ChunkResult], List[Dict[str, Any]]]:
        """
        对Markdown内容进行智能分块

        Args:
            content: Markdown内容
            filename: 文件名（可选）

        Returns:
            Tuple[分块结果列表, 表格列表]
        """
        try:
            logging.info(f"开始智能分块: {filename}")

            # 1. 提取表格和剩余内容
            remainder, extracted_tables = self._extract_tables_and_remainder(content)

            # 2. 结构分析
            elements = self.structure_analyzer.analyze(remainder)
            logging.info(f"分析得到 {len(elements)} 个文档元素")

            # 3. 建立上下文关系
            element_ids = []
            for element in elements:
                element_id = self.context_manager.add_element(element)
                element_ids.append(element_id)

            # 4. 提取图片信息
            images_per_element = self._extract_images_for_elements(elements) if self.extract_images else {}

            # 5. 智能分块
            chunks = self._create_smart_chunks(elements, element_ids, images_per_element)

            # 6. 处理表格
            table_chunks = self._process_extracted_tables(extracted_tables)

            logging.info(f"分块完成: {len(chunks)} 个文本块, {len(table_chunks)} 个表格")

            return chunks, table_chunks

        except Exception as e:
            logging.error(f"分块过程中出现错误: {e}")
            # 降级到简单分块
            return self._fallback_chunking(content), []

    def _extract_tables_and_remainder(self, content: str) -> Tuple[str, List[str]]:
        """提取表格和剩余内容"""
        tables = []
        remainder = content

        if "|" in content:
            # 标准Markdown表格
            border_table_pattern = re.compile(r"(?:\n|^)(?:\|.*?\|.*?\|.*?\n)(?:\|(?:\s*[:-]+[-| :]*\s*)\|.*?\n)(?:\|.*?\|.*?\|.*?\n)+", re.VERBOSE)
            border_tables = border_table_pattern.findall(content)
            tables.extend(border_tables)
            remainder = border_table_pattern.sub("", remainder)

            # 无边框Markdown表格
            no_border_table_pattern = re.compile(r"(?:\n|^)(?:\S.*?\|.*?\n)(?:(?:\s*[:-]+[-| :]*\s*).*?\n)(?:\S.*?\|.*?\n)+", re.VERBOSE)
            no_border_tables = no_border_table_pattern.findall(remainder)
            tables.extend(no_border_tables)
            remainder = no_border_table_pattern.sub("", remainder)

        if "<table>" in remainder.lower():
            # HTML表格
            html_table_pattern = re.compile(r"(?:\n|^)\s*(?:<table[^>]*>.*?</table>)\s*(?=\n|$)", re.VERBOSE | re.DOTALL | re.IGNORECASE)
            html_tables = html_table_pattern.findall(remainder)
            tables.extend(html_tables)
            remainder = html_table_pattern.sub("", remainder)

        return remainder, tables

    def _extract_images_for_elements(self, elements) -> Dict[int, List[Image.Image]]:
        """为每个元素提取图片"""
        images_per_element = {}

        for i, element in enumerate(elements):
            images = self._extract_images_from_text(element.content)
            if images:
                images_per_element[i] = images

        return images_per_element

    def _extract_images_from_text(self, text: str) -> List[Image.Image]:
        """从文本中提取图片"""
        images = []
        image_matches = self.image_pattern.findall(text)

        for alt_text, url in image_matches:
            try:
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200 and response.headers.get("Content-Type", "").startswith("image/"):
                    img = Image.open(BytesIO(response.content)).convert("RGB")
                    images.append(img)
            except Exception as e:
                logging.warning(f"无法下载图片 {url}: {e}")
                continue

        return images

    def _create_smart_chunks(self, elements, element_ids: List[str], images_per_element: Dict[int, List[Image.Image]]) -> List[ChunkResult]:
        """创建智能分块"""
        chunks = []
        current_chunk_elements = []
        current_chunk_ids = []
        current_chunk_images = []
        current_tokens = 0

        for i, (element, element_id) in enumerate(zip(elements, element_ids)):
            element_images = images_per_element.get(i, [])

            # 检查是否可以加入当前块
            can_add_to_current = self._can_add_to_chunk(current_chunk_elements, current_chunk_ids, current_tokens, element, element_id, element_images)

            if can_add_to_current:
                # 添加到当前块
                current_chunk_elements.append(element)
                current_chunk_ids.append(element_id)
                current_chunk_images.extend(element_images)
                current_tokens += element.token_count
            else:
                # 完成当前块
                if current_chunk_elements:
                    chunk = self._finalize_smart_chunk(current_chunk_elements, current_chunk_ids, current_chunk_images)
                    chunks.append(chunk)

                # 开始新块
                if self._is_splittable_element(element):
                    # 可分割的大元素
                    sub_chunks = self._split_large_element_smart(element, element_id, element_images)
                    chunks.extend(sub_chunks)

                    # 重置当前块
                    current_chunk_elements = []
                    current_chunk_ids = []
                    current_chunk_images = []
                    current_tokens = 0
                else:
                    # 不可分割元素，开始新块
                    current_chunk_elements = [element]
                    current_chunk_ids = [element_id]
                    current_chunk_images = element_images[:]
                    current_tokens = element.token_count

        # 处理最后的块
        if current_chunk_elements:
            chunk = self._finalize_smart_chunk(current_chunk_elements, current_chunk_ids, current_chunk_images)
            chunks.append(chunk)

        return chunks

    def _can_add_to_chunk(self, current_elements, current_ids: List[str], current_tokens: int, new_element, new_element_id: str, new_images: List[Image.Image]) -> bool:
        """判断是否可以将新元素添加到当前块"""

        # 1. 检查token限制
        if current_tokens + new_element.token_count > self.max_tokens:
            return False

        # 2. 检查结构完整性
        if not self._maintains_structural_integrity(current_ids, new_element_id):
            return False

        # 3. 检查特殊元素的完整性
        if not self._maintains_special_element_integrity(current_elements, new_element):
            return False

        return True

    def _maintains_structural_integrity(self, current_ids: List[str], new_element_id: str) -> bool:
        """检查是否维护了结构完整性"""
        if not self.maintain_hierarchy or not current_ids:
            return True

        # 检查是否应该保持在一起
        last_id = current_ids[-1]
        return self.context_manager.should_keep_together(last_id, new_element_id)

    def _maintains_special_element_integrity(self, current_elements, new_element) -> bool:
        """检查特殊元素的完整性"""
        from .semantic_markdown_chunker import ElementType

        # 1. 代码块完整性检查
        if self.preserve_code_blocks:
            for element in current_elements:
                if element.element_type == ElementType.CODE_BLOCK:
                    # 代码块不能与其他元素混合
                    if new_element.element_type != ElementType.CODE_BLOCK:
                        return False

        # 2. 表格完整性检查
        if self.preserve_tables:
            for element in current_elements:
                if element.element_type == ElementType.TABLE:
                    # 表格优先独立成块，除非是相关说明
                    if not self._is_table_related_content(new_element):
                        return False

        return True

    def _is_table_related_content(self, element) -> bool:
        """判断是否是表格相关内容"""
        from .semantic_markdown_chunker import ElementType

        if element.element_type != ElementType.PARAGRAPH:
            return False

        content = element.content.lower()
        table_keywords = ["表", "table", "如下", "见表", "统计", "上表", "above table", "表中", "如表所示"]
        return any(keyword in content for keyword in table_keywords)

    def _is_splittable_element(self, element) -> bool:
        """判断元素是否可分割"""
        from .semantic_markdown_chunker import ElementType

        # 代码块和表格不可分割
        if element.element_type in [ElementType.CODE_BLOCK, ElementType.TABLE]:
            return False

        # 短内容不分割
        if element.token_count <= self.max_tokens:
            return False

        return True

    def _split_large_element_smart(self, element, element_id: str, images: List[Image.Image]) -> List[ChunkResult]:
        """智能分割大元素"""
        from .semantic_markdown_chunker import ElementType

        if element.element_type == ElementType.PARAGRAPH:
            return self._split_paragraph_smart(element, element_id, images)
        elif element.element_type == ElementType.LIST:
            return self._split_list_smart(element, element_id, images)
        else:
            # 其他类型强制分割
            return [self._create_chunk_result(element, element_id, images)]

    def _split_paragraph_smart(self, element, element_id: str, images: List[Image.Image]) -> List[ChunkResult]:
        """智能分割段落"""
        from .semantic_markdown_chunker import DocumentElement, ElementType

        chunks = []

        # 使用多级分隔符分割
        sentences = self._split_text_smartly(element.content)

        current_text = ""
        current_tokens = 0
        current_images = []

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
                    chunks.append(self._create_chunk_result(chunk_element, element_id, current_images))

                current_text = sentence + " "
                current_tokens = sentence_tokens
                current_images = []

        if current_text:
            chunk_element = DocumentElement(
                element_type=ElementType.PARAGRAPH, content=current_text.strip(), metadata=element.metadata.copy(), token_count=current_tokens, line_start=element.line_start, line_end=element.line_end
            )
            chunks.append(self._create_chunk_result(chunk_element, element_id, current_images))

        return chunks

    def _split_text_smartly(self, text: str) -> List[str]:
        """智能文本分割"""
        # 优先级分隔符
        primary_delimiters = [".", "。", "!", "！", "?", "？"]

        # 先按主要分隔符分割
        parts = []
        current_part = ""

        for char in text:
            current_part += char
            if char in primary_delimiters:
                parts.append(current_part.strip())
                current_part = ""

        if current_part.strip():
            parts.append(current_part.strip())

        # 如果分割后的部分仍然太长，进一步分割
        final_parts = []
        for part in parts:
            if num_tokens_from_string(part) > self.max_tokens * 0.8:
                # 使用次级分隔符
                sub_parts = re.split(f"[{';；:：'}]", part)
                final_parts.extend([p.strip() for p in sub_parts if p.strip()])
            else:
                final_parts.append(part)

        return final_parts

    def _split_list_smart(self, element, element_id: str, images: List[Image.Image]) -> List[ChunkResult]:
        """智能分割列表"""
        from .semantic_markdown_chunker import ListElement

        if not isinstance(element, ListElement):
            return [self._create_chunk_result(element, element_id, images)]

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
                    chunk_element = self._create_list_element(current_items, element.list_type, element)
                    chunks.append(self._create_chunk_result(chunk_element, element_id, []))

                current_items = [item]
                current_tokens = item_tokens

        if current_items:
            chunk_element = self._create_list_element(current_items, element.list_type, element)
            chunks.append(self._create_chunk_result(chunk_element, element_id, images))

        return chunks

    def _create_list_element(self, items: List[str], list_type: str, original_element):
        """创建列表元素"""
        from .semantic_markdown_chunker import ListElement, ElementType

        content_lines = []
        for i, item in enumerate(items):
            if list_type == "ordered":
                content_lines.append(f"{i + 1}. {item}")
            else:
                content_lines.append(f"- {item}")

        content = "\n".join(content_lines)

        return ListElement(
            element_type=ElementType.LIST,
            content=content,
            metadata=original_element.metadata.copy(),
            token_count=num_tokens_from_string(content),
            line_start=original_element.line_start,
            line_end=original_element.line_end,
            list_type=list_type,
            items=items,
        )

    def _finalize_smart_chunk(self, elements, element_ids: List[str], images: List[Image.Image]) -> ChunkResult:
        """完成智能分块"""

        # 合并内容
        content_parts = [element.content for element in elements]
        content = "\n".join(content_parts)

        # 计算token数
        total_tokens = sum(element.token_count for element in elements)

        # 收集元素类型
        element_types = [element.element_type.value for element in elements]

        # 获取上下文信息
        context_info = self.context_manager.get_enhanced_context_for_chunk(element_ids)

        # 处理图片
        combined_images = None
        if images:
            combined_images = [reduce(concat_img, images)] if len(images) > 1 else images

        # 创建结果
        return ChunkResult(
            content=content,
            token_count=total_tokens,
            element_types=element_types,
            context_info=context_info,
            images=combined_images,
            tables=[],
            metadata={"elements_count": len(elements), "chunk_method": "smart_semantic", "structure_preserved": True, "context_enhanced": True},
        )

    def _create_chunk_result(self, element, element_id: str, images: List[Image.Image]) -> ChunkResult:
        """创建单个元素的分块结果"""

        context_info = self.context_manager.get_enhanced_context_for_chunk([element_id])

        combined_images = None
        if images:
            combined_images = [reduce(concat_img, images)] if len(images) > 1 else images

        return ChunkResult(
            content=element.content,
            token_count=element.token_count,
            element_types=[element.element_type.value],
            context_info=context_info,
            images=combined_images,
            tables=[],
            metadata={"elements_count": 1, "chunk_method": "smart_semantic", "element_type": element.element_type.value},
        )

    def _process_extracted_tables(self, extracted_tables: List[str]) -> List[Dict[str, Any]]:
        """处理提取的表格"""
        tables = []

        for table_content in extracted_tables:
            # 转换为HTML格式
            if table_content.strip().startswith("<"):
                # 已经是HTML格式
                html_content = table_content
            else:
                # Markdown表格，转换为HTML
                html_content = markdown(table_content, extensions=["markdown.extensions.tables"])

            tables.append({"content": (None, html_content), "metadata": {"type": "table", "source": "markdown_extraction"}})

        return tables

    def _fallback_chunking(self, content: str) -> List[ChunkResult]:
        """降级分块策略"""
        logging.warning("使用降级分块策略")

        # 简单按段落分割
        paragraphs = content.split("\n\n")
        chunks = []

        current_content = ""
        current_tokens = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            para_tokens = num_tokens_from_string(paragraph)

            if current_tokens + para_tokens <= self.max_tokens:
                current_content += paragraph + "\n\n"
                current_tokens += para_tokens
            else:
                if current_content:
                    chunks.append(
                        ChunkResult(
                            content=current_content.strip(), token_count=current_tokens, element_types=["paragraph"], context_info={}, images=None, tables=[], metadata={"chunk_method": "fallback"}
                        )
                    )

                current_content = paragraph + "\n\n"
                current_tokens = para_tokens

        if current_content:
            chunks.append(
                ChunkResult(content=current_content.strip(), token_count=current_tokens, element_types=["paragraph"], context_info={}, images=None, tables=[], metadata={"chunk_method": "fallback"})
            )

        return chunks
