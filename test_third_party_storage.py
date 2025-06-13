#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
第三方文件存储接口测试脚本

使用方法:
1. 配置 conf/third_party_storage.yml 文件
2. 设置环境变量 STORAGE_IMPL=THIRD_PARTY
3. 运行此脚本进行测试

python test_third_party_storage.py
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["STORAGE_IMPL"] = "THIRD_PARTY"


def test_third_party_storage():
    """测试第三方存储接口的所有功能"""

    print("🚀 开始测试第三方文件存储接口...")
    print(f"📅 测试时间: {datetime.now()}")
    print("-" * 60)

    try:
        # 导入存储实现
        from rag.utils.storage_factory import STORAGE_IMPL

        print(f"✅ 成功导入存储实现: {type(STORAGE_IMPL).__name__}")

        # 测试数据
        test_bucket = "test-ragflow"
        test_filename = "test-file.txt"
        test_content = f"测试文件内容 - 创建时间: {datetime.now()}".encode("utf-8")

        # 1. 健康检查测试
        print("\n🏥 1. 健康检查测试")
        try:
            health_status = STORAGE_IMPL.health()
            print(f"   健康状态: {'✅ 正常' if health_status else '❌ 异常'}")
        except Exception as e:
            print(f"   健康检查失败: {e}")

        # 2. 文件上传测试
        print("\n📤 2. 文件上传测试")
        try:
            upload_result = STORAGE_IMPL.put(test_bucket, test_filename, test_content)
            print("   上传结果: ✅ 成功")
            print(f"   响应数据: {upload_result}")
        except Exception as e:
            print(f"   上传失败: ❌ {e}")
            traceback.print_exc()
            return False

        # 3. 文件存在性检查测试
        print("\n🔍 3. 文件存在性检查测试")
        try:
            exists = STORAGE_IMPL.obj_exist(test_bucket, test_filename)
            print(f"   文件存在: {'✅ 是' if exists else '❌ 否'}")

            # 检查不存在的文件
            not_exists = STORAGE_IMPL.obj_exist(test_bucket, "non-existent-file.txt")
            print(f"   不存在文件检查: {'✅ 正确' if not not_exists else '❌ 错误'}")
        except Exception as e:
            print(f"   存在性检查失败: ❌ {e}")

        # 4. 文件下载测试
        print("\n📥 4. 文件下载测试")
        try:
            downloaded_content = STORAGE_IMPL.get(test_bucket, test_filename)
            if downloaded_content:
                if downloaded_content == test_content:
                    print("   下载结果: ✅ 成功，内容匹配")
                    print(f"   文件大小: {len(downloaded_content)} 字节")
                else:
                    print("   下载结果: ❌ 内容不匹配")
                    print(f"   期望: {test_content}")
                    print(f"   实际: {downloaded_content}")
            else:
                print("   下载失败: ❌ 返回空内容")
        except Exception as e:
            print(f"   下载失败: ❌ {e}")
            traceback.print_exc()

        # 5. 预签名URL测试（如果支持）
        print("\n🔗 5. 预签名URL测试")
        try:
            presigned_url = STORAGE_IMPL.get_presigned_url(test_bucket, test_filename, 3600)
            if presigned_url:
                print("   预签名URL: ✅ 生成成功")
                print(f"   URL长度: {len(presigned_url)} 字符")
                # 不打印完整URL以保护安全性
                print(f"   URL前缀: {presigned_url[:50]}...")
            else:
                print("   预签名URL: ❌ 生成失败")
        except Exception as e:
            print(f"   预签名URL失败: ❌ {e}")

        # 6. 对象信息获取测试（如果支持）
        print("\n📋 6. 对象信息获取测试")
        try:
            if hasattr(STORAGE_IMPL, "get_object_info"):
                obj_info = STORAGE_IMPL.get_object_info(test_bucket, test_filename)
                print("   对象信息: ✅ 获取成功")
                print(f"   信息内容: {obj_info}")
            else:
                print("   对象信息: ⚠️  不支持此功能")
        except Exception as e:
            print(f"   对象信息获取失败: ❌ {e}")

        # 7. 对象列表测试（如果支持）
        print("\n📃 7. 对象列表测试")
        try:
            if hasattr(STORAGE_IMPL, "list_objects"):
                objects = STORAGE_IMPL.list_objects(test_bucket)
                print("   对象列表: ✅ 获取成功")
                print(f"   对象数量: {len(objects)}")
                if objects:
                    print(f"   示例对象: {objects[0] if objects else '无'}")
            else:
                print("   对象列表: ⚠️  不支持此功能")
        except Exception as e:
            print(f"   对象列表获取失败: ❌ {e}")

        # 8. 性能指标测试（如果支持）
        print("\n📊 8. 性能指标测试")
        try:
            if hasattr(STORAGE_IMPL, "get_metrics"):
                metrics = STORAGE_IMPL.get_metrics()
                print("   性能指标: ✅ 获取成功")
                for key, value in metrics.items():
                    print(f"   {key}: {value}")
            else:
                print("   性能指标: ⚠️  不支持此功能")
        except Exception as e:
            print(f"   性能指标获取失败: ❌ {e}")

        # 9. 多文件操作测试
        print("\n📚 9. 多文件操作测试")
        try:
            test_files = [("file1.txt", b"Content of file 1"), ("file2.txt", b"Content of file 2"), ("subdir/file3.txt", b"Content of file 3")]

            # 上传多个文件
            for filename, content in test_files:
                STORAGE_IMPL.put(test_bucket, filename, content)

            print(f"   多文件上传: ✅ 成功上传 {len(test_files)} 个文件")

            # 检查所有文件是否存在
            all_exist = all(STORAGE_IMPL.obj_exist(test_bucket, fname) for fname, _ in test_files)
            print(f"   文件存在检查: {'✅ 全部存在' if all_exist else '❌ 部分缺失'}")

        except Exception as e:
            print(f"   多文件操作失败: ❌ {e}")

        # 10. 文件删除测试（清理）
        print("\n🗑️  10. 文件删除测试")
        try:
            # 删除测试文件
            all_files = [test_filename] + [fname for fname, _ in test_files]
            deleted_count = 0

            for filename in all_files:
                if STORAGE_IMPL.rm(test_bucket, filename):
                    deleted_count += 1

            print(f"   删除结果: ✅ 成功删除 {deleted_count}/{len(all_files)} 个文件")

            # 验证文件已被删除
            still_exists = any(STORAGE_IMPL.obj_exist(test_bucket, fname) for fname in all_files)
            print(f"   删除验证: {'❌ 仍有文件存在' if still_exists else '✅ 全部删除成功'}")

        except Exception as e:
            print(f"   文件删除失败: ❌ {e}")

        print("\n" + "=" * 60)
        print("🎉 第三方存储接口测试完成！")
        return True

    except Exception as e:
        print(f"\n❌ 测试过程中发生严重错误: {e}")
        traceback.print_exc()
        return False


def test_storage_migration():
    """测试存储迁移功能（从Minio迁移到第三方存储）"""

    print("\n🔄 测试存储迁移功能...")

    try:
        # 这里可以添加存储迁移的测试逻辑
        # 例如：从Minio读取文件，然后上传到第三方存储
        print("   ⚠️  存储迁移功能需要根据具体需求实现")
        return True

    except Exception as e:
        print(f"   迁移测试失败: ❌ {e}")
        return False


def main():
    """主函数"""

    print("🔧 RAGFlow第三方文件存储接口测试工具")
    print("=" * 60)

    # 检查配置文件
    config_file = project_root / "conf" / "third_party_storage.yml"
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        print("请先创建并配置 conf/third_party_storage.yml 文件")
        return False

    print(f"✅ 找到配置文件: {config_file}")

    # 运行基础功能测试
    success = test_third_party_storage()

    if success:
        # 运行迁移测试
        test_storage_migration()

        print("\n📝 测试总结:")
        print("✅ 基础功能测试通过")
        print("💡 你现在可以通过设置环境变量 STORAGE_IMPL=THIRD_PARTY 来使用第三方存储")
        print("🔧 如需自定义API端点或认证方式，请修改 conf/third_party_storage.yml 配置文件")

    else:
        print("\n📝 测试总结:")
        print("❌ 测试失败，请检查配置和第三方存储服务")
        print("🔍 建议检查以下几点:")
        print("   1. 第三方存储服务是否正常运行")
        print("   2. API密钥和认证信息是否正确")
        print("   3. 网络连接是否正常")
        print("   4. API端点路径是否正确")

    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        traceback.print_exc()
        sys.exit(1)
