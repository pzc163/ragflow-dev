"""
MinerU Markdown 文档解析器

专门处理 MinerU API 返回的 Markdown 格式文档
设计原则：
1. 不继承 PDF 解析器，避免设计冲突
2. 专门针对 Markdown 格式优化
3. 充分利用 MinerU 的结构化输出
4. 与 RAGFlow 生态系统兼容
"""

import requests
import json
import logging
import base64
import re
from io import BytesIO
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image

logger = logging.getLogger(__name__)


class MinerUParser:
    """
    专用的 MinerU Markdown 解析器

    核心功能：
    1. 调用 MinerU API，获取 Markdown 内容
    2. 解析 Markdown，提取文本段落和表格
    3. 处理图片和视觉元素
    4. 输出 RAGFlow 兼容的格式

    与传统 PDF 解析器的区别：
    - 输入：PDF 文件
    - 中间：Markdown 内容（MinerU 转换）
    - 输出：结构化的文本段落和表格
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化 MinerU Markdown 解析器

        Args:
            config: MinerU API 和处理配置
        """
        self.config = self._get_default_config()
        if config:
            self.config.update(config)

        self.api_endpoint = self.config["api_endpoint"]
        self.api_timeout = self.config["api_timeout"]
        self.enable_debug = self.config["enable_debug"]

        # Markdown 处理配置
        self.markdown_extensions = ["tables", "fenced_code", "toc"]

        # 图片处理配置
        self.process_images = self.config.get("process_images", True)
        self.max_image_size = self.config.get("max_image_size", (800, 800))

        logger.info("MinerU Markdown Parser 初始化完成")

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "api_endpoint": "http://172.19.0.3:8081/file_parse",
            "api_timeout": 600,
            "parse_method": "auto",  # auto, ocr, txt
            "return_layout": False,
            "return_info": False,
            "return_content_list": True,
            "return_images": True,
            "process_images": True,
            "max_image_size": (800, 800),
            "enable_debug": False,
            "output_format": "ragflow",  # ragflow, simple
        }

    def parse(self, filename: str, binary: Optional[bytes] = None, from_page: int = 0, to_page: int = 100000, callback=None) -> Tuple[List[Tuple], List[Tuple]]:
        """
        解析文档的主入口

        Args:
            filename: 文件名或路径
            binary: 文件二进制内容
            from_page: 起始页码（MinerU 会忽略，但保持接口兼容）
            to_page: 结束页码
            callback: 进度回调函数

        Returns:
            Tuple[sections, tables]: RAGFlow 格式的段落和表格
        """
        try:
            if callback:
                callback(0.1, "开始调用 MinerU API...")

            # 1. 调用 MinerU API
            api_response = self._call_mineru_api(filename, binary, callback)

            if callback:
                callback(0.4, "MinerU API 调用成功，开始处理 Markdown...")

            # 2. 处理 API 响应，提取 Markdown 和其他数据
            markdown_content, images_data, additional_data = self._extract_api_data(api_response)

            if callback:
                callback(0.6, "开始解析 Markdown 内容...")

            # 3. 处理图片数据
            processed_images = {}
            if self.process_images and images_data:
                processed_images = self._process_images(images_data, callback)

            # 4. 解析 Markdown 内容
            sections, tables = self._parse_markdown_content(markdown_content, processed_images, additional_data, callback)

            if callback:
                callback(1.0, f"解析完成：{len(sections)} 个段落，{len(tables)} 个表格")

            return sections, tables

        except Exception as e:
            logger.error(f"MinerU Markdown 解析失败: {e}")
            if callback:
                callback(msg=f"解析失败: {str(e)}")
            raise

    def _call_mineru_api(self, filename: str, binary: Optional[bytes], callback) -> Dict[str, Any]:
        """
        调用 MinerU API，获取 Markdown 和相关数据
        """
        try:
            # 准备文件数据
            if binary:
                file_bytes = binary
                file_path = filename or "document.pdf"
            else:
                with open(filename, "rb") as f:
                    file_bytes = f.read()
                file_path = filename

            # 构建请求
            files = {"file": (file_path, file_bytes, "application/pdf")}

            data = {
                "parse_method": self.config["parse_method"],
                "return_layout": self.config["return_layout"],
                "return_info": self.config["return_info"],
                "return_content_list": self.config["return_content_list"],
                "return_images": self.config["return_images"],
            }

            if callback:
                callback(0.2, "正在上传文件到 MinerU...")

            logger.info(f"发送 MinerU HTTP 请求到: {self.api_endpoint}")
            logger.info(f"请求参数: {data}")
            logger.info(f"文件大小: {len(file_bytes)} bytes")

            response = requests.post(self.api_endpoint, files=files, data=data, timeout=self.api_timeout)
            response.raise_for_status()

            logger.info(f"MinerU HTTP 响应状态: {response.status_code}")
            logger.info(f"MinerU HTTP 响应头: {dict(response.headers)}")

            result = response.json()

            if callback:
                callback(0.35, "MinerU API 响应接收完成")

            if self.enable_debug:
                logger.debug(f"MinerU API 响应: {json.dumps(result, ensure_ascii=False)[:500]}...")

            return result

        except Exception as e:
            logger.error(f"MinerU API 调用失败: {e}")
            raise RuntimeError(f"MinerU API 调用失败: {e}") from e

    def _extract_api_data(self, api_response: Dict[str, Any]) -> Tuple[str, Dict, Dict]:
        """
        从 API 响应中提取关键数据

        Returns:
            Tuple[markdown_content, images_data, additional_data]
        """
        try:
            # 检查错误
            if "error" in api_response:
                raise RuntimeError(f"MinerU API 返回错误: {api_response['error']}")

            # 提取 Markdown 内容（核心数据）
            markdown_content = api_response.get("md_content", "")
            if not markdown_content:
                logger.warning("MinerU API 未返回 md_content")
                markdown_content = ""

            # 提取图片数据
            images_data = api_response.get("images", {})

            # 提取其他结构化数据
            additional_data = {"content_list": api_response.get("content_list", []), "layout": api_response.get("layout", {}), "info": api_response.get("info", {}), "raw_response": api_response}

            logger.info(f"成功提取数据: Markdown {len(markdown_content)} 字符, {len(images_data)} 张图片")

            return markdown_content, images_data, additional_data

        except Exception as e:
            logger.error(f"提取 API 数据失败: {e}")
            raise

    def _process_images(self, images_data: Dict[str, str], callback=None) -> Dict[str, Dict]:
        """
        处理图片数据：解码、描述、优化
        """
        processed_images = {}

        if not images_data:
            return processed_images

        try:
            total_images = len(images_data)
            if callback:
                callback(0.5, f"开始处理 {total_images} 张图片...")

            for i, (filename, base64_data) in enumerate(images_data.items()):
                try:
                    # 解码图片
                    if base64_data.startswith("data:image/"):
                        header, base64_content = base64_data.split(",", 1)
                        image_format = header.split(";")[0].split("/")[1]
                    else:
                        base64_content = base64_data
                        image_format = "jpeg"

                    image_bytes = base64.b64decode(base64_content)
                    image = Image.open(BytesIO(image_bytes)).convert("RGB")

                    # 生成图片描述
                    description = self._generate_image_description(image, filename, image_format)

                    # 图片尺寸优化
                    if self.max_image_size:
                        image = self._resize_image(image, self.max_image_size)

                    processed_images[filename] = {"image": image, "description": description, "filename": filename, "format": image_format, "size": image.size}

                    if callback and i % 3 == 0:
                        progress = 0.5 + (i / total_images) * 0.05
                        callback(progress, f"处理图片 {i + 1}/{total_images}")

                except Exception as e:
                    logger.warning(f"处理图片 {filename} 失败: {e}")
                    processed_images[filename] = {"description": f"图片: {filename} (处理失败)", "filename": filename, "error": str(e)}

            success_count = len([v for v in processed_images.values() if "error" not in v])
            logger.info(f"图片处理完成: {success_count}/{total_images} 成功")

        except Exception as e:
            logger.error(f"批量处理图片失败: {e}")

        return processed_images

    def _generate_image_description(self, image: Image.Image, filename: str, image_format: str) -> str:
        """
        生成图片描述
        """
        try:
            width, height = image.size
            aspect_ratio = width / height

            # 基于尺寸和比例判断图片类型
            if aspect_ratio > 2.5:
                image_type = "宽幅图表或流程图"
            elif aspect_ratio < 0.4:
                image_type = "纵向图表或列表"
            elif 0.8 <= aspect_ratio <= 1.2:
                image_type = "方形图表或图形"
            else:
                image_type = "标准图表或图像"

            return f"{image_type}，尺寸 {width}×{height}，{image_format.upper()} 格式（来源：MinerU 提取）"

        except Exception as e:
            logger.warning(f"生成图片描述失败: {e}")
            return f"图片: {filename} (MinerU 提取)"

    def _resize_image(self, image: Image.Image, max_size: Tuple[int, int]) -> Image.Image:
        """
        智能调整图片尺寸
        """
        try:
            current_width, current_height = image.size
            max_width, max_height = max_size

            # 计算缩放比例
            width_ratio = max_width / current_width
            height_ratio = max_height / current_height
            ratio = min(width_ratio, height_ratio)

            if ratio >= 1.0:
                return image  # 不需要缩小

            new_width = int(current_width * ratio)
            new_height = int(current_height * ratio)

            return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        except Exception as e:
            logger.warning(f"调整图片尺寸失败: {e}")
            return image

    def _parse_markdown_content(self, markdown_content: str, processed_images: Dict, additional_data: Dict, callback=None) -> Tuple[List[Tuple], List[Tuple]]:
        """
        解析 Markdown 内容，提取段落和表格

        这是核心的 Markdown → RAGFlow 格式转换逻辑
        """
        sections = []
        tables = []

        if not markdown_content.strip():
            logger.warning("Markdown 内容为空")
            return sections, tables

        try:
            if callback:
                callback(0.65, "开始解析 Markdown 结构...")

            # 1. 使用优先的结构化数据（如果可用）
            content_list = additional_data.get("content_list", [])
            if content_list:
                sections_from_list, tables_from_list = self._parse_content_list(content_list, processed_images)
                if sections_from_list or tables_from_list:
                    logger.info("使用 content_list 解析结果")
                    sections.extend(sections_from_list)
                    tables.extend(tables_from_list)

            # 2. 如果没有结构化数据，或者作为补充，解析原始 Markdown
            if not sections:  # 没有从 content_list 获得内容
                if callback:
                    callback(0.75, "解析原始 Markdown 内容...")

                sections_from_md, tables_from_md = self._parse_raw_markdown(markdown_content, processed_images)
                sections.extend(sections_from_md)
                tables.extend(tables_from_md)

            # 3. 后处理：清理和优化
            sections = self._post_process_sections(sections)
            tables = self._post_process_tables(tables)

            if callback:
                callback(0.9, "Markdown 解析完成")

            logger.info(f"Markdown 解析结果: {len(sections)} 段落, {len(tables)} 表格")

            return sections, tables

        except Exception as e:
            logger.error(f"解析 Markdown 内容失败: {e}")
            raise

    def _parse_content_list(self, content_list: List[Dict], processed_images: Dict) -> Tuple[List[Tuple], List[Tuple]]:
        """
        解析 MinerU 的 content_list 结构化数据
        """
        sections = []
        tables = []

        try:
            for i, item in enumerate(content_list):
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type", "text").lower()
                content = item.get("content", "").strip()

                if not content:
                    continue

                if item_type in ["text", "paragraph", "heading", "title"]:
                    # 文本段落
                    # 生成简单的位置标记（用于兼容 RAGFlow）
                    position_marker = f"@@{i}\t0\t1000\t{i * 100}\t{(i + 1) * 100}##"
                    text_with_marker = f"{content}{position_marker}"
                    sections.append((text_with_marker, ""))

                elif item_type == "table":
                    # 表格内容
                    table_html = item.get("html", item.get("markdown", content))
                    if not table_html:
                        continue

                    # 如果是 Markdown 表格，转换为 HTML
                    if not table_html.strip().startswith("<"):
                        table_html = self._markdown_table_to_html(table_html)

                    tables.append(((None, table_html), ""))

                elif item_type == "image" and processed_images:
                    # 图片内容
                    image_filename = item.get("filename", item.get("src", ""))
                    if image_filename in processed_images:
                        image_info = processed_images[image_filename]
                        description = image_info.get("description", f"图片: {image_filename}")

                        position_marker = f"@@{i}\t0\t1000\t{i * 100}\t{(i + 1) * 100}##"
                        text_with_marker = f"{description}{position_marker}"
                        sections.append((text_with_marker, ""))

                # 可以根据需要添加更多类型的处理

        except Exception as e:
            logger.error(f"解析 content_list 失败: {e}")

        return sections, tables

    def _parse_raw_markdown(self, markdown_content: str, processed_images: Dict) -> Tuple[List[Tuple], List[Tuple]]:
        """
        解析原始 Markdown 文本
        """
        sections = []
        tables = []

        try:
            # 按行分析 Markdown
            lines = markdown_content.split("\n")

            current_paragraph = []
            current_table = []
            in_table = False
            line_index = 0

            for line in lines:
                line = line.strip()

                if not line:
                    # 空行，可能是段落分隔
                    if current_paragraph:
                        self._add_paragraph_to_sections(current_paragraph, line_index, sections)
                        current_paragraph = []
                    continue

                # 检测表格
                if self._is_table_line(line):
                    if not in_table:
                        # 开始新表格
                        if current_paragraph:
                            self._add_paragraph_to_sections(current_paragraph, line_index, sections)
                            current_paragraph = []
                        in_table = True
                        current_table = [line]
                    else:
                        # 继续表格
                        current_table.append(line)
                else:
                    if in_table:
                        # 表格结束
                        if current_table:
                            self._add_table_to_tables(current_table, tables)
                            current_table = []
                        in_table = False

                    # 检测图片引用
                    if self._contains_image_reference(line, processed_images):
                        # 处理图片
                        if current_paragraph:
                            self._add_paragraph_to_sections(current_paragraph, line_index, sections)
                            current_paragraph = []

                        image_description = self._extract_image_description(line, processed_images)
                        if image_description:
                            position_marker = f"@@{line_index}\t0\t1000\t{line_index * 100}\t{(line_index + 1) * 100}##"
                            text_with_marker = f"{image_description}{position_marker}"
                            sections.append((text_with_marker, ""))
                    else:
                        # 普通文本行
                        current_paragraph.append(line)

                line_index += 1

            # 处理剩余内容
            if current_table and in_table:
                self._add_table_to_tables(current_table, tables)

            if current_paragraph:
                self._add_paragraph_to_sections(current_paragraph, line_index, sections)

        except Exception as e:
            logger.error(f"解析原始 Markdown 失败: {e}")

        return sections, tables

    def _is_table_line(self, line: str) -> bool:
        """检测是否是表格行"""
        return "|" in line and line.count("|") >= 2

    def _contains_image_reference(self, line: str, processed_images: Dict) -> bool:
        """检测是否包含图片引用"""
        if not processed_images:
            return False

        # 检测 Markdown 图片语法
        if re.search(r"!\[.*?\]\(.*?\)", line):
            return True

        # 检测图片文件名
        for filename in processed_images.keys():
            if filename.lower() in line.lower():
                return True

        return False

    def _extract_image_description(self, line: str, processed_images: Dict) -> Optional[str]:
        """从行中提取图片描述"""
        # 匹配文件名
        for filename, image_info in processed_images.items():
            if filename.lower() in line.lower():
                return image_info.get("description", f"图片: {filename}")

        # 提取 Markdown 图片的 alt 文本
        match = re.search(r"!\[(.*?)\]", line)
        if match:
            alt_text = match.group(1)
            return f"图片: {alt_text}" if alt_text else "图片"

        return None

    def _add_paragraph_to_sections(self, paragraph_lines: List[str], line_index: int, sections: List):
        """将段落添加到 sections"""
        if not paragraph_lines:
            return

        paragraph_text = "\n".join(paragraph_lines).strip()
        if paragraph_text:
            position_marker = f"@@{line_index}\t0\t1000\t{line_index * 100}\t{(line_index + 1) * 100}##"
            text_with_marker = f"{paragraph_text}{position_marker}"
            sections.append((text_with_marker, ""))

    def _add_table_to_tables(self, table_lines: List[str], tables: List):
        """将表格添加到 tables"""
        if not table_lines:
            return

        table_html = self._markdown_table_to_html(table_lines)
        tables.append(((None, table_html), ""))

    def _markdown_table_to_html(self, table_lines) -> str:
        """
        将 Markdown 表格转换为 HTML
        """
        try:
            if isinstance(table_lines, str):
                table_lines = table_lines.split("\n")

            html_lines = ["<table>"]

            for i, line in enumerate(table_lines):
                line = line.strip()
                if not line or "|" not in line:
                    continue

                # 跳过分隔行（如 |---|----|）
                if re.match(r"^\|[\s\-\:]+\|", line):
                    continue

                # 提取单元格
                cells = [cell.strip() for cell in line.split("|")]
                cells = [cell for cell in cells if cell]  # 去掉空字符串

                if not cells:
                    continue

                # 第一行通常是表头
                tag = "th" if i == 0 else "td"
                html_lines.append("<tr>")
                for cell in cells:
                    html_lines.append(f"<{tag}>{cell}</{tag}>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            return "\n".join(html_lines)

        except Exception as e:
            logger.warning(f"Markdown 表格转换失败: {e}")
            # 返回原始内容
            if isinstance(table_lines, list):
                return "\n".join(table_lines)
            return str(table_lines)

    def _post_process_sections(self, sections: List[Tuple]) -> List[Tuple]:
        """
        后处理段落：清理、合并、优化
        """
        processed_sections = []

        for section in sections:
            if len(section) != 2:
                continue

            text, tag = section

            # 清理文本
            text = text.strip()
            if not text:
                continue

            # 移除多余的空行
            text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)

            # 清理 Markdown 标记
            text = self._clean_markdown_markers(text)

            processed_sections.append((text, tag))

        return processed_sections

    def _post_process_tables(self, tables: List[Tuple]) -> List[Tuple]:
        """
        后处理表格：清理、验证
        """
        processed_tables = []

        for table in tables:
            if len(table) != 2:
                continue

            table_data, tag = table

            if isinstance(table_data, tuple) and len(table_data) == 2:
                image, html = table_data

                # 清理 HTML
                html = self._clean_table_html(html)

                if html and html.strip():
                    processed_tables.append(((image, html), tag))

        return processed_tables

    def _clean_markdown_markers(self, text: str) -> str:
        """清理 Markdown 标记"""
        try:
            # 清理标题标记
            text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

            # 清理粗体和斜体标记
            text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
            text = re.sub(r"\*(.*?)\*", r"\1", text)

            # 清理链接标记
            text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

            return text

        except Exception as e:
            logger.warning(f"清理 Markdown 标记失败: {e}")
            return text

    def _clean_table_html(self, html: str) -> str:
        """清理表格 HTML"""
        try:
            if not html or not html.strip():
                return html

            # 简单的 HTML 清理
            html = html.strip()

            # 确保表格标签完整
            if not html.startswith("<table"):
                html = f"<table>{html}</table>"

            return html

        except Exception as e:
            logger.warning(f"清理表格 HTML 失败: {e}")
            return html


# 工厂函数
def create_mineru_parser(config: Optional[Dict[str, Any]] = None) -> MinerUParser:
    """
    创建 MinerU Markdown 解析器实例

    Args:
        config: 配置字典

    Returns:
        MinerUMarkdownParser 实例
    """
    return MinerUParser(config)


# 简化的使用接口
def parse_with_mineru(filename: str, binary: Optional[bytes] = None, config: Optional[Dict[str, Any]] = None, callback=None) -> Tuple[List[Tuple], List[Tuple]]:
    """
    使用 MinerU 解析文档的简化接口

    Args:
        filename: 文件名或路径
        binary: 文件二进制内容
        config: MinerU 配置
        callback: 进度回调

    Returns:
        Tuple[sections, tables]: 解析结果
    """
    parser = create_mineru_parser(config)
    return parser.parse(filename, binary, callback=callback)
