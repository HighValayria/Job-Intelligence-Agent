# Job Intelligence Agent

求职情报采集与整理系统。第一阶段是一个完全离线可运行的 Mock 闭环，用于验证长期运行的信息采集架构：采集招聘信息、面经、Offer、待遇/工作体验帖，清洗文本，合并 OCR，分类与结构化抽取，去重，写入 SQLite，并从 SQLite 全量导出 Excel。

当前版本不包含真实小红书/牛客采集、浏览器自动化、登录、Cookie、验证码、真实 LLM API、PaddleOCR、VLM、Embedding 去重、Web 前端或通知功能。

## 架构

```text
Scheduler / Runner
-> Query 配置
-> Collector
-> RawPost
-> 文本清洗
-> 图片 OCR
-> UnifiedContent
-> LLM 分类
-> 类型对应的结构化抽取
-> Normalization
-> Validation
-> Deduplication
-> SQLite
-> Excel Export
```

核心边界：

- Collector 只负责把平台数据转换成 `RawPost`。
- OCR Provider 只负责图片到文本。
- LLM Provider 只接收 `UnifiedContent`，只输出 Pydantic Schema 数据。
- Repository 是唯一 SQLite 写入入口。
- Excel 只从 SQLite 全量导出，不参与去重或状态判断。

## 目录职责

- `config/`: 查询、平台、公司别名、岗位 taxonomy 配置。
- `collectors/`: 采集接口与 MockCollector。
- `models/`: RawPost、UnifiedContent、分类结果和四类业务 Schema。
- `processing/`: 文本清洗、OCR 抽象、UnifiedContent 构建。
- `llm/`: LLMProvider 抽象、MockLLMProvider、分类/抽取/标准化调用薄层。
- `validation/`: Pydantic Schema 校验与置信度辅助。
- `dedup/`: post_id 去重与内容 fingerprint 去重。
- `storage/`: SQLite schema 与 Repository。
- `exporters/`: Excel 导出。
- `scheduler/`: PipelineRunner。
- `tests/`: pytest 测试与 Mock 帖子 fixture。
- `data/`: 默认输出目录，生成 SQLite 和 Excel。

## 如何运行

安装依赖：

```bash
pip install -e ".[dev]"
```

执行 Mock 全链路：

```bash
python main.py
```

默认生成：

- `data/job_intelligence.sqlite3`
- `data/job_intelligence.xlsx`

再次运行会读取同一批 Mock 帖子，但相同 `platform + post_id` 不会重复插入。

运行测试：

```bash
python -m pytest
```

如果本机没有把 Python 加入 PATH，可以直接使用当前机器的 Python：

```powershell
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe main.py
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe -m pytest --basetemp data\pytest-tmp -o cache_dir=data\pytest-cache
```

## 数据库设计

SQLite 是主数据源，当前 schema 至少包含：

- `posts`: 所有帖子的基础索引，保存原始正文、OCR、URL、发布时间、抓取时间、分类结果、抽取结果、confidence、needs_review 和内容 fingerprint。
- `recruitments`: 招聘信息结构化结果。
- `interviews`: 面经主表。
- `interview_rounds`: 面试轮次明细。
- `offers`: Offer 和薪酬福利结构化结果。
- `work_conditions`: 待遇与工作体验结构化结果。
- `companies`: 公司标准名、类型、别名。
- `crawl_runs`: 每次 pipeline 运行记录。

一级去重使用 `platform + post_id`。二级去重使用规范化 `full_content` 后的 SHA256 fingerprint。

## 增加新的 Collector

1. 在 `collectors/` 新增类并继承 `collectors.base.Collector`。
2. 实现 `collect(self, queries) -> list[RawPost]`。
3. 平台原始字段必须在 Collector 内转换成统一 `RawPost`。
4. 在 `config/platforms.yaml` 中登记平台和 Collector 路径。

Collector 不应该调用 LLM、SQLite 或 Excel。

## 增加新的 OCR Provider

1. 在 `processing/ocr.py` 或新文件中继承 `OCRProvider`。
2. 实现 `extract(image) -> OCRResult`。
3. 在 runner 初始化时注入新的 provider：

```python
PipelineRunner(ocr_provider=YourOCRProvider()).run()
```

OCR Provider 只返回 OCR 文本和置信度，不参与分类、抽取或入库。

## 增加新的 LLM Provider

1. 继承 `llm.base.LLMProvider`。
2. 实现：
   - `classify(content)`
   - `extract(content, post_type)`
   - `normalize(result)`
3. 输出必须通过 `validation/schema_validator.py` 的 Pydantic Schema 校验。
4. 在 runner 初始化时注入：

```python
PipelineRunner(llm_provider=YourLLMProvider()).run()
```

LLM Provider 不应直接操作网页、SQLite 或 Excel。

## Mock 数据

`tests/fixtures/mock_posts.json` 包含 4 篇帖子：

- 招聘信息
- 面经
- Offer
- 待遇/工作体验

其中面经样例正文很少，核心内容来自 `MockOCRProvider` 的图片 OCR 文本，用于验证 `UnifiedContent -> 分类 -> 抽取 -> SQLite -> Excel` 全链路。
