# 结构化数据论文库

供团队共享的论文索引，无需登录即可浏览。

表格基础模型、结构化决策及相关方法的论文索引。按研究领域 → 子方向 → 具体议题 → 论文浏览，每层附研究范围说明。无需登录；支持搜索、目录与时间筛选、浏览器本地收藏、CSV 导出，以及原文、PDF 和代码跳转。

## 更新论文

第 5 类下的“推理显存与速度优化”按部署准备、输入压缩、上下文编码、前向计算和在线服务整理 OOM 与效率研究，另设跨阶段的 LLM 方法借鉴入口。现有相关论文按核心贡献归类；空议题表示尚无已核验条目。LLM 方法收录时注明适用前提和是否已有表格任务验证，详见[专题规则](research/COLLECTION.md#推理显存与速度专题)。

1. 按[检索与收录规则](research/COLLECTION.md)运行 `npm run collect`，结合会议、模型家族、作者发布与引用追溯核验候选。
2. 编辑 [`data/papers.json`](data/papers.json)，并更新[模型家族与版本登记](research/model-families.json)；保留已有条目的 `id`，避免收藏失效。
3. 提交前运行 `npm run record:updates`，自动记录新增与资料更新、填写新论文的收录日期并更新 `updatedAt`。再运行 `npm run check`，验证页面后推送到 `main`，GitHub Pages 自动发布。

也可以直接在 GitHub 网页编辑此 JSON 文件并提交。管理仓库需要所有者登录，访问站点不需要。

```json
{
  "id": "arxiv-YYMM.NNNNN",
  "title": "论文原始题名",
  "date": "2026-10-12",
  "updated": "2026-10-12",
  "addedAt": "2026-10-14",
  "category": 5,
  "section": "context-selection",
  "topicId": "retrieval-shots",
  "related": [6],
  "topic": "上下文优化",
  "status": "preprint",
  "venue": "预印本",
  "summary": "用一两句话说明研究问题与方法。",
  "url": "https://arxiv.org/abs/YYMM.NNNNN",
  "pdf": "https://arxiv.org/pdf/YYMM.NNNNN",
  "code": null,
  "keywords": ["TabPFN", "ICL"],
  "aliases": ["论文中的模型简称"],
  "sources": ["https://arxiv.org/abs/YYMM.NNNNN"]
}
```

`category` 为六个领域的编号，`section` 为该领域下的子方向 ID，`topicId` 为该子方向下的具体议题 ID。可选值见同一文件的 `categories → children → children`。每篇论文只计入一个完整主路径，`related` 保留其他相关领域的编号。`topic` 是对论文研究问题的补充描述，不用于目录归属。

目录节点的 `name`、`description`、`code` 分别是标题、范围说明和层级编号。新增议题时，在所属子方向的 `children` 中添加节点；保持已有 ID 稳定，以保留分享链接。目录数量和论文数量均根据数据自动汇总。旧版 `?category=3` 链接仍然有效，子目录可通过 URL 直接分享。

`status`：`published` 正式会议/期刊、`workshop`、`preprint`、`report` 技术报告。综述的发表状态按实际来源填写。

`venue` 记录会议/期刊及年份，Workshop 必须保留完整标识。已确认的 Highlight、Spotlight、Oral 等展示标记可另加 `recognition`，例如 `{"label":"Spotlight","source":"https://arxiv.org/abs/2506.10707","verifiedAt":"2026-10-12"}`。标记必须有会议官网或作者一手来源，不能从论文影响力或模型效果推断；卡片标签可点击查看来源。

`date` 使用最早已核实的公开时间；月份或日期缺失时仅填 `YYYY` / `YYYY-MM`，可加 `dateNote`。更新日期不替代首发日期。没有核实 PDF 或代码时填 `null`。只记录可由论文及其一手来源支持的信息，不赋予未经验证的质量分数。

`addedAt` 是首次加入本站的日期（北京时间），显示在卡片底部，支持“最近收录在前”排序和 CSV 导出。历史条目按其首次出现在本站 Git 版本记录的日期补齐；不能把原论文发表或修订日期当作收录日期。

各级目录以绿色 `+N` 显示当天新收录数量，为零时不显示；当天收录的论文卡片显示浅蓝色“今日收录”标记。提示仅由 `addedAt` 按北京时间计算，跨日自动消失，页面保持打开或从后台恢复时也会刷新；资料更正不计入新增，历史收录日期和更新记录照常保留。

顶层 `collectionUpdates` 保存按日归并的 `{date, added: [论文ID], updated: [论文ID]}`。默认折叠的“近期更新”面板据此显示当前目录近 30 天的更新日、数量及涉及的下级方向；同日新收录和更正不重复计数。资料更正保留原 `addedAt`，没有论文内容变化时不增加更新记录。`npm run record:updates` 默认与当前 `HEAD` 比较，可通过 `--base Git引用 --date YYYY-MM-DD` 显式指定；历史记录应保留，不按当前日期重建。

`aliases` 让站内检索覆盖模型简称、版本写法和原题名；`sources` 保存核验来源，并帮助合并同一论文的 arXiv、OpenReview 和会议版本。模型包含预训练部分、首发早于半年、所在主题已有代表作，都不构成自动排除理由。

## 每日维护

每天北京时间 09:00 由当前 Codex 对话的定时任务触发[每日更新机制](research/DAILY_UPDATE.md)：arXiv 每天增量检索；正式会议、OpenAlex 全文与语义近邻、引用关系、Consensus 和模型家族官方来源每周回查近六个月。候选进入跨天待审队列，经原始来源核验和质量审核后才发布；有实质变化时自动生成《结构化数据研究小报》。本机配置获授权的飞书话题群后，上线核验完成的小报可自动发送并回读去重。没有内容变化时不改目录更新日期。

`npm run collect:daily` 按渠道检查点只运行到期的检索，候选并入跨天的待审队列（`npm run queue -- top` 查看），不直接发布；`npm run collect:daily -- --dry-run` 只预览。OpenAlex 翻页需要免费 API key，写入环境变量 `OPENALEX_API_KEY`。审核结果用 `npm run apply:review` 写入，运行记录用 `npm run collect:finish` 生成。任务依赖本机 Codex 调度环境及网络；静态站点本身不执行采集，也不需要付费 API。实际调度时间以 Codex 定时任务设置为准。

已连接的 Consensus 由同一个 Codex 任务每周补充检索，先搜索、再读取完整记录，使用 `npm run collect:consensus` 导入队列后核验。插件不可用或限流时保留缺口，其他渠道继续；访问论文站无需安装插件。

论文在全部目录、分类和检索结果中默认按最早已核实的公开时间倒序排列，可切换为最早公开在前或最近修订在前；入库和修订不会改变首发排序。收藏保存在浏览器本机，不是团队共享收藏。

## 本地预览

需要 Node.js 20 或更新版本；采集和完整检查另需 Python 3.9 或更新版本。均无第三方依赖。

```sh
npm run dev
npm run check
```

预览地址 `http://127.0.0.1:4317`。站点文件直接由 GitHub Pages 从 `main` 分支根目录发布；`.nojekyll` 禁用 Jekyll 处理。也可原样部署到任意静态托管服务。

## 数据与访问

- 站点只保存论文元数据和中文概览，不托管论文全文。论文版权归原作者或出版方。
- PDF 链接打开原始文件，可在浏览器 PDF 阅读器下载；部分出版方限制访问的论文仅提供原文入口。
- 收藏只写入当前浏览器的本地存储，不跨设备同步；清理浏览器数据会删除收藏。
- CSV 导出当前筛选结果；页脚 JSON 下载完整目录。
- 无账号系统、付费 API、外部字体或分析追踪。GitHub Pages 的免费额度与限制遵循其[官方说明](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。
