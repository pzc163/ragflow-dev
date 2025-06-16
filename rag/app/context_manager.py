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
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .semantic_markdown_chunker import DocumentElement, ElementType, HeadingElement


@dataclass
class ContextInfo:
    """上下文信息类"""

    element_id: str
    parent_id: Optional[str]
    element_type: ElementType
    level: int
    title: str
    content_preview: str
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MarkdownContextManager:
    """Markdown文档上下文管理器"""

    def __init__(self):
        self.context_map: Dict[str, ContextInfo] = {}
        self.heading_stack: List[Tuple[int, str, str]] = []  # (level, title, element_id)
        self.current_section_id: Optional[str] = None

    def add_element(self, element: DocumentElement) -> str:
        """添加元素并建立上下文关系"""
        element_id = self._generate_element_id(element)

        # 创建上下文信息
        context_info = ContextInfo(
            element_id=element_id, parent_id=None, element_type=element.element_type, level=0, title="", content_preview=self._create_content_preview(element.content), metadata=element.metadata.copy()
        )

        # 处理不同类型的元素
        if element.element_type == ElementType.HEADING:
            self._handle_heading_element(element, context_info)
        else:
            self._handle_content_element(element, context_info)

        # 存储上下文信息
        self.context_map[element_id] = context_info

        return element_id

    def _generate_element_id(self, element: DocumentElement) -> str:
        """生成元素唯一ID"""
        return f"{element.element_type.value}_{element.line_start}_{element.line_end}"

    def _create_content_preview(self, content: str, max_length: int = 50) -> str:
        """创建内容预览"""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."

    def _handle_heading_element(self, element: HeadingElement, context_info: ContextInfo):
        """处理标题元素"""
        context_info.level = element.level
        context_info.title = element.title

        # 维护标题层级栈
        current_level = element.level

        # 弹出比当前级别低的标题
        while self.heading_stack and self.heading_stack[-1][0] >= current_level:
            self.heading_stack.pop()

        # 设置父子关系
        if self.heading_stack:
            parent_level, parent_title, parent_id = self.heading_stack[-1]
            context_info.parent_id = parent_id

            # 将当前元素添加到父元素的子元素列表
            if parent_id in self.context_map:
                self.context_map[parent_id].children.append(context_info.element_id)

        # 将当前标题添加到栈中
        self.heading_stack.append((current_level, element.title, context_info.element_id))
        self.current_section_id = context_info.element_id

    def _handle_content_element(self, element: DocumentElement, context_info: ContextInfo):
        """处理内容元素"""
        # 非标题元素归属于当前章节
        if self.current_section_id:
            context_info.parent_id = self.current_section_id
            if self.current_section_id in self.context_map:
                self.context_map[self.current_section_id].children.append(context_info.element_id)

    def get_context_path(self, element_id: str) -> List[str]:
        """获取元素的完整上下文路径"""
        path = []
        current_id = element_id

        while current_id and current_id in self.context_map:
            context = self.context_map[current_id]
            if context.element_type == ElementType.HEADING:
                path.append(context.title)
            current_id = context.parent_id

        path.reverse()  # 从根到叶
        return path

    def get_section_context(self, element_id: str) -> Dict[str, Any]:
        """获取元素所在章节的完整上下文"""
        if element_id not in self.context_map:
            return {}

        context = self.context_map[element_id]

        # 找到所属的章节标题
        section_id = self._find_section_heading(element_id)
        if not section_id:
            return {"path": [], "section_title": "", "element_type": context.element_type.value}

        section_context = self.context_map[section_id]
        path = self.get_context_path(section_id)

        return {"path": path, "section_title": section_context.title, "section_level": section_context.level, "element_type": context.element_type.value, "parent_id": context.parent_id}

    def _find_section_heading(self, element_id: str) -> Optional[str]:
        """找到元素所属的章节标题"""
        current_id = element_id

        while current_id and current_id in self.context_map:
            context = self.context_map[current_id]
            if context.element_type == ElementType.HEADING:
                return current_id
            current_id = context.parent_id

        return None

    def get_related_elements(self, element_id: str, include_siblings: bool = True) -> List[str]:
        """获取相关元素（同一章节下的元素）"""
        if element_id not in self.context_map:
            return []

        section_id = self._find_section_heading(element_id)
        if not section_id:
            return []

        section_context = self.context_map[section_id]
        related_elements = []

        # 添加章节标题
        related_elements.append(section_id)

        # 添加章节下的所有子元素
        related_elements.extend(section_context.children)

        return related_elements

    def should_keep_together(self, element1_id: str, element2_id: str) -> bool:
        """判断两个元素是否应该保持在一起"""
        if element1_id not in self.context_map or element2_id not in self.context_map:
            return False

        context1 = self.context_map[element1_id]
        context2 = self.context_map[element2_id]

        # 1. 标题和其直接内容应该保持在一起
        if context1.element_type == ElementType.HEADING and context2.parent_id == element1_id:
            return True

        # 2. 列表项应该尽量保持在一起
        if context1.element_type == ElementType.LIST and context2.element_type == ElementType.LIST and context1.parent_id == context2.parent_id:
            return True

        # 3. 表格和其上下文说明应该保持在一起
        if self._is_table_with_context(element1_id, element2_id):
            return True

        return False

    def _is_table_with_context(self, element1_id: str, element2_id: str) -> bool:
        """判断是否是表格和其上下文说明"""
        context1 = self.context_map[element1_id]
        context2 = self.context_map[element2_id]

        # 检查表格前的说明段落
        if context1.element_type == ElementType.PARAGRAPH and context2.element_type == ElementType.TABLE:
            # 检查内容是否包含表格相关关键词
            content = context1.content_preview.lower()
            if any(keyword in content for keyword in ["表", "table", "如下", "见表", "统计"]):
                return True

        # 检查表格后的说明段落
        if context1.element_type == ElementType.TABLE and context2.element_type == ElementType.PARAGRAPH:
            content = context2.content_preview.lower()
            if any(keyword in content for keyword in ["上表", "above table", "表中", "如表所示"]):
                return True

        return False

    def get_enhanced_context_for_chunk(self, element_ids: List[str]) -> Dict[str, Any]:
        """为分块获取增强的上下文信息"""
        if not element_ids:
            return {}

        # 收集所有相关的上下文信息
        all_paths = []
        section_titles = set()
        element_types = []

        for element_id in element_ids:
            if element_id in self.context_map:
                context = self.get_section_context(element_id)
                if context.get("path"):
                    all_paths.append(context["path"])
                if context.get("section_title"):
                    section_titles.add(context["section_title"])
                element_types.append(context.get("element_type", ""))

        # 找到最长的公共路径前缀
        common_path = self._find_common_path_prefix(all_paths)

        return {"common_context_path": common_path, "section_titles": list(section_titles), "element_types": element_types, "context_preserved": True, "hierarchy_maintained": len(common_path) > 0}

    def _find_common_path_prefix(self, paths: List[List[str]]) -> List[str]:
        """找到路径列表的公共前缀"""
        if not paths:
            return []

        if len(paths) == 1:
            return paths[0]

        common = []
        min_length = min(len(path) for path in paths)

        for i in range(min_length):
            current_item = paths[0][i]
            if all(path[i] == current_item for path in paths):
                common.append(current_item)
            else:
                break

        return common

    def debug_print_structure(self):
        """打印文档结构（调试用）"""
        logging.info("=== Document Structure ===")
        for element_id, context in self.context_map.items():
            indent = "  " * context.level
            logging.info(f"{indent}{element_id}: {context.element_type.value} - {context.title or context.content_preview}")
            if context.children:
                logging.info(f"{indent}  Children: {context.children}")
