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

"""
分块器工厂模式设计示例
这是对现有naive.py中统一chunk函数的重构建议
"""

import re
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from rag.nlp import rag_tokenizer, tokenize_chunks, tokenize_chunks_with_images, tokenize_table


@dataclass
class ChunkConfig:
    """分块配置类"""

    chunk_token_num: int = 128
    delimiter: str = "\n!?。；！？"
    lang: str = "Chinese"
    from_page: int = 0
    to_page: int = 100000

    # 格式特定配置
    layout_recognize: str = "DeepDOC"  # PDF专用
    smart_chunking: bool = False  # Markdown专用
    preserve_code_blocks: bool = True  # Markdown专用
    preserve_tables: bool = True  # Markdown专用
    maintain_hierarchy: bool = True  # Markdown专用
    extract_images: bool = True  # Markdown专用
    html4excel: bool = False  # Excel专用


@dataclass
class ChunkResult:
    """分块结果类"""

    chunks: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class BaseChunker(ABC):
    """分块器基类"""

    def __init__(self, config: ChunkConfig):
        self.config = config
        self.is_english = config.lang.lower() == "english"

    @abstractmethod
    def can_handle(self, filename: str) -> bool:
        """判断是否能处理指定文件"""
        pass

    @abstractmethod
    def chunk(self, filename: str, binary: Optional[bytes] = None, callback=None, **kwargs) -> ChunkResult:
        """执行分块"""
        pass

    def _create_doc_metadata(self, filename: str) -> Dict[str, Any]:
        """创建文档元数据"""
        return {"docnm_kwd": filename, "title_tks": rag_tokenizer.tokenize(re.sub(r"\.[a-zA-Z]+$", "", filename))}


class MarkdownChunker(BaseChunker):
    """Markdown文档分块器"""

    def can_handle(self, filename: str) -> bool:
        return bool(re.search(r"\.(md|markdown)$", filename, re.IGNORECASE))

    def chunk(self, filename: str, binary: Optional[bytes] = None, callback=None, **kwargs) -> ChunkResult:
        """Markdown文档分块"""
        callback(0.1, "Start to parse Markdown.")

        doc = self._create_doc_metadata(filename)
        doc["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(doc["title_tks"])

        if self.config.smart_chunking:
            return self._smart_chunk(filename, binary, doc, callback, **kwargs)
        else:
            return self._naive_chunk(filename, binary, doc, callback, **kwargs)

    def _smart_chunk(self, filename: str, binary: Optional[bytes], doc: Dict[str, Any], callback, **kwargs) -> ChunkResult:
        """智能分块"""
        try:
            from .smart_chunker import SmartMarkdownChunker

            # 读取文件内容
            if binary:
                from rag.nlp import find_codec

                encoding = find_codec(binary)
                content = binary.decode(encoding, errors="ignore")
            else:
                with open(filename, "r") as f:
                    content = f.read()

            # 创建智能分块器
            smart_chunker = SmartMarkdownChunker(
                max_tokens=self.config.chunk_token_num,
                delimiter=self.config.delimiter,
                preserve_code_blocks=self.config.preserve_code_blocks,
                preserve_tables=self.config.preserve_tables,
                maintain_hierarchy=self.config.maintain_hierarchy,
                extract_images=self.config.extract_images,
            )

            callback(0.3, "Using smart semantic chunker...")

            # 执行智能分块
            chunk_results, table_results = smart_chunker.chunk_markdown(content, filename)

            callback(0.7, f"Smart chunking complete: {len(chunk_results)} chunks, {len(table_results)} tables")

            # 转换为标准格式
            sections = []
            section_images = []

            for chunk_result in chunk_results:
                sections.append((chunk_result.content, ""))
                if chunk_result.images:
                    section_images.append(chunk_result.images[0])
                else:
                    section_images.append(None)

            # 处理表格
            tables = []
            for table_result in table_results:
                tables.append((table_result["content"], ""))

            res = tokenize_table(tables, doc, self.is_english)

            # 处理文本块
            if section_images and not all(img is None for img in section_images):
                from rag.nlp import naive_merge_with_images

                chunks, images = naive_merge_with_images(sections, section_images, self.config.chunk_token_num, self.config.delimiter)
                res.extend(tokenize_chunks_with_images(chunks, doc, self.is_english, images))
            else:
                from rag.nlp import naive_merge

                chunks = naive_merge(sections, self.config.chunk_token_num, self.config.delimiter)
                res.extend(tokenize_chunks(chunks, doc, self.is_english, None))

            callback(0.8, "Smart chunking finished.")

            return ChunkResult(chunks=res, metadata={"method": "smart_semantic", "chunks_count": len(chunk_results), "tables_count": len(table_results), "structure_preserved": True})

        except Exception as e:
            logging.error(f"Smart chunking failed: {e}")
            return self._naive_chunk(filename, binary, doc, callback, **kwargs)

    def _naive_chunk(self, filename: str, binary: Optional[bytes], doc: Dict[str, Any], callback, **kwargs) -> ChunkResult:
        """原有分块方法"""
        from .naive import Markdown
        from rag.nlp import naive_merge_with_images, naive_merge, concat_img
        from functools import reduce

        markdown_parser = Markdown(self.config.chunk_token_num)
        sections, tables = markdown_parser(filename, binary)

        # 处理图片
        section_images = []
        for section_text, _ in sections:
            images = markdown_parser.get_pictures(section_text) if section_text else None
            if images:
                combined_image = reduce(concat_img, images) if len(images) > 1 else images[0]
                section_images.append(combined_image)
            else:
                section_images.append(None)

        res = tokenize_table(tables, doc, self.is_english)

        # 处理文本块
        if section_images and not all(img is None for img in section_images):
            chunks, images = naive_merge_with_images(sections, section_images, self.config.chunk_token_num, self.config.delimiter)
            res.extend(tokenize_chunks_with_images(chunks, doc, self.is_english, images))
        else:
            chunks = naive_merge(sections, self.config.chunk_token_num, self.config.delimiter)
            res.extend(tokenize_chunks(chunks, doc, self.is_english, None))

        callback(0.8, "Naive chunking finished.")

        return ChunkResult(chunks=res, metadata={"method": "naive", "sections_count": len(sections), "tables_count": len(tables)})


class PDFChunker(BaseChunker):
    """PDF文档分块器"""

    def can_handle(self, filename: str) -> bool:
        return bool(re.search(r"\.pdf$", filename, re.IGNORECASE))

    def chunk(self, filename: str, binary: Optional[bytes] = None, callback=None, **kwargs) -> ChunkResult:
        """PDF文档分块"""
        from .naive import Pdf
        from deepdoc.parser.pdf_parser import PlainParser, VisionParser
        from api.db.services.llm_service import LLMBundle
        from api.db import LLMType
        from rag.nlp import naive_merge

        callback(0.1, "Start to parse PDF.")

        doc = self._create_doc_metadata(filename)
        doc["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(doc["title_tks"])

        layout_recognizer = self.config.layout_recognize
        if isinstance(layout_recognizer, bool):
            layout_recognizer = "DeepDOC" if layout_recognizer else "Plain Text"

        if layout_recognizer == "DeepDOC":
            pdf_parser = Pdf()
            sections, tables = pdf_parser(filename if not binary else binary, from_page=self.config.from_page, to_page=self.config.to_page, callback=callback)
        elif layout_recognizer == "Plain Text":
            pdf_parser = PlainParser()
            sections, tables = pdf_parser(filename if not binary else binary, from_page=self.config.from_page, to_page=self.config.to_page, callback=callback)
        else:
            vision_model = LLMBundle(kwargs["tenant_id"], LLMType.IMAGE2TEXT, llm_name=layout_recognizer, lang=self.config.lang)
            pdf_parser = VisionParser(vision_model=vision_model, **kwargs)
            sections, tables = pdf_parser(filename if not binary else binary, from_page=self.config.from_page, to_page=self.config.to_page, callback=callback)

        res = tokenize_table(tables, doc, self.is_english)
        callback(0.8, "Finish parsing PDF.")

        # PDF使用通用分块
        chunks = naive_merge(sections, self.config.chunk_token_num, self.config.delimiter)
        res.extend(tokenize_chunks(chunks, doc, self.is_english, pdf_parser))

        return ChunkResult(
            chunks=res, metadata={"method": f"pdf_{layout_recognizer.lower().replace(' ', '_')}", "sections_count": len(sections), "tables_count": len(tables), "layout_recognizer": layout_recognizer}
        )


class WordChunker(BaseChunker):
    """Word文档分块器"""

    def can_handle(self, filename: str) -> bool:
        return bool(re.search(r"\.docx$", filename, re.IGNORECASE))

    def chunk(self, filename: str, binary: Optional[bytes] = None, callback=None, **kwargs) -> ChunkResult:
        """Word文档分块"""
        from .naive import Docx
        from rag.nlp import naive_merge_docx

        callback(0.1, "Start to parse Word document.")

        doc = self._create_doc_metadata(filename)
        doc["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(doc["title_tks"])

        sections, tables = Docx()(filename, binary)
        res = tokenize_table(tables, doc, self.is_english)
        callback(0.8, "Finish parsing Word document.")

        # Word使用专用分块
        chunks, images = naive_merge_docx(sections, self.config.chunk_token_num, self.config.delimiter)
        res.extend(tokenize_chunks_with_images(chunks, doc, self.is_english, images))

        return ChunkResult(chunks=res, metadata={"method": "docx", "sections_count": len(sections), "tables_count": len(tables)})


class ChunkerFactory:
    """分块器工厂"""

    def __init__(self):
        self._chunkers = [
            MarkdownChunker,
            PDFChunker,
            WordChunker,
            # 可以继续添加其他格式的分块器
        ]

    def create_chunker(self, filename: str, config: ChunkConfig) -> BaseChunker:
        """根据文件名创建对应的分块器"""
        for chunker_class in self._chunkers:
            chunker = chunker_class(config)
            if chunker.can_handle(filename):
                return chunker

        raise ValueError(f"No suitable chunker found for file: {filename}")

    def chunk_file(self, filename: str, binary: Optional[bytes] = None, config: Optional[ChunkConfig] = None, callback=None, **kwargs) -> ChunkResult:
        """统一的文件分块接口"""
        if config is None:
            config = ChunkConfig()

        chunker = self.create_chunker(filename, config)
        return chunker.chunk(filename, binary, callback, **kwargs)


# 使用示例
def improved_chunk(filename, binary=None, from_page=0, to_page=100000, lang="Chinese", callback=None, **kwargs):
    """改进的统一分块函数"""

    # 从kwargs中提取配置
    parser_config = kwargs.get("parser_config", {})

    config = ChunkConfig(
        chunk_token_num=parser_config.get("chunk_token_num", 128),
        delimiter=parser_config.get("delimiter", "\n!?。；！？"),
        lang=lang,
        from_page=from_page,
        to_page=to_page,
        layout_recognize=parser_config.get("layout_recognize", "DeepDOC"),
        smart_chunking=parser_config.get("smart_chunking", False),
        preserve_code_blocks=parser_config.get("preserve_code_blocks", True),
        preserve_tables=parser_config.get("preserve_tables", True),
        maintain_hierarchy=parser_config.get("maintain_hierarchy", True),
        extract_images=parser_config.get("extract_images", True),
        html4excel=parser_config.get("html4excel", False),
    )

    factory = ChunkerFactory()
    result = factory.chunk_file(filename, binary, config, callback, **kwargs)

    return result.chunks
