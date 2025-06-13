import { useTranslate } from '@/hooks/common-hooks';
import { Form, Space, Switch, Typography } from 'antd';
import { ChunkMethodItem, EmbeddingModelItem } from './common-item';

const { Text } = Typography;

export const MinerUConfiguration = () => {
  const { t } = useTranslate('knowledgeConfiguration');

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={20}>
      <EmbeddingModelItem />
      <ChunkMethodItem />

      <Form.Item
        name={['parser_config', 'mineru_fallback']}
        label={t('mineruFallback', 'MinerU 回退机制')}
        tooltip={t('mineruFallbackTip', '当 MinerU 服务不可用时，自动回退到标准解析器')}
        valuePropName="checked"
        initialValue={true}
      >
        <Switch />
      </Form.Item>

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

      <Text type="secondary" style={{ fontSize: '12px' }}>
        {t('mineruDescription', 'MinerU 使用先进的 PDF 解析技术，将 PDF 转换为高质量的 Markdown 格式，特别适合处理包含复杂表格和图表的学术文档。')}
      </Text>
    </Space>
  );
};
