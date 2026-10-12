# Shirly 的研究书架

公开站点：**https://shirlyjia.github.io/paper-library/**

表格基础模型、结构化决策及相关方法的论文索引。按研究领域 → 子方向 → 具体议题 → 论文浏览，每层附研究范围说明。无需登录；支持搜索、目录与时间筛选、浏览器本地收藏、CSV 导出，以及原文、PDF 和代码跳转。

## 更新论文

1. 编辑 [`data/papers.json`](data/papers.json)：新增或修改 `papers` 条目；保留已有条目的 `id`，避免收藏失效。
2. 将顶层 `updatedAt` 改为本次内容更新日期，运行 `npm run check`。
3. 提交并推送到 `main`，GitHub Pages 自动更新。没有构建或数据库步骤。

也可以直接在 GitHub 网页编辑此 JSON 文件并提交。管理仓库需要所有者登录，访问站点不需要。

```json
{
  "id": "arxiv-YYMM.NNNNN",
  "title": "论文原始题名",
  "date": "2026-10-12",
  "updated": "2026-10-12",
  "category": 5,
  "section": "context-selection",
  "topicId": "retrieval-shots",
  "related": [6],
  "topic": "上下文优化",
  "status": "preprint",
  "venue": "预印本",
  "summary": "用一两句话说明研究问题与方法。",
  "evidence": "数据、实验规模、验证结果及特有的适用条件。",
  "url": "https://arxiv.org/abs/YYMM.NNNNN",
  "pdf": "https://arxiv.org/pdf/YYMM.NNNNN",
  "code": null,
  "keywords": ["TabPFN", "ICL"]
}
```

`category` 为六个领域的编号，`section` 为该领域下的子方向 ID，`topicId` 为该子方向下的具体议题 ID。可选值见同一文件的 `categories → children → children`。每篇论文只计入一个完整主路径，`related` 保留其他相关领域的编号。`topic` 是对论文研究问题的补充描述，不用于目录归属。

目录节点的 `name`、`description`、`code` 分别是标题、范围说明和层级编号。新增议题时，在所属子方向的 `children` 中添加节点；保持已有 ID 稳定，以保留分享链接。目录数量和论文数量均根据数据自动汇总。旧版 `?category=3` 链接仍然有效，子目录可通过 URL 直接分享。

`status`：`published` 正式会议/期刊、`workshop`、`preprint`、`report` 技术报告。综述的发表状态按实际来源填写。

`date` 使用最早已核实的公开时间；月份或日期缺失时仅填 `YYYY` / `YYYY-MM`，可加 `dateNote`。更新日期不替代首发日期。没有核实 PDF 或代码时填 `null`。只记录可由论文及其一手来源支持的信息，不赋予未经验证的质量分数。

## 本地预览

需要 Node.js 20 或更新版本，无第三方依赖。

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
