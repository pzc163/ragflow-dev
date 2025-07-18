#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
import os
import random
import xxhash
from datetime import datetime
from typing import Optional

from api.db.db_utils import bulk_insert_into_db
from deepdoc.parser import PdfParser  # noqa: F401
from peewee import JOIN
from api.db.db_models import DB, File2Document, File
from api.db import StatusEnum, FileType, TaskStatus
from api.db.db_models import Task, Document, Knowledgebase, Tenant
from api.db.services.common_service import CommonService
from api.db.services.document_service import DocumentService
from api.utils import current_timestamp, get_uuid
from deepdoc.parser.excel_parser import RAGFlowExcelParser
from rag.settings import get_svr_queue_name
from rag.utils.storage_factory import STORAGE_IMPL
from rag.utils.redis_conn import REDIS_CONN
from api import settings
from rag.nlp import search


def _check_mineru_service_availability() -> tuple[bool, str]:
    """检查 MinerU 服务是否可用

    Returns:
        tuple[bool, str]: (是否可用, 状态消息)
    """
    try:
        # 导入这里避免循环导入
        from rag.app.mineru import is_mineru_service_available

        if is_mineru_service_available():
            return True, "MinerU 服务可用"
        else:
            return False, "MinerU 服务不可用，请检查服务状态"
    except ImportError:
        return False, "MinerU 模块导入失败"
    except Exception as e:
        return False, f"MinerU 服务检查失败: {str(e)}"


def trim_header_by_lines(text: str, max_length) -> str:
    # Trim header text to maximum length while preserving line breaks
    # Args:
    #     text: Input text to trim
    #     max_length: Maximum allowed length
    # Returns:
    #     Trimmed text
    len_text = len(text)
    if len_text <= max_length:
        return text
    for i in range(len_text):
        if text[i] == "\n" and len_text - i <= max_length:
            return text[i + 1 :]
    return text


class TaskService(CommonService):
    """Service class for managing document processing tasks.

    This class extends CommonService to provide specialized functionality for document
    processing task management, including task creation, progress tracking, and chunk
    management. It handles various document types (PDF, Excel, etc.) and manages their
    processing lifecycle.

    The class implements a robust task queue system with retry mechanisms and progress
    tracking, supporting both synchronous and asynchronous task execution.

    Attributes:
        model: The Task model class for database operations.
    """

    model = Task

    @classmethod
    @DB.connection_context()
    def get_task(cls, task_id):
        """Retrieve detailed task information by task ID.

        This method fetches comprehensive task details including associated document,
        knowledge base, and tenant information. It also handles task retry logic and
        progress updates.

        Args:
            task_id (str): The unique identifier of the task to retrieve.

        Returns:
            dict: Task details dictionary containing all task information and related metadata.
                 Returns None if task is not found or has exceeded retry limit.
        """
        fields = [
            cls.model.id,
            cls.model.doc_id,
            cls.model.from_page,
            cls.model.to_page,
            cls.model.retry_count,
            Document.kb_id,
            Document.parser_id,
            Document.parser_config,
            Document.name,
            Document.type,
            Document.location,
            Document.size,
            Knowledgebase.tenant_id,
            Knowledgebase.language,
            Knowledgebase.embd_id,
            Knowledgebase.pagerank,
            Knowledgebase.parser_config.alias("kb_parser_config"),
            Tenant.img2txt_id,
            Tenant.asr_id,
            Tenant.llm_id,
            cls.model.update_time,
        ]
        docs = (
            cls.model.select(*fields)
            .join(Document, on=(cls.model.doc_id == Document.id))
            .join(Knowledgebase, on=(Document.kb_id == Knowledgebase.id))
            .join(Tenant, on=(Knowledgebase.tenant_id == Tenant.id))
            .where(cls.model.id == task_id)
        )
        docs = list(docs.dicts())
        if not docs:
            return None

        msg = f"\n{datetime.now().strftime('%H:%M:%S')} Task has been received."
        prog = random.random() / 10.0
        if docs[0]["retry_count"] >= 3:
            msg = "\nERROR: Task is abandoned after 3 times attempts."
            prog = -1

        cls.model.update(
            progress_msg=cls.model.progress_msg + msg,
            progress=prog,
            retry_count=docs[0]["retry_count"] + 1,
        ).where(cls.model.id == docs[0]["id"]).execute()

        if docs[0]["retry_count"] >= 3:
            return None

        return docs[0]

    @classmethod
    @DB.connection_context()
    def get_tasks(cls, doc_id: str):
        """Retrieve all tasks associated with a document.

        This method fetches all processing tasks for a given document, ordered by page
        number and creation time. It includes task progress and chunk information.

        Args:
            doc_id (str): The unique identifier of the document.

        Returns:
            list[dict]: List of task dictionaries containing task details.
                       Returns None if no tasks are found.
        """
        fields = [
            cls.model.id,
            cls.model.from_page,
            cls.model.progress,
            cls.model.digest,
            cls.model.chunk_ids,
        ]
        tasks = cls.model.select(*fields).order_by(cls.model.from_page.asc(), cls.model.create_time.desc()).where(cls.model.doc_id == doc_id)
        tasks = list(tasks.dicts())
        if not tasks:
            return None
        return tasks

    @classmethod
    @DB.connection_context()
    def update_chunk_ids(cls, id: str, chunk_ids: str):
        """Update the chunk IDs associated with a task.

        This method updates the chunk_ids field of a task, which stores the IDs of
        processed document chunks in a space-separated string format.

        Args:
            id (str): The unique identifier of the task.
            chunk_ids (str): Space-separated string of chunk identifiers.
        """
        cls.model.update(chunk_ids=chunk_ids).where(cls.model.id == id).execute()

    @classmethod
    @DB.connection_context()
    def get_ongoing_doc_name(cls):
        """Get names of documents that are currently being processed.

        This method retrieves information about documents that are in the processing state,
        including their locations and associated IDs. It uses database locking to ensure
        thread safety when accessing the task information.

        Returns:
            list[tuple]: A list of tuples, each containing (parent_id/kb_id, location)
                        for documents currently being processed. Returns empty list if
                        no documents are being processed.
        """
        with DB.lock("get_task", -1):
            docs = (
                cls.model.select(*[Document.id, Document.kb_id, Document.location, File.parent_id])
                .join(Document, on=(cls.model.doc_id == Document.id))
                .join(
                    File2Document,
                    on=(File2Document.document_id == Document.id),
                    join_type=JOIN.LEFT_OUTER,
                )
                .join(
                    File,
                    on=(File2Document.file_id == File.id),
                    join_type=JOIN.LEFT_OUTER,
                )
                .where(
                    Document.status == StatusEnum.VALID.value,
                    Document.run == TaskStatus.RUNNING.value,
                    ~(Document.type == FileType.VIRTUAL.value),
                    cls.model.progress < 1,
                    cls.model.create_time >= current_timestamp() - 1000 * 600,
                )
            )
            docs = list(docs.dicts())
            if not docs:
                return []

            return list(
                set(
                    [
                        (
                            d["parent_id"] if d["parent_id"] else d["kb_id"],
                            d["location"],
                        )
                        for d in docs
                    ]
                )
            )

    @classmethod
    @DB.connection_context()
    def do_cancel(cls, id):
        """Check if a task should be cancelled based on its document status.

        This method determines whether a task should be cancelled by checking the
        associated document's run status and progress. A task should be cancelled
        if its document is marked for cancellation or has negative progress.

        Args:
            id (str): The unique identifier of the task to check.

        Returns:
            bool: True if the task should be cancelled, False otherwise.
        """
        task = cls.model.get_by_id(id)
        _, doc = DocumentService.get_by_id(task.doc_id)
        return doc.run == TaskStatus.CANCEL.value or doc.progress < 0

    @classmethod
    @DB.connection_context()
    def update_progress(cls, id, info):
        """Update the progress information for a task.

        This method updates both the progress message and completion percentage of a task.
        It handles platform-specific behavior (macOS vs others) and uses database locking
        when necessary to ensure thread safety.

        Args:
            id (str): The unique identifier of the task to update.
            info (dict): Dictionary containing progress information with keys:
                        - progress_msg (str, optional): Progress message to append
                        - progress (float, optional): Progress percentage (0.0 to 1.0)
        """
        if os.environ.get("MACOS"):
            if info["progress_msg"]:
                task = cls.model.get_by_id(id)
                progress_msg = trim_header_by_lines(task.progress_msg + "\n" + info["progress_msg"], 3000)
                cls.model.update(progress_msg=progress_msg).where(cls.model.id == id).execute()
            if "progress" in info:
                cls.model.update(progress=info["progress"]).where(cls.model.id == id).execute()
            return

        with DB.lock("update_progress", -1):
            if info["progress_msg"]:
                task = cls.model.get_by_id(id)
                progress_msg = trim_header_by_lines(task.progress_msg + "\n" + info["progress_msg"], 3000)
                cls.model.update(progress_msg=progress_msg).where(cls.model.id == id).execute()
            if "progress" in info:
                cls.model.update(progress=info["progress"]).where(cls.model.id == id).execute()

    @classmethod
    @DB.connection_context()
    def get_mineru_task_details(cls, task_id: str) -> Optional[dict]:
        """获取 MinerU 任务的详细信息

        Args:
            task_id (str): 任务 ID

        Returns:
            dict: MinerU 任务详细信息，如果不是 MinerU 任务或任务不存在则返回 None
        """
        try:
            fields = [
                cls.model.id,
                cls.model.doc_id,
                cls.model.from_page,
                cls.model.to_page,
                cls.model.progress,
                cls.model.progress_msg,
                cls.model.retry_count,
                cls.model.chunk_ids,
                cls.model.digest,
                cls.model.create_time,
                cls.model.update_time,
                Document.parser_id,
                Document.name,
                Document.size,
                Document.type,
                Document.parser_config,
                Knowledgebase.tenant_id,
                Knowledgebase.language,
            ]

            task = (
                cls.model.select(*fields)
                .join(Document, on=(cls.model.doc_id == Document.id))
                .join(Knowledgebase, on=(Document.kb_id == Knowledgebase.id))
                .where(cls.model.id == task_id, Document.parser_id == "mineru")
                .first()
            )

            if not task:
                return None

            task_dict = task.__dict__["__data__"]

            # 计算额外的 MinerU 特定信息
            task_dict["is_completed"] = task_dict["progress"] >= 1.0
            task_dict["is_failed"] = task_dict["progress"] < 0
            task_dict["is_running"] = 0 < task_dict["progress"] < 1.0

            # 解析 chunk_ids
            if task_dict["chunk_ids"]:
                chunk_list = task_dict["chunk_ids"].split()
                task_dict["chunk_count"] = len(chunk_list)
                task_dict["chunk_list"] = chunk_list
            else:
                task_dict["chunk_count"] = 0
                task_dict["chunk_list"] = []

            # 计算预计剩余时间（简单估算）
            if task_dict["is_running"]:
                elapsed_time = (datetime.now() - task_dict["update_time"]).total_seconds()
                if task_dict["progress"] > 0:
                    estimated_total_time = elapsed_time / task_dict["progress"]
                    estimated_remaining_time = estimated_total_time * (1 - task_dict["progress"])
                    task_dict["estimated_remaining_seconds"] = int(estimated_remaining_time)
                else:
                    task_dict["estimated_remaining_seconds"] = None
            else:
                task_dict["estimated_remaining_seconds"] = None

            return task_dict

        except Exception as e:
            return {"error": f"获取 MinerU 任务详情失败: {str(e)}"}


def queue_tasks(doc: dict, bucket: str, name: str, priority: int):
    """Create and queue document processing tasks.

    This function creates processing tasks for a document based on its type and configuration.
    It handles different document types (PDF, Excel, etc.) differently and manages task
    chunking and configuration. It also implements task reuse optimization by checking
    for previously completed tasks.

    Args:
        doc (dict): Document dictionary containing metadata and configuration.
        bucket (str): Storage bucket name where the document is stored.
        name (str): File name of the document.
        priority (int, optional): Priority level for task queueing (default is 0).

    Note:
        - For PDF documents, tasks are created per page range based on configuration
        - For Excel documents, tasks are created per row range
        - For MinerU documents, a single task processes the entire PDF document
        - Task digests are calculated for optimization and reuse
        - Previous task chunks may be reused if available

    Parser-specific behavior:
        - "pdf": Standard PDF parsing with page-based task splitting
        - "table": Excel/spreadsheet parsing with row-based task splitting
        - "mineru": MinerU Markdown-based PDF processing (single task per document)
        - Others: Single task processing
    """

    def new_task():
        return {"id": get_uuid(), "doc_id": doc["id"], "progress": 0.0, "from_page": 0, "to_page": 100000000}

    parse_task_array = []

    if doc["type"] == FileType.PDF.value:
        file_bin = STORAGE_IMPL.get(bucket, name)
        do_layout = doc["parser_config"].get("layout_recognize", "DeepDOC")
        pages = PdfParser.total_page_number(doc["name"], file_bin)
        page_size = doc["parser_config"].get("task_page_size", 12)
        if doc["parser_id"] == "paper":
            page_size = doc["parser_config"].get("task_page_size", 22)
        if doc["parser_id"] in ["one", "knowledge_graph"] or do_layout != "DeepDOC":
            page_size = 10**9
        page_ranges = doc["parser_config"].get("pages") or [(1, 10**5)]
        for s, e in page_ranges:
            s -= 1
            s = max(0, s)
            e = min(e - 1, pages)
            for p in range(s, e, page_size):
                task = new_task()
                task["from_page"] = p
                task["to_page"] = min(p + page_size, e)
                parse_task_array.append(task)

    elif doc["parser_id"] == "table":
        file_bin = STORAGE_IMPL.get(bucket, name)
        rn = RAGFlowExcelParser.row_number(doc["name"], file_bin)
        for i in range(0, rn, 3000):
            task = new_task()
            task["from_page"] = i
            task["to_page"] = min(i + 3000, rn)
            parse_task_array.append(task)

    elif doc["parser_id"] == "mineru":
        # MinerU 专用处理逻辑：PDF → Markdown → 结构化处理
        # 验证文件类型，MinerU 主要处理 PDF 文件
        if doc["type"] != FileType.PDF.value:
            raise ValueError(f"MinerU 解析器主要支持 PDF 文件，当前文件类型: {doc['type']}")

        # 检查 MinerU 服务可用性
        service_available, service_msg = _check_mineru_service_availability()
        if not service_available:
            # 如果服务不可用，可以考虑回退到标准 PDF 解析器
            fallback_enabled = doc.get("parser_config", {}).get("mineru_fallback", True)
            if fallback_enabled:
                # 记录警告但继续处理（将在实际执行时决定回退）
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"MinerU 服务不可用 ({service_msg})，任务将在执行时回退到标准解析器")
            else:
                raise RuntimeError(f"MinerU 服务不可用且未启用回退机制: {service_msg}")

        # 获取文件用于验证
        file_bin = STORAGE_IMPL.get(bucket, name)

        # 验证文件是否为有效的 PDF
        try:
            # 使用 PdfParser 验证 PDF 文件有效性
            total_pages = PdfParser.total_page_number(doc["name"], file_bin)
            if total_pages <= 0:
                raise ValueError("PDF 文件页数无效")
        except Exception as e:
            raise ValueError(f"PDF 文件验证失败: {str(e)}")

        # MinerU 处理整个文档，不需要分页
        # 创建单个任务处理整个文档
        task = new_task()
        task["from_page"] = 0
        task["to_page"] = total_pages  # 设置实际页数而不是默认的大数

        # 添加 MinerU 特定的任务元数据
        task["parser_type"] = "mineru_markdown"
        task["total_pages"] = total_pages
        task["file_size"] = doc.get("size", 0)
        task["service_available"] = service_available
        task["service_check_msg"] = service_msg

        # 根据文件大小调整任务优先级（大文件可能需要更长处理时间）
        file_size = doc.get("size", 0)
        if file_size > 50 * 1024 * 1024:  # 50MB 以上
            task["estimated_time"] = "long"  # 标记为长时间任务
            task["timeout_multiplier"] = 3.0  # 增加超时倍数
        elif file_size > 10 * 1024 * 1024:  # 10MB 以上
            task["estimated_time"] = "medium"
            task["timeout_multiplier"] = 2.0
        else:
            task["estimated_time"] = "short"
            task["timeout_multiplier"] = 1.0

        # 将 MinerU 特定配置传递给任务
        mineru_config = doc.get("parser_config", {}).get("mineru_config", {})
        if mineru_config:
            task["mineru_config"] = mineru_config

        parse_task_array.append(task)
    else:
        parse_task_array.append(new_task())

    chunking_config = DocumentService.get_chunking_config(doc["id"])
    for task in parse_task_array:
        hasher = xxhash.xxh64()
        for field in sorted(chunking_config.keys()):
            if field == "parser_config":
                for k in ["raptor", "graphrag"]:
                    if k in chunking_config[field]:
                        del chunking_config[field][k]
            hasher.update(str(chunking_config[field]).encode("utf-8"))
        for field in ["doc_id", "from_page", "to_page"]:
            hasher.update(str(task.get(field, "")).encode("utf-8"))
        task_digest = hasher.hexdigest()
        task["digest"] = task_digest
        task["progress"] = 0.0
        task["priority"] = priority

    prev_tasks = TaskService.get_tasks(doc["id"])
    ck_num = 0
    if prev_tasks:
        for task in parse_task_array:
            ck_num += reuse_prev_task_chunks(task, prev_tasks, chunking_config)
        TaskService.filter_delete([Task.doc_id == doc["id"]])
        chunk_ids = []
        for task in prev_tasks:
            if task["chunk_ids"]:
                chunk_ids.extend(task["chunk_ids"].split())
        if chunk_ids:
            settings.docStoreConn.delete({"id": chunk_ids}, search.index_name(chunking_config["tenant_id"]), chunking_config["kb_id"])
    DocumentService.update_by_id(doc["id"], {"chunk_num": ck_num})

    bulk_insert_into_db(Task, parse_task_array, True)
    DocumentService.begin2parse(doc["id"])

    unfinished_task_array = [task for task in parse_task_array if task["progress"] < 1.0]

    # 针对 MinerU 任务的特殊处理
    for unfinished_task in unfinished_task_array:
        task_priority = priority

        # MinerU 任务的优先级调整
        if doc["parser_id"] == "mineru":
            # 根据文件大小和估计处理时间调整优先级
            estimated_time = unfinished_task.get("estimated_time", "medium")
            if estimated_time == "short":
                # 小文件优先处理
                task_priority = max(0, priority - 1)
            elif estimated_time == "long":
                # 大文件降低优先级，避免阻塞其他任务
                task_priority = priority + 1

            # 如果服务不可用但有回退，降低优先级
            if not unfinished_task.get("service_available", True):
                task_priority = priority + 1

        assert REDIS_CONN.queue_product(get_svr_queue_name(task_priority), message=unfinished_task), "Can't access Redis. Please check the Redis' status."


def reuse_prev_task_chunks(task: dict, prev_tasks: list[dict], chunking_config: dict):
    """Attempt to reuse chunks from previous tasks for optimization.

    This function checks if chunks from previously completed tasks can be reused for
    the current task, which can significantly improve processing efficiency. It matches
    tasks based on page ranges and configuration digests.

    Args:
        task (dict): Current task dictionary to potentially reuse chunks for.
        prev_tasks (list[dict]): List of previous task dictionaries to check for reuse.
        chunking_config (dict): Configuration dictionary for chunk processing.

    Returns:
        int: Number of chunks successfully reused. Returns 0 if no chunks could be reused.

    Note:
        Chunks can only be reused if:
        - A previous task exists with matching page range and configuration digest
        - The previous task was completed successfully (progress = 1.0)
        - The previous task has valid chunk IDs
    """
    idx = 0
    while idx < len(prev_tasks):
        prev_task = prev_tasks[idx]
        if prev_task.get("from_page", 0) == task.get("from_page", 0) and prev_task.get("digest", 0) == task.get("digest", ""):
            break
        idx += 1

    if idx >= len(prev_tasks):
        return 0
    prev_task = prev_tasks[idx]
    if prev_task["progress"] < 1.0 or not prev_task["chunk_ids"]:
        return 0
    task["chunk_ids"] = prev_task["chunk_ids"]
    task["progress"] = 1.0
    if "from_page" in task and "to_page" in task and int(task["to_page"]) - int(task["from_page"]) >= 10**6:
        task["progress_msg"] = f"Page({task['from_page']}~{task['to_page']}): "
    else:
        task["progress_msg"] = ""
    task["progress_msg"] = " ".join([datetime.now().strftime("%H:%M:%S"), task["progress_msg"], "Reused previous task's chunks."])
    prev_task["chunk_ids"] = ""

    return len(task["chunk_ids"].split())


def get_mineru_task_stats(tenant_id: str = None) -> dict:
    """获取 MinerU 任务的统计信息

    Args:
        tenant_id (str, optional): 租户 ID，如果提供则只统计该租户的任务

    Returns:
        dict: MinerU 任务统计信息
    """
    try:
        from api.db.db_models import Task, Document, Knowledgebase

        # 构建查询条件
        query = (
            Task.select(Task, Document.parser_id, Document.size, Document.name)
            .join(Document, on=(Task.doc_id == Document.id))
            .join(Knowledgebase, on=(Document.kb_id == Knowledgebase.id))
            .where(Document.parser_id == "mineru")
        )

        if tenant_id:
            query = query.where(Knowledgebase.tenant_id == tenant_id)

        tasks = list(query.dicts())

        if not tasks:
            return {"total_tasks": 0, "completed_tasks": 0, "running_tasks": 0, "failed_tasks": 0, "total_documents": 0, "total_file_size": 0, "avg_file_size": 0, "completion_rate": 0.0}

        # 统计数据
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t["progress"] >= 1.0])
        running_tasks = len([t for t in tasks if 0 < t["progress"] < 1.0])
        failed_tasks = len([t for t in tasks if t["progress"] < 0])

        # 文档统计
        unique_docs = set(t["doc_id"] for t in tasks)
        total_documents = len(unique_docs)

        # 文件大小统计
        file_sizes = [t["size"] for t in tasks if t["size"]]
        total_file_size = sum(file_sizes) if file_sizes else 0
        avg_file_size = total_file_size / len(file_sizes) if file_sizes else 0

        # 完成率
        completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "running_tasks": running_tasks,
            "failed_tasks": failed_tasks,
            "total_documents": total_documents,
            "total_file_size": total_file_size,
            "avg_file_size": round(avg_file_size, 2),
            "completion_rate": round(completion_rate, 4),
            "summary": f"MinerU 任务总计 {total_tasks} 个，完成 {completed_tasks} 个（{completion_rate:.1%}），处理文档 {total_documents} 个，总大小 {total_file_size / (1024 * 1024):.1f}MB",
        }

    except Exception as e:
        return {"error": f"获取 MinerU 任务统计失败: {str(e)}", "total_tasks": 0, "completed_tasks": 0, "running_tasks": 0, "failed_tasks": 0}
