# Literature Mining Pipeline (生物医学文献挖掘与数据清洗流水线)

这是一个用于自动化检索、下载并解析生物医学文献的管道工具。该管道通过对接 NCBI PubMed 数据库和 PubTator 平台，并结合大语言模型 (DeepSeek-V3) 进行相关性校验，实现基于关键字的大规模文献检索、元数据下载、结构化清洗与智能分类。

## 🚀 项目结构与工作流

整个流水线由四个核心 Python 脚本组成，按顺序执行：

```mermaid
graph TD
    A[keywords.txt 检索词] --> B(01.get_pmid_from_keywords.py)
    B -->|按年份检索并合并| C[pmid_list.txt PMID列表]
    C --> D(02.get_article_jason_from_pmid.py)
    D -->|对接 PubTator API 批量下载| E[raw_api_responses.json 原始JSON]
    E --> F(03.extract_article_details_from_jason.py)
    F -->|解析文章元数据并清洗| G[extracted_articles.tsv 结构化数据集]
    G --> H(04.title_filter_deepseek_R3.py)
    H -->|DeepSeek-V3 智能相关性筛选| I[salt_alkali_relevant.tsv 目标文献]
```

### 📝 工作流示意图 / Workflow Diagram
![Workflow Diagram](pipeline_workflow.png)


### 1. 文献检索与 ID 提取 (`01.get_pmid_from_keywords.py`)
* **功能**：基于本地 `keywords.txt` 中配置的检索词，调用 NCBI Entrez API 检索自 1979 年至今的所有相关文献。
* **特点**：
  * 支持断点续传（通过 `progress.json` 记录进度，防止网络中断或配额限制导致前功尽弃）。
  * 自动将各年份检索到的 PMID 去重并合并输出至 `pmid_list.txt`。

### 2. 文献元数据下载 (`02.get_article_jason_from_pmid.py`)
* **功能**：读取 `pmid_list.txt`，将 PMID 分批次（默认每批 10 个）向 PubTator API 发送请求，下载包含文献标题和摘要等元数据的 biocJSON 原始数据。
* **特点**：
  * 控制请求延迟（`REQUEST_DELAY = 0.5s`）避免被 API 阻断。
  * 保存为原始响应 JSON 文件 `raw_api_responses.json`。

### 3. 数据解析与结构化导出 (`03.extract_article_details_from_jason.py`)
* **功能**：解析 `raw_api_responses.json`，提取文献基本元数据，生成结构化的 TSV 文件 `extracted_articles.tsv`。
* **提取字段**：PMID、Journal、Year、DOI、PMCID、Authors、Title、Abstract。

### 4. 大模型相关性筛选与分类 (`04.title_filter_deepseek_R3.py`)
* **功能**：调用 DeepSeek API，利用外部 Prompt 模板，综合评估文章的 `Title` 与 `Abstract`，识别文献是否属于特定的逆境胁迫研究。
* **特点**：
  * 采用双重外部配置：`config.json`（配置模型与 API）与 `prompt_templates.json`（配置英文提示词，易于迁移到其他研究方向）。
  * 全异步并发处理（使用 `asyncio` 和 `tenacity` 自动重试）。
  * 本地分类结果自动缓存（`{stress_type}_filter_cache.json`），节省 API 成本。
  * 自动将筛选结果分流保存到 `{stress_type}_relevant.tsv` 和 `{stress_type}_irrelevant.tsv` 中，并保留输入文件中的全部元数据列。

---

## 🛠️ 安装与配置

### 1. 安装依赖
克隆项目后，使用 pip 安装所需的第三方库：
```bash
pip install -r requirements.txt
```

### 2. 配置 NCBI 邮箱
在使用 Entrez API 前，请在 `01.get_pmid_from_keywords.py` 第 8 行配置您的有效邮箱地址（NCBI 要求）：
```python
Entrez.email = "your_email@example.com"
```

### 3. 创建检索词文件
在项目根目录下创建 `keywords.txt`，写入您需要检索的关键词组合。例如：
```text
(Salt stress OR Salinity) AND (Triticum aestivum OR Wheat)
```

### 4. 配置 API 与 Prompts
在运行筛选前，请确保在当前目录下配置好 `config.json`（填入您的 API 密钥）以及 `prompt_templates.json` 中的英文分类提示词。

---

## 📖 使用说明

按顺序运行以下四个脚本：

```bash
# 步骤 1: 检索文献并生成 PMID 列表
python 01.get_pmid_from_keywords.py

# 步骤 2: 下载文献元数据
python 02.get_article_jason_from_pmid.py

# 步骤 3: 提取结构化元数据表格
python 03.extract_article_details_from_jason.py

# 步骤 4: 大语言模型分类与筛选（例如 salt_alkali）
python 04.title_filter_deepseek_R3.py --stress salt_alkali
```

执行完成后，您将在当前目录下获得 `filtered_results/salt_alkali_relevant.tsv` 文件，可直接使用 Excel 或 Pandas 导入分析。
