/**
 * MinerU 切片方法配置组件
 * 
 * 📋 配置项分类：
 * 
 * 🔧 基础配置：
 * - 嵌入模型：用于向量化文档块
 * - 切片方法：选择解析策略
 * - 建议文本块大小：控制每个文档块的 token 数量
 * - 文本分段标识符：用于文档分割的分隔符
 * 
 * 🌐 MinerU API 配置：
 * - API 端点：MinerU 服务地址
 * - API 超时时间：防止长时间等待
 * - 解析方法：auto/ocr/txt 三种策略
 * - 回退机制：服务不可用时的降级策略
 * 
 * 📄 内容处理配置：
 * - 处理图片：是否提取和处理图片
 * - 返回内容列表：结构化内容输出
 * - 返回布局信息：保留文档布局结构
 * - 返回解析信息：调试和监控用途
 * - 调试模式：详细日志输出
 * 
 * 🎯 RAGFlow 通用配置：
 * - 页面排名：文档重要性评分
 * - 自动关键词提取：提升检索精度
 * - 自动问题提取：增强问答能力
 * 
 * ❌ 不支持的配置：
 * - 布局识别：MinerU 有自己的解析逻辑
 * - 表格转HTML：专门针对 Excel 文件
 * - 页面范围：MinerU 处理完整文档
 */

import { useTranslate } from '@/hooks/common-hooks';
import { Form, Space, Switch, Typography, Input, InputNumber, Select, Slider } from 'antd';
import { ChunkMethodItem, EmbeddingModelItem } from './common-item';
import MaxTokenNumber from '@/components/max-token-number';
import Delimiter from '@/components/delimiter';
import { AutoKeywordsItem, AutoQuestionsItem } from '@/components/auto-keywords-item';
import PageRank from '@/components/page-rank';
import { DatasetConfigurationContainer } from '@/components/dataset-configuration-container';
import { Divider } from 'antd';

const { Text } = Typography;

export const MinerUConfiguration = () => {
  const { t } = useTranslate('knowledgeConfiguration');

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={20}>
      {/* 基础配置 */}
      <DatasetConfigurationContainer>
        <EmbeddingModelItem />
        <ChunkMethodItem />
        <MaxTokenNumber />
        <Delimiter />
      </DatasetConfigurationContainer>

      <Divider />

      {/* MinerU 特有配置 */}
      <DatasetConfigurationContainer>
        <Form.Item
          name={['parser_config', 'mineru_endpoint']}
          label={t('mineruEndpoint', 'MinerU API 端点')}
          tooltip={t('mineruEndpointTip', '指定 MinerU 服务的 API 地址')}
          initialValue="http://172.19.0.3:8081/file_parse"
        >
          <Input placeholder="http://172.19.0.3:8081/file_parse" />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'mineru_timeout']}
          label={t('mineruTimeout', 'API 超时时间')}
          tooltip={t('mineruTimeoutTip', '设置 MinerU API 调用的超时时间（秒）')}
          initialValue={600}
        >
          <InputNumber min={30} max={3600} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'parse_method']}
          label={t('parseMethod', '解析方法')}
          tooltip={t('parseMethodTip', '选择 MinerU 的解析策略')}
          initialValue="auto"
        >
          <Select
            options={[
              { value: 'auto', label: t('parseMethodAuto', '自动选择') },
              { value: 'ocr', label: t('parseMethodOcr', 'OCR 解析') },
              { value: 'txt', label: t('parseMethodTxt', '文本提取') }
            ]}
          />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'mineru_fallback']}
          label={t('mineruFallback', 'MinerU 回退机制')}
          tooltip={t('mineruFallbackTip', '当 MinerU 服务不可用时，自动回退到标准解析器')}
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>
      </DatasetConfigurationContainer>

      <Divider />

      {/* 内容处理配置 */}
      <DatasetConfigurationContainer>
        <Form.Item
          name={['parser_config', 'process_images']}
          label={t('processImages', '处理图片')}
          tooltip={t('processImagesTip', '是否处理文档中的图片内容')}
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'return_content_list']}
          label={t('returnContentList', '返回内容列表')}
          tooltip={t('returnContentListTip', '是否返回结构化的内容列表')}
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'return_layout']}
          label={t('returnLayout', '返回布局信息')}
          tooltip={t('returnLayoutTip', '是否返回文档的布局结构信息')}
          valuePropName="checked"
          initialValue={false}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'return_info']}
          label={t('returnInfo', '返回解析信息')}
          tooltip={t('returnInfoTip', '是否返回详细的解析过程信息')}
          valuePropName="checked"
          initialValue={false}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name={['parser_config', 'enable_debug']}
          label={t('enableDebug', '调试模式')}
          tooltip={t('enableDebugTip', '启用调试模式以获取详细的处理信息')}
          valuePropName="checked"
          initialValue={false}
        >
          <Switch />
        </Form.Item>
      </DatasetConfigurationContainer>

      <Divider />

      {/* RAGFlow 通用配置 */}
      <DatasetConfigurationContainer>
        <PageRank />
        <AutoKeywordsItem />
        <AutoQuestionsItem />
      </DatasetConfigurationContainer>

      <Text type="secondary" style={{ fontSize: '12px' }}>
        {t('mineruDescription', 'MinerU 使用先进的 PDF 解析技术，将 PDF 转换为高质量的 Markdown 格式，特别适合处理包含复杂表格和图表的学术文档。')}
      </Text>
    </Space>
  );
};
