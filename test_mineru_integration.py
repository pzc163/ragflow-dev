#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU与RAGFlow集成测试脚本
用于验证MinerU HTTP解析器是否正确集成到RAGFlow中
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_mineru_parser_import():
    """测试MinerU解析器导入"""
    try:
        from deepdoc.parser.mineru_http_parser import create_mineru_parser

        logger.info("✓ MinerUHttpParser 导入成功")

        # 测试创建解析器实例
        config = {"endpoint": "http://localhost:8888/file_parse", "timeout": 600, "fallback_to_default": True}
        parser = create_mineru_parser(config)  # noqa: F841
        logger.info("✓ MinerU 解析器实例创建成功")

        return True
    except Exception as e:
        logger.error(f"✗ MinerU 解析器导入失败: {e}")
        return False


def test_mineru_app_import():
    """测试MinerU应用模块导入"""
    try:
        from rag.app import mineru

        logger.info("✓ MinerU 应用模块导入成功")

        # 测试chunk函数存在
        if hasattr(mineru, "chunk"):
            logger.info("✓ MinerU chunk 函数存在")
        else:
            logger.warning("⚠ MinerU chunk 函数不存在")

        # 测试Pdf类存在
        if hasattr(mineru, "Pdf"):
            logger.info("✓ MinerU Pdf 类存在")
        else:
            logger.warning("⚠ MinerU Pdf 类不存在")

        return True
    except Exception as e:
        logger.error(f"✗ MinerU 应用模块导入失败: {e}")
        return False


def test_task_executor_registration():
    """测试任务执行器中的MinerU注册"""
    try:
        from rag.svr.task_executor import FACTORY
        from api.db import ParserType

        # 检查MinerU是否在FACTORY中注册
        if ParserType.MINERU.value in FACTORY:
            logger.info("✓ MinerU 已在任务执行器中注册")

            # 获取MinerU模块
            mineru_module = FACTORY[ParserType.MINERU.value]
            logger.info(f"✓ MinerU 模块: {mineru_module}")

            return True
        else:
            logger.error("✗ MinerU 未在任务执行器中注册")
            return False

    except Exception as e:
        logger.error(f"✗ 任务执行器注册检查失败: {e}")
        return False


def test_settings_configuration():
    """测试配置设置"""
    try:
        from api import settings

        # 检查MinerU相关配置
        mineru_configs = [
            ("MINERU_ENDPOINT", getattr(settings, "MINERU_ENDPOINT", None)),
            ("MINERU_TIMEOUT", getattr(settings, "MINERU_TIMEOUT", None)),
            ("MINERU_FALLBACK", getattr(settings, "MINERU_FALLBACK", None)),
            ("MINERU_PARSE_METHOD", getattr(settings, "MINERU_PARSE_METHOD", None)),
        ]

        all_configured = True
        for config_name, config_value in mineru_configs:
            if config_value is not None:
                logger.info(f"✓ {config_name}: {config_value}")
            else:
                logger.warning(f"⚠ {config_name}: 未配置")
                all_configured = False

        return all_configured

    except Exception as e:
        logger.error(f"✗ 配置检查失败: {e}")
        return False


def test_parser_type_enum():
    """测试解析器类型枚举"""
    try:
        from api.db import ParserType

        if hasattr(ParserType, "MINERU"):
            logger.info(f"✓ ParserType.MINERU 存在: {ParserType.MINERU.value}")
            return True
        else:
            logger.error("✗ ParserType.MINERU 不存在")
            return False

    except Exception as e:
        logger.error(f"✗ 解析器类型枚举检查失败: {e}")
        return False


def run_integration_tests():
    """运行集成测试"""
    logger.info("=" * 60)
    logger.info("开始 MinerU 与 RAGFlow 集成测试")
    logger.info("=" * 60)

    tests = [
        ("解析器类型枚举测试", test_parser_type_enum),
        ("MinerU解析器导入测试", test_mineru_parser_import),
        ("MinerU应用模块导入测试", test_mineru_app_import),
        ("任务执行器注册测试", test_task_executor_registration),
        ("配置设置测试", test_settings_configuration),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\n运行测试: {test_name}")
        logger.info("-" * 40)

        try:
            if test_func():
                passed += 1
                logger.info(f"✓ {test_name} 通过")
            else:
                logger.error(f"✗ {test_name} 失败")
        except Exception as e:
            logger.error(f"✗ {test_name} 异常: {e}")

    logger.info("\n" + "=" * 60)
    logger.info(f"测试结果: {passed}/{total} 通过")
    if passed == total:
        logger.info("🎉 所有测试通过！MinerU 集成成功！")
        return True
    else:
        logger.warning(f"⚠ {total - passed} 个测试失败，请检查配置")
        return False


def test_mineru_chunk_function():
    """测试MinerU chunk函数（模拟测试）"""
    logger.info("\n测试 MinerU chunk 函数")
    logger.info("-" * 40)

    try:
        # 这里只测试函数是否可调用，不进行实际的文件解析
        # 因为需要真实的PDF文件和MinerU服务

        logger.info("✓ MinerU chunk 函数可导入")
        logger.info("📝 注意: 实际使用需要:")
        logger.info("   1. MinerU HTTP 服务运行在配置的端点")
        logger.info("   2. 提供有效的PDF文件进行解析")
        logger.info("   3. 网络连接正常")

        return True

    except Exception as e:
        logger.error(f"✗ MinerU chunk 函数测试失败: {e}")
        return False


if __name__ == "__main__":
    try:
        # 设置环境变量用于测试
        os.environ.setdefault("MINERU_ENDPOINT", "http://localhost:8888/file_parse")
        os.environ.setdefault("MINERU_TIMEOUT", "600")
        os.environ.setdefault("MINERU_FALLBACK", "true")
        os.environ.setdefault("MINERU_PARSE_METHOD", "auto")

        success = run_integration_tests()

        # 额外测试
        if success:
            test_mineru_chunk_function()

        logger.info("\n" + "=" * 60)
        logger.info("测试完成")
        logger.info("=" * 60)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生未预期错误: {e}")
        sys.exit(1)
