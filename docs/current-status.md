# Current Status

日期：2026-08-15

## 测试状态

使用本机 Python：

```powershell
C:\Users\33967\AppData\Local\Programs\Python\Python312\python.exe -m pytest --basetemp data\pytest-tmp -o cache_dir=data\pytest-cache
```

结果：`18 passed`。

## 真实样本盘点

当前 `real_samples/`：

- 总数：32
- `interview`: 15
- `recruitment`: 13
- `information_gap`（原 `infodiff`）: 4
- `offer`: 0
- 小红书：22
- 牛客：5
- 未填平台或空样本：5
- 含图片：15
- 纯文本：17
- 已有 `gold.json`: 8
- 空或不完整样本：5

Offer 真实样本为 0 是当前阶段允许状态；Mock Offer 和 Offer Schema 仍保留。

## 已完成

- `work_condition` 兼容迁移到 `information_gap`
- `InformationGap` Schema
- per-image OCR result
- 结构化 `UnifiedContent.segments`
- `RealSampleLoader`
- optional partial gold evaluation
- AI 初标 `gold_draft.json` 与人工确认 `gold.json` 分离
- inspect CLI
- inventory CLI
- RealLLMProvider 配置化骨架
- PaddleOCRProvider 可选骨架
- Excel “信息差” Sheet
- `docs/architecture.md`
- `docs/current-status.md`

## 未完成 / 下一步

- 真实 LLM prompt 需要用 gold 样本迭代。
- 当前真实样本已有 8 个审核通过的 gold，可用于初步回归；样本量仍需继续扩充。
- 可以继续运行 `draft-gold` 生成 `gold_draft.json`，审核后再 `promote-gold`。
- Moonshot/Kimi K3 `.env` 配置已接入；`llm-status` 可本地检查配置是否加载，不会发送样本内容。
- 真实 LLM 回归已跑通：Kimi K3 可完成分类和抽取，已补 schema 输出修复、metadata/source_url 输入、评估文本归一化和 `data/llm-cache/` 响应缓存。
- 当前 12 个 gold 样本在 mock OCR 下的真实 LLM 字段级评估为 `149 passed / 124 failed`；评估器已支持同级列表匹配和文本包含匹配，剩余失败主要集中在字段粒度、信息差摘要、部分面经题目分类，以及含图样本缺少可外发的真实 OCR 内容。
- PaddleOCR 本地 smoke 已验证国家电网图片样本可识别并进入 `UnifiedContent`；将 OCR 派生文本发送给 Moonshot 需要额外授权。
- PaddleOCRProvider 已在项目 `.venv` 中用 PaddleOCR 3.7.0 跑通单图 inspect。
- 第一次运行 PaddleOCR 会下载官方模型到 `C:\Users\33967\.paddlex\official_models\`。
- 真实小红书/牛客自动采集仍属于后续阶段，不在本阶段实现。
