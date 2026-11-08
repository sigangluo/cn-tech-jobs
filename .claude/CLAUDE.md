# 社招职位看板（维护手册）

多家互联网公司的**技术 / 产品**社招岗位：官网公开接口 → `data/<公司>/*.csv` → `site/data` → 静态看板 `site/`。由 AI（你）维护。

- 这份文档是维护规则的唯一来源。**README 只写给看板用户**（目的、怎么看），不要往里写维护内容。
- 出了问题读 [runbook.md](runbook.md)；更新数据后对照 [known-issues.md](known-issues.md)，只处理**新出现**的异常。
- 文档只记代码里读不出来的东西；能从代码注释、测试、脚本输出看到的，不在这里重复。
- **公司不是固定的**：任何脚本、页面、文档里都不要写死公司名或数量，公司列表唯一来源是 `companies/`。

## 不要碰

- `data/`、`site/data/`、`.backups/`：生成物，不进 git，不要手改；要改就改生成它们的脚本再重新生成。
- 不要自动 commit / 推送 / 发布，除非用户明确要求。强制推送 gh-pages 会覆盖线上，属于对外发布。

## 布局

```
companies/<key>/fetch.py   每家公司一个文件：META + fetch()，自动发现；_template/ 是新增公司的模板
scripts/update.py          入口：并行抓取（失败自动重试一次）→ 合并 → 质量报告 → 耗时汇总
scripts/{fetch_company,build,audit,publish,serve}.py   各自职责见文件头 docstring
scripts/lib/               共用：schema（职位格式、CSV）、years、http（重试/限流/完整性/统计）、feishu_hire、scope、jd、geo
site/                      静态看板；assets/state.js 是筛选状态⇄URL 的纯函数
tests/                     Python 单测 + tests/state.test.js
reports/                   每次更新的质量报告（进 main）
```

## 更新数据（用户说「更新一下数据」）

```bash
python3 scripts/update.py     # 约 7 分钟，总耗时 = 最慢那家（目前是腾讯）。确定性脚本，不需要 API key
```

1. 失败的公司会自动重试一次，仍失败才中止（且不合并）→ runbook「抓取失败」。
2. 某家某个看板类别比上次少超过 30%：拒绝覆盖旧 CSV。先查清是抓漏还是真下架，确认真下架才用 `--accept-large-drop <key>` → runbook「数量骤降」。
3. 看末尾的耗时表和质量报告 alerts（`reports/<日期>.json`）：对照 known-issues，只处理新出现或明显恶化的。报告是复核队列，不等于已人工核验。
4. `python3 scripts/serve.py` 本地预览（不能双击 html，也不要用 `http.server`，它会让浏览器缓存旧数据）。
5. 向用户汇报：各公司职位数及变化、失败 / 重试 / ⚠、新出现的 alerts。**不要自动提交或发布。**

看板只呈现抓取当天的快照：不保存历史，不做新增 / 下架对比，没有趋势图（有意为之，不要加）。`weekly-audit` 工作流每周在 GitHub 上重新抓取，只是「抓取还能不能跑通」的哨兵，不发布、不产出可发布的数据。

## 发布与回滚

数据由 `scripts/publish.py` 单独发布到 `gh-pages`，该分支**永远只有一个提交**。

- 用户说「发布」：先 `python3 scripts/publish.py`（默认只检查），把文件数、数据日期、提交作者、目标仓库告诉用户，**得到确认后**才加 `--push`。提交作者用本仓库 `git config` 里的公开身份（noreply 邮箱），不用内网 / 公司邮箱。
- 每次 `--push` 前自动存档到 `.backups/`（最近 3 份）。回滚：`publish.py --archive .backups/<文件>`（同样先检查、确认后才 `--push`）。
- 页面文案不要承诺「每周更新」，发布是手动的；数据日期超过 10 天页面会自动提示。

## 新增一家公司

只写一个文件，合并、看板、页脚全部自动带上。

1. `cp -r companies/_template companies/<key>`（`<key>` 是英文小写名，同时是 `data/<key>/` 目录名）。飞书招聘系统（`xxx.jobs.feishu.cn`）直接用 `lib/feishu_hire.py`，不要另写一份。
2. 浏览器 F12 → Network 找职位列表接口，先确认不带 cookie 能否调通、单页最多几条、翻页有无上限 / 漏项。
3. 写 `META` 和 `fetch()`，返回 `make_job(...)` 列表（字段见 `lib/schema.py`）：
   - **年限一律用 `resolve_years(官网结构化字段或 None, 任职要求)`**，返回的第三项原样填给 `years_source`（校验会拒绝没填的）。官网只有一个描述字段时第三个参数传 `"职位描述"`。
   - `category` 填官网**原始**一级分类名，不要自己合并；合成看板类别靠 `META["categories"]` 多对一映射。
   - 公司特有信息放 `extra`（只进 CSV）。想要公司专属筛选就声明 `META["facets"]`，以官网列表页自带的筛选项为准，名字沿用官网。
   - 翻页后用 `lib.http.ensure_complete(抓到, 官网声称总数, 名称)` 核对完整性；抓不全就**抛异常**，不要返回半截数据。请求用 `call_json`（带重试和限流退避），自己写的等待用 `http.backoff()`，耗时才会进统计。
4. `python3 scripts/update.py --only <key>`，打开预览确认筛选、图表、列表都正常，点开一个职位确认链接能打开（没把握的链接宁可留空）。官网没有国家字段的公司，国家由 `lib/geo.py` 按城市推断；冒出新的海外城市要补进 `geo.OVERSEAS`。
5. 把这家的已知缺口记到 known-issues。

不要为新公司改 `build.py`、`update.py`、`site/` 或本文档；必须改说明抽象漏了，先补 `lib/`，不要开特例。新增看板类别（如「运营」）才动共用代码：`schema.CATEGORIES` 加一项，各公司 `META["categories"]` 映射过来，前端最多 8 个类别。

## 要遵守的约定

**工作年限**（全项目唯一一份实现 `lib/years.py`，细节见其 docstring 和测试）
- 「未提及」（没写，不知道）和「明确不限」（写了不限，或 0-N 年 / N 年以内）是两回事，必须分开；前端第 0 档用灰色。
- 任职要求文字明确写了年限就以文字为准，没写才用官网结构化字段；官网写「不限」但文字没提，记「未提及」。
- 「优先 / 加分」里的年限记为优先年限，不算必须。「年限来源」进 CSV，质量报告据此统计。

**类别推断**：官网没有可靠类别字段的公司按职位名推断，原始分类名统一用 `schema.INFERRED_CATEGORY`（审计和前端靠其中的 `INFERRED_MARK` 识别「类别推断」），**不要在别处手写这些字符串**。规则分散在 `lib/feishu_hire.py`、`companies/alibaba`、`companies/jd`，排除规则在 `lib/scope.py`；改规则要在 `tests/test_scope.py` 补用例，且按「一类职位」改，不为单个职位名加特例。

**筛选**（`site/assets/app.js`）
- 通用层对所有公司一致；公司专属筛选只在选中**一家**公司时出现，前端只读 `jobs.json`，不写死任何公司。
- 选项数字是「满足除自己以外所有条件」的职位数（`passes(j, skip)` + `refreshOptions`）。新增筛选维度要同时：加 `passes` 的 `skip` 分支、补 `refreshOptions`、在 `state.js` 加 URL 参数并补 `tests/state.test.js`。
- 筛选状态写在地址栏（`history.replaceState`），打开时按 `jobs.json` 校验后恢复，格式只在 `state.js` 定义。
- 关键词搜索只加载**当前公司筛选范围内**的职位描述（全部约 8 MB 压缩），不要改回「一上来全加载」。

**站点**
- 纯静态、无构建、无第三方依赖、不请求外部资源。职位名、部门、JD 来自第三方：**只用 `textContent` / 文本节点渲染，不拼 `innerHTML`**；链接只接受 `https://`。
- 配色遵循 dataviz skill（类别色 `--cat-0…7` 按顺序固定，年限用同一色相有序渐变）；改颜色要用该 skill 自带的校验脚本重新校验（仓库里没有）。

**直达链接必须用真实浏览器验证**：这些站点多是单页应用，任何路径都返回同一个壳页面，curl 判断不了对错。打开列表页、点一个职位看它跳到哪个地址，再抽样打开自己拼的链接确认出现对应职位名；拿不准就留空，看板会指向官网职位列表。**用浏览器自动化前先征得用户同意。**

## 改完要做

- Python：`python3 -m unittest discover -s tests`；改了 `years.py`、`schema.py`、`scope.py` 或识别规则必须补 / 改测试。
- 前端：`node --check site/assets/app.js && node --check site/assets/state.js && node tests/state.test.js`，有条件再在浏览器里看一遍（先征得同意）。
- 改了行为就同步改本文档；README 只在用户可见的变化时才改，保持短。CI（`test.yml`）会在推送和 PR 上跑这些测试。
