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
MinerU 专用文档处理模块

独立的 MinerU + Markdown 处理流程，避免 PDF 解析器的设计冲突

核心设计理念：
1. PDF 文件 → MinerU API → Markdown 内容
2. Markdown 内容 → 结构化解析 → 文本段落 + 表格
3. 文本段落 + 表格 → RAGFlow chunking → 最终文档块

优势：
- 专门针对 Markdown 格式优化
- 充分利用 MinerU 的结构化输出
- 避免 PDF 坐标系统的复杂性
- 与 RAGFlow 生态完全兼容
"""

import logging
import re
from typing import List, Dict, Any, Optional
from timeit import default_timer as timer

from api.db import ParserType
from api import settings
from rag.nlp import rag_tokenizer, tokenize_table, tokenize_chunks, naive_merge
from deepdoc.parser.mineru_parser import MinerUParser, create_mineru_parser
from deepdoc.parser.pdf_parser import PlainParser

logger = logging.getLogger(__name__)


def chunk(filename, binary=None, from_page=0, to_page=100000, lang="Chinese", callback=None, **kwargs):
    """
    MinerU + Markdown 专用文档处理入口

    处理流程：
    1. PDF → MinerU API → Markdown → 结构化数据
    2. Markdown → 文本段落 + 表格
    3. 应用 RAGFlow 的 chunking 和 tokenization

    Args:
        filename: 文件名或路径
        binary: 文件二进制内容
        from_page: 起始页码（MinerU 处理全文档，但保持接口兼容）
        to_page: 结束页码
        lang: 语言设置
        callback: 进度回调函数
        **kwargs: 其他参数，包括 parser_config

    Returns:
        List[Dict]: 分块后的文档列表，与 naive.chunk 格式兼容
    """

    # 验证文件类型
    if not re.search(r"\.pdf$", filename, re.IGNORECASE):
        raise NotImplementedError("MinerU 处理器专门为 PDF 文件设计")

    # 获取配置
    parser_config = kwargs.get("parser_config", {})

    # 初始化文档基础信息（与 naive.py 保持一致）
    doc = {"docnm_kwd": filename, "title_tks": rag_tokenizer.tokenize(re.sub(r"\.[a-zA-Z]+$", "", filename))}
    doc["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(doc["title_tks"])

    # 判断语言
    is_english = lang.lower() == "english"

    try:
        logger.info(f"开始 MinerU 处理: {filename}")
        if callback:
            callback(0.05, "初始化 MinerU Markdown 处理器...")

        # 1. 获取 MinerU 配置并创建解析器
        # 避免 parser_config 重复传递的问题
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop("parser_config", None)  # 移除重复的 parser_config
        mineru_config = _get_mineru_config(parser_config, **kwargs_copy)
        logger.info(f"MinerU 配置: {mineru_config}")
        mineru_parser = create_mineru_parser(mineru_config)

        if callback:
            callback(0.1, "开始 MinerU Markdown 解析流程...")

        # 2. 执行 MinerU 解析：PDF → Markdown → 结构化内容
        sections, tables = mineru_parser.parse(filename=filename, binary=binary, from_page=from_page, to_page=to_page, callback=callback)

        if callback:
            callback(0.7, f"MinerU 解析完成，获得 {len(sections)} 个段落和 {len(tables)} 个表格")

        # 3. 处理表格（使用 RAGFlow 标准方法）
        if callback:
            callback(0.75, "开始处理表格...")

        res = tokenize_table(tables, doc, is_english)

        if callback:
            callback(0.8, "表格处理完成，开始文本分块...")

        # 4. 文本分块（使用与 naive.py 相同的逻辑）
        chunk_token_num = int(parser_config.get("chunk_token_num", 128))
        delimiter = parser_config.get("delimiter", "\n!?。；！？")

        # 使用 naive_merge 进行分块
        chunks = naive_merge(sections, chunk_token_num, delimiter)

        if callback:
            callback(0.85, f"文本分块完成，生成 {len(chunks)} 个文本块")

        # 如果只需要段落，直接返回
        if kwargs.get("section_only", False):
            return chunks

        # 5. 标记化处理（使用 RAGFlow 标准方法）
        if callback:
            callback(0.9, "开始标记化处理...")

        # 创建一个虚拟的解析器对象用于 tokenize_chunks
        # 这里我们使用一个简单的类来模拟解析器接口
        dummy_parser = _create_dummy_parser()

        res.extend(tokenize_chunks(chunks, doc, is_english, dummy_parser))

        if callback:
            callback(1.0, f"MinerU 处理完成，共生成 {len(res)} 个文档块")

        logger.info(f"MinerU + Markdown 处理完成: {len(res)} 个文档块")
        return res

    except Exception as e:
        logger.error(f"MinerU + Markdown 处理失败: {e}")
        if callback:
            callback(msg=f"MinerU 处理失败: {str(e)}")

        # 检查是否启用回退机制
        fallback_enabled = kwargs.get("fallback_to_plain", True)
        if fallback_enabled:
            logger.warning("回退到简单文本解析器")
            if callback:
                callback(msg="回退到简单文本解析器")
            # 避免参数重复传递
            kwargs_copy = kwargs.copy()
            kwargs_copy.pop("parser_config", None)
            return _fallback_to_plain_parser(filename, binary, from_page, to_page, lang, callback, doc, is_english, parser_config, **kwargs_copy)
        else:
            raise


def _get_mineru_config(parser_config: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    从配置中获取 MinerU 参数
    支持多种配置来源的优先级：kwargs > parser_config > settings
    """
    config = {
        # API 配置
        "api_endpoint": (kwargs.get("mineru_endpoint") or parser_config.get("mineru_endpoint") or getattr(settings, "MINERU_ENDPOINT", "http://172.19.0.3:8081/file_parse")),
        "api_timeout": (kwargs.get("mineru_timeout") or parser_config.get("mineru_timeout") or getattr(settings, "MINERU_TIMEOUT", 600)),
        # 解析配置
        "parse_method": (kwargs.get("parse_method") or parser_config.get("parse_method") or getattr(settings, "MINERU_PARSE_METHOD", "auto")),
        # 返回内容配置
        "return_layout": parser_config.get("return_layout", False),
        "return_info": parser_config.get("return_info", False),
        "return_content_list": parser_config.get("return_content_list", True),
        "return_images": parser_config.get("return_images", True),
        # 图片处理配置
        "process_images": parser_config.get("process_images", True),
        "max_image_size": parser_config.get("max_image_size", (800, 800)),
        # 调试配置
        "enable_debug": parser_config.get("enable_debug", False),
        "output_format": "ragflow",
    }

    # 如果 parser_config 中有完整的 mineru_config，合并它
    if "mineru_config" in parser_config:
        user_config = parser_config["mineru_config"]
        if isinstance(user_config, dict):
            config.update(user_config)

    return config


def _create_dummy_parser():
    """
    创建一个虚拟解析器对象，用于 tokenize_chunks
    """

    class DummyParser:
        def __init__(self):
            self.model_species = ParserType.MINERU.value

        def crop(self, chunk, need_position=False):
            """
            虚拟的 crop 方法，抛出 NotImplementedError
            这样 tokenize_chunks 会正确处理并跳过图片处理
            """
            raise NotImplementedError("MinerU 处理器不支持图片裁剪功能")

        def remove_tag(self, text):
            """
            虚拟的 remove_tag 方法，直接返回文本
            """
            return text

    return DummyParser()


def _fallback_to_plain_parser(filename, binary, from_page, to_page, lang, callback, doc, is_english, parser_config, **kwargs):
    """
    回退到简单文本解析器
    保持与 naive.py 的完全兼容性
    """
    try:
        if callback:
            callback(0.1, "使用简单文本解析器...")

        plain_parser = PlainParser()
        sections, tables = plain_parser(filename if not binary else binary, from_page=from_page, to_page=to_page)

        if callback:
            callback(0.5, "简单解析完成，开始处理...")

        # 处理表格
        res = tokenize_table(tables, doc, is_english)

        # 进行分块
        chunk_token_num = int(parser_config.get("chunk_token_num", 128))
        delimiter = parser_config.get("delimiter", "\n!?。；！？")
        chunks = naive_merge(sections, chunk_token_num, delimiter)

        if kwargs.get("section_only", False):
            return chunks

        # 标记化
        dummy_parser = _create_dummy_parser()
        res.extend(tokenize_chunks(chunks, doc, is_english, dummy_parser))

        if callback:
            callback(1.0, f"回退处理完成，共生成 {len(res)} 个文档块")

        return res

    except Exception as e:
        logger.error(f"回退解析器也失败了: {e}")
        raise RuntimeError(f"MinerU 和回退解析器都失败了: {filename}") from e


# === 辅助和兼容性函数 ===


def analyze_markdown_structure(sections: List, mineru_parser) -> List[int]:
    """
    分析 Markdown 文档结构
    针对 MinerU 的 Markdown 输出优化
    """
    try:
        # 基于 Markdown 标题层级分析
        levels = []

        for text, _ in sections:
            # 检测 Markdown 标题
            if text.strip().startswith("#"):
                # 计算标题级别
                level = 0
                for char in text:
                    if char == "#":
                        level += 1
                    else:
                        break
                levels.append(min(level, 6))  # 最多6级标题
            else:
                # 使用传统的标题频率分析作为回退
                level = _analyze_text_level(text)
                levels.append(level)

        return levels

    except Exception as e:
        logger.warning(f"Markdown 结构分析失败: {e}，使用默认层级")
        return [1] * len(sections)


def _analyze_text_level(text: str) -> int:
    """
    基于文本内容分析层级
    """
    try:
        # 简单启发式规则
        text_clean = text.strip()

        # 短文本可能是标题
        if len(text_clean) < 50:
            return 2

        # 包含项目符号的可能是列表
        if re.search(r"^[•\-\*]\s", text_clean, re.MULTILINE):
            return 3

        # 默认为正文
        return 4

    except Exception:
        return 4


def get_mineru_parser(config: Optional[Dict[str, Any]] = None) -> MinerUParser:
    """
    获取 MinerU 解析器实例
    供外部模块使用
    """
    return create_mineru_parser(config)


def is_mineru_service_available() -> bool:
    """
    检查 MinerU 服务是否可用
    """
    try:
        import requests

        # 从默认配置获取端点
        config = _get_mineru_config({})
        endpoint = config["api_endpoint"]

        # 尝试健康检查
        health_url = endpoint.replace("/file_parse", "/health")
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"MinerU 服务检查失败: {e}")
        return False


def get_mineru_status() -> Dict[str, Any]:
    """
    获取 MinerU 服务状态信息
    """
    config = _get_mineru_config({})

    return {
        "service_available": is_mineru_service_available(),
        "endpoint": config["api_endpoint"],
        "timeout": config["api_timeout"],
        "parse_method": config["parse_method"],
        "processing_type": "PDF → Markdown → RAGFlow",
        "supported_formats": ["pdf"],
        "features": ["高质量 PDF 转 Markdown", "结构化内容提取", "表格和图片处理", "智能分块和标记化"],
    }


def create_mineru_processor(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    创建 MinerU 处理器的工厂函数
    """
    return {
        "name": "MinerU Markdown Processor",
        "parser": get_mineru_parser(config),
        "chunk_func": chunk,
        "analyze_func": analyze_markdown_structure,
        "status_func": get_mineru_status,
        "supported_formats": ["pdf"],
        "processing_type": "markdown_based",
        "requires_service": True,
        "service_check": is_mineru_service_available,
    }


# === 测试和调试功能 ===

if __name__ == "__main__":
    import sys

    def progress_callback(progress=None, msg=""):
        if progress is not None:
            print(f"进度: {progress:.1%}")
        if msg:
            print(f"状态: {msg}")

    if len(sys.argv) > 1:
        try:
            print(f"🚀 使用 MinerU + Markdown 处理文件: {sys.argv[1]}")
            print("=" * 60)

            # 显示服务状态
            status = get_mineru_status()
            print(f"服务状态: {'✅ 可用' if status['service_available'] else '❌ 不可用'}")
            print(f"API 端点: {status['endpoint']}")
            print(f"处理类型: {status['processing_type']}")
            print()

            # 测试配置
            parser_config = {"chunk_token_num": 128, "delimiter": "\n!?。；！？", "enable_debug": True, "process_images": True, "return_content_list": True}

            start_time = timer()
            result = chunk(sys.argv[1], callback=progress_callback, parser_config=parser_config, fallback_to_plain=True)

            processing_time = timer() - start_time

            print("\n✅ 处理成功完成")
            print(f"⏱️  总耗时: {processing_time:.2f} 秒")
            print(f"📄 生成文档块: {len(result)} 个")

            # 显示前几个块的摘要信息
            print("\n📊 前 3 个文档块预览:")
            for i, chunk_data in enumerate(result[:3]):
                content = chunk_data.get("content_with_weight", "")
                tokens = chunk_data.get("token_num", 0)
                print(f"\n块 {i + 1} ({tokens} tokens):")
                print(f"  内容: {content[:100]}...")

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback

            traceback.print_exc()
    else:
        print("📖 MinerU + Markdown 文档处理器")
        print("用法: python mineru.py <pdf_file_path>")
        print("\n功能概述:")
        print("🔄 PDF → MinerU API → Markdown → 结构化文档块")
        print("🎯 专门针对 Markdown 格式优化，避免 PDF 坐标系统复杂性")
        print("🔧 与 RAGFlow 生态系统完全兼容")

        print("\n🔍 系统状态:")
        status = get_mineru_status()
        for key, value in status.items():
            if key == "features":
                print(f"  {key}: {', '.join(value)}")
            else:
                print(f"  {key}: {value}")

        print("\n📋 配置示例:")
        example_config = {"chunk_token_num": 128, "delimiter": "\n!?。；！？", "process_images": True, "return_content_list": True, "fallback_to_plain": True}
        for key, value in example_config.items():
            print(f"  {key}: {value}")
