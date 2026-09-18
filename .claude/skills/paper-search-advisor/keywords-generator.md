# 关键词生成规则

## 关键词生成逻辑

### 基础词生成规则
从用户输入中提取：
- 核心概念（通常是名词）
- 领域标签（医学、AI等）
- 技术术语（RAG、LLM等）

例：
- 输入："医学领域的RAG系统"
- 提取：["医学", "RAG", "系统"]

### 方法词生成规则
根据核心词推导相关方法：
- 如果提到"RAG"，推导："检索增强生成", "retrieval augmented generation"
- 如果提到"医学"，推导："诊断", "临床", "治疗"
- 如果提到"AI/NLP"，推导："深度学习", "神经网络", "Transformer"

### 应用词生成规则
根据领域推导应用场景：
- 医学 + RAG → "医学问答", "临床决策支持", "病历分析"
- AI + 医学 → "医学诊断", "医学影像", "电子病历处理"

### 评估词生成规则
根据任务推导评估指标：
- 问答任务 → "准确率", "F1", "ROUGE", "BLEU"
- 检索任务 → "召回率", "精准率", "MRR", "NDCG"
- 医学任务 → "灵敏度", "特异性", "诊断准确率"

---

## 关键词扩展策略

### 英文扩展
将中文关键词翻译为英文版本：
- 医学 → Medical, Medicine
- RAG → Retrieval Augmented Generation
- 问答 → Question Answering, QA

### 同义词扩展
使用同义词和近义词：
- 医学 → Healthcare, Biomedical, Clinical
- 问答系统 → QA System, Question Answering System, QA Engine

### 上下位词扩展
使用更通用或更具体的词：
- RAG → Information Retrieval, Machine Learning, Natural Language Processing
- 医学诊断 → Medical AI, Clinical Decision Support

### 缩写形式
常用缩写的展开和组合：
- RAG, LLM, QA, NLP, NER, SVM

---

## 关键词组合规则

### 基础组合
用 AND 连接必须同时出现的词：
- `RAG AND 医学`
- `医学 AND 问答`

### 扩展组合
用 OR 连接可选择的词：
- `(医学 OR 临床 OR 生物医学)`
- `(RAG OR 检索增强) AND (问答 OR QA)`

### 复杂组合
混合使用 AND / OR / NOT：
- `(RAG OR 检索增强) AND (医学 OR 临床) AND NOT opinion`

---

## 按数据库定制关键词

### PubMed 特定关键词
- 使用 MeSH 关键词
- 加入医学特定术语
- 例：`[MeSH Terms] AND Medical AND Question Answering`

### arXiv 特定关键词
- 使用 CS（计算机科学）相关术语
- 加入方法名称
- 例：`cat:cs.NLP AND RAG`

### OpenAlex 特定关键词
- 可使用结构化查询
- 按学科、年份组织
- 例：`has_fulltext:true AND year >= 2021`

---