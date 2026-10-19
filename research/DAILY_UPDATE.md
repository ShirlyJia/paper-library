# 每日更新机制

每天北京时间 09:00 由 Codex 定时任务触发；收录标准和质量审核见 [检索与收录规则](COLLECTION.md)，本文件只写执行顺序。调度依赖本机 Codex 环境与网络，实际完成时间取决于检索和审核；访问静态站点不触发采集。

## 检索节奏

每个渠道单独记检查点（`work/collection/daily-state.json`），只运行到期渠道；一个来源失败只影响它自己，次日自动重跑。

| 渠道 | 频率 | 时间窗口 | 执行方式 |
| --- | --- | --- | --- |
| arXiv（主题检索式 + 已登记家族） | 每天 | 最近 7 天，并与上次完成日期重叠 3 天 | 自动 |
| OpenAlex 全文、语义近邻、引用网络 | 每 7 天 | 近 6 个月（按发表日期过滤，索引有延迟） | 自动 |
| 正式会议目录、参考文献来源 | 每 7 天 | 当年与上一年目录 | 自动 |
| Consensus | 每 7 天 | 近 6 个月 | Codex 连接器，手动导入 |
| 已登记模型家族官方来源 | 每 7 天 | — | `npm run fetch:sources -- --families` |

首次执行或渠道没有记录时回查近 6 个月；停机后从上次完成日期补齐。OpenAlex 翻页需要免费 key，写在项目根目录被忽略的 `.env`（`OPENALEX_API_KEY=...`），没有 key 时只取第一页并记为未完成。

## 每日步骤

1. **准备。** 读 `AGENTS.md`。工作区干净时 `git pull --ff-only`；有未提交修改先辨认归属，不覆盖、不强推。
2. **采集。** `npm run collect:daily`。到期的自动渠道写入 `work/collection/daily/日期/运行编号/candidates-N.json`，并自动并入跨天待审队列 `work/collection/queue.json`。脚本最后列出今天到期的手动渠道（Consensus、模型家族）及命令；照做后把结果并入同一运行目录。没有到期渠道时跳过采集，直接处理队列。
3. **初筛。** `npm run queue -- top` 按优先级列出待处理候选：题名命中、被多个独立渠道发现、近期首发在前，已有论文只在出现新修订或录用记录时进入"更新核对"。排序不删除候选；语义和引用结果不因缺少关键词被丢弃。先处理高分项；只在摘要命中一次的低分项每周集中扫一遍。摘要级结论用 `npm run queue -- screen ID --verdict not-relevant|needs-fulltext --reason 理由` 记下，次日不再出现，论文有新修订时自动重开。初筛记录不是公开决定。
4. **审核。** 拟收录或涉及方法／实验结论的更正，用 `npm run fetch:sources -- jobs.json --out 本次目录/primary` 取得正文文本（arXiv 优先用 HTML 版），按规则的"质量与价值审核"阅读并判断；仅摘要不能完成审核。从新论文的相关工作、基线表和参考文献追踪未知家族；TabArena 作为专项线索。
5. **写入。** 把本次新增、更正、暂缓、排除写进一个 `本次目录/review-input.json`（格式见 `scripts/apply_review.py` 开头；新增和更正各附一句 `brief`），运行 `npm run apply:review -- 本次目录/review-input.json`。脚本校验质量审核字段，统一写入 `data/papers.json`、`research/decisions.json` 和家族登记表。不要为这些步骤另写一次性脚本。不得为凑数量添加论文。
6. **检查并发布。** `npm run record:updates && npm run check`，再在站内按目录、年份和简称搜索新条目。只提交本次相关修改，推送 `origin/main`（先用 `git remote get-url origin` 确认），等待 Pages 发布后核对线上 JSON 与页面；截图核对只在本次确有发布时做。推送冲突、测试或部署失败时保留现场并报告，不重置远端、不强推。没有内容变化时不修改 `updatedAt`，不制造空发布。
7. **收尾。** 有新增或更正时，先按["今天的看点"撰写提示词](BRIEFING_PROMPT.md)写 `本次目录/briefing-highlights.md`，再运行 `npm run collect:finish -- 本次目录 --review-input 本次目录/review-input.json [--published] [--note 缺口说明]`。脚本生成固定格式的 `review.json`、小报 `briefing.md` 和运行记录 `run-notes.md`，并只推进本次完整完成的渠道检查点。候选已在队列里，所以检索检查点与审核进度分开推进，未审候选不会丢失。发布或核对未完成时不加 `--published`。
8. **群内发布。** 本机已配置飞书发送时，`collect:finish` 自动调用 `lark-cli`，将已上线的小报和站点链接发布到获授权的话题群，并回读核验；同时重试启用日期以来尚未送达的小报。通知失败保留回执，收录检查点不回退。补发可独立运行 `npm run briefing:send`，无需重跑检索。

```sh
npm run collect:daily
npm run queue -- top
npm run apply:review -- 本次目录/review-input.json
npm run record:updates && npm run check
npm run collect:finish -- 本次目录 --review-input 本次目录/review-input.json --published
```

## 更新小报与运行记录

`collect:finish` 每次生成两份文件，结论和过程分开：

| 文件 | 何时生成 | 内容 |
| --- | --- | --- |
| `briefing.md`（小报） | 有新增或实质更正时 | 只写结论。开头一句速览（自动）：收录篇数、新论文与补录各几篇、覆盖哪些方向、论文库链接。"今天的看点"：审核者按[撰写提示词](BRIEFING_PROMPT.md)写入 `briefing-highlights.md`，用 150–300 字平实地讲清今天的主线和两三篇重点论文。各方向上新（自动）：按方向分组，每篇一行简称、链接和 `brief`。 |
| `run-notes.md`（运行记录） | 每次 | 过程信息。需要处理的问题：检索失败渠道、未上线、`--note`。暂缓论文及理由。渠道完成情况、待审队列规模、发布状态。 |

在当前对话里先输出小报全文和文件链接。只有运行记录的"需要处理"一节有内容时，才另起一段简短列出问题。没有新增也没有问题时保持安静。获用户明确授权后，只向本机飞书配置指定的话题群自动发送公开小报和站点链接；不发送运行记录、候选、内部备注、本机路径或聊天内容，不向其他接收方发送。

## 飞书小报发送

- 通过已安装的 `lark-cli` 发送 Markdown 富文本。每次实质更新创建一个新话题，保留论文原文链接和网站入口；无更新不发空小报，不自动 @ 群成员。
- 目标与身份仅保存在 Git 忽略的 `work/notifications/feishu.json`：`enabled`、`identity`（`user` 或 `bot`）、`chatName`、`notBefore`（启用日期），首次精确匹配唯一话题群后写入 `chatId`。不按模糊名称自动选群，不自动切换身份。凭证由飞书 CLI 管理，不写入仓库。
- 用户身份须完成飞书授权；机器人身份须具备权限并已加入目标群。身份失效或目标不匹配时停止发送，在当前对话报告处理方式。
- 只发送 `publication.published=true` 的运行，发送前再次核对本次论文线上与本地一致。只读取该运行的 `briefing.md`，核对日期及论文链接覆盖。
- 按群、北京时间日期和论文 ID 清单去重；回执保存在 `work/notifications/receipts/`，成功回读后也保存到运行目录的 `feishu-delivery.json`。同一清单正文变更不另发重复话题，先核对已有消息。CLI 请求使用固定幂等键；网络结果不明时先回查群历史，超过安全重试窗口不盲目重发。
- `npm run briefing:send -- --run 本次目录 --dry-run` 预览；去掉 `--dry-run` 发送该次小报；不传 `--run` 重试启用日期以来尚未发送的已发布小报。换机器时需迁移本机配置和回执，或设置新的启用日期，避免补发历史内容。

每篇新增或更正在 `review-input.json` 里附 `brief`（不超过 80 字，说明它是什么；更正写明改了什么），可选 `name` 指定简称。`apply:review` 会检查 `brief`。

## 检查点格式

```json
{"channels": {"arxiv": "YYYY-MM-DD", "fulltext": "YYYY-MM-DD", "semantic": "YYYY-MM-DD", "citations": "YYYY-MM-DD",
              "formal": "YYYY-MM-DD", "references": "YYYY-MM-DD", "consensus": "YYYY-MM-DD", "families": "YYYY-MM-DD"}}
```

日期为北京时间，记录渠道最近一次完整完成。只有 `npm run collect:finish` 根据运行目录中的报告推进检查点；采集命令本身从不推进。

## 资源使用

- 网络缓存保留两天，采集时自动清理；同一天重试复用缓存。
- 会议完整目录、OpenAlex 半年回查、Consensus 与家族官方来源每周各一次，不每天重复。
- 正文抓取只保存文本和 SHA-256，需要原件时加 `--keep-raw`。

## 日期与发布边界

- 论文卡片顶部日期是最早已核实的公开时间，`updated` 是论文修订时间，`addedAt` 是首次加入本站的北京时间日期；三者分别维护，更正不改写 `addedAt`。`collectionUpdates` 按日记录新增与资料更新，同日去重，由 `npm run record:updates` 维护。
- 目录 `+N` 和"今日收录"按当天 `addedAt` 自动显示，跨北京时间零点清除，无需手动维护。
- `updatedAt` 表示目录内容更新，不代表最后一次检索。
- 站点保持团队中性名称，不加个人署名；保留六大类完整标题和已有 ID，不恢复"优先阅读"或"验证与边界"。
- 执行过程、候选、队列、检查点和本机路径只保存在被忽略的 `work/` 目录，不进入公开元数据。
