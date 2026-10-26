---
name: yiban-exam
description: 面向优课 / 易班在线考试（exam.yooc.me、exambackend.yooc.me），依据用户提供的本地资料（学生手册、复习资料、法规原文等 docx/pdf/txt）自动完成网页上当前这套选择题并全量复验。触发场景：用户附上一份文档并说「根据文档内容完成我现在打开的这个网页页面的这些选择题」「继续做完这套题」「根据学生手册答易班考试」「优课考试帮我做完」。会自己拉全卷、逐题在资料里找条款、按选项文本匹配作答，但**不点交卷**。
description_zh: 依据学生手册、法规原文等本地资料（docx/pdf/txt），自动作答优课／易班在线考试网页上的选择题，逐题标注资料条款依据并全量复验；兼容「逐题型」与「整卷型」两种卷型，只作答、不代交卷。
description_en: Auto-answer multiple-choice questions in Yooc / Yiban online exams from local reference documents (docx/pdf/txt), cite the source clause for every answer, and verify the whole paper. Handles both one-question-per-page and whole-paper-in-one-page exam types. Fills answers only - never submits.
agent_created: true
---

# 易班 / 优课在线考试自动作答

一句话流程：**依据资料 → 变成可检索的纯文本 → 一次拿全卷 → 逐题在资料里找到条款 → 按文本匹配注入 → 全量复验 → 交给用户交卷。**

## 三条硬边界（任何情况下不破）

1. **不点「交卷」。** 交卷不可逆，必须由用户决定。脚本只负责把选项选上，做完明确告诉用户「已全部作答、未交卷」。同理不点任何"提交/确认"类按钮（含整卷型的「提交试卷」）。
2. **不猜答案。** 每题必须能在依据文本里指出条款（行号 + 原句）。查不到就标 `推断`，并在交付时单独列出原因，**绝不静默**。
3. **按文本匹配选项，不按字母，也尽量不按下标。** 平台会打乱**选项顺序**，整卷型还会打乱**题目顺序**，`A/B/C/D` 和下标都不可靠。

---

## 0. 前置

依赖 **web-access** skill 的 CDP proxy（复用用户已登录的浏览器）。

```bash
node "$HOME/.workbuddy/skills/web-access/scripts/check-deps.mjs"
```

Windows 上 proxy 是 check-deps 的子进程，**会随发起它的 shell 一起被回收**（表现为下一次 Bash 调用报 `upstream connect failed ... 10061`）。必须用 `run_in_background: true` 跑一条常驻命令：

```bash
node "$HOME/.workbuddy/skills/web-access/scripts/check-deps.mjs"; echo KEEPER; node -e "setInterval(function(){},60000)"
```

判定标准：在**另一次独立的 Bash 调用**里 `curl -s http://localhost:3456/targets` 也能返回列表。

若存在 `web-access/references/site-patterns/exam.yooc.me.md`，先读它。

约定：
- Python 用任意 3.9+ 解释器（PDF 场景需 `pip install pypdf`），下文记作 `$PY`
- 本 skill 目录记作 `$SK` = `$HOME/.workbuddy/skills/yiban-exam`

接着从 `/targets` 里找出用户当前打开的那个考试 tab，记下它的 `target` id（下文 `<TID>`）。**不要新开 tab 去答** —— 考试有状态，必须在用户那个已进入答题的 tab 上操作。

> **先确认 tab 还活着**：`curl -s "http://localhost:3456/info?target=<TID>"`。返回 `{}`（而不是带 `title`/`url` 的 JSON）说明 tab 已被关闭；此时 `/eval` 会返回**空 body**，Python 侧表现为 `json.decoder.JSONDecodeError: Expecting value: line 1 column 1`。别去调 proxy、也别怀疑脚本 —— 重新 `/targets` 拿新的 tab id 即可。用户很可能已经交卷并关掉了考试页。

---

## 1. 判别卷型（先做这一步，后面两条链路完全不同）

看考试设置区的「答题提交方式 / 出题类型」：

| 卷型 | 判据 | 页面特征 | 用什么脚本 |
|---|---|---|---|
| **逐题型** | 没写「整卷」；或「逐题提交」 | 一次只渲染一题，有「上一题 / 下一题」按钮；题干在 `main h3` | `auto_answer.py` |
| **整卷型** | 「**整卷提交**」+「出题类型：整卷型」 | 全卷一次性渲染同页，**无翻页按钮**，页脚「保存试卷 / 提交试卷」+ 侧栏「题目大纲」；每题是 `div.question-board` | `whole_paper.py` |

最省事的判据：`document.querySelectorAll('div.question-board').length > 0` 就是整卷型。

⚠️ 整卷型的 URL 就是 `/exam/<id>/detail`，**页面标题写着「考试详情」但其实就是答题界面**，别以为它是只读预览页就去找「开始考试」按钮。

---

## 2. 把资料变成可检索的依据文本

**docx**（学生手册等）：

```bash
"$PY" "$SK/scripts/docx_to_text.py" "~/Downloads/学生手册（1）.docx" 依据.txt
```

**pdf**（法规原文、新闻/党史文章等，很常见）：

```bash
"$PY" "$SK/scripts/pdf_to_text.py" 依据.txt "国旗法.pdf" "国徽法.pdf" "国防教育法.pdf"
```

两者产出格式一致：**每段一行**（行号 = 段号，后面引用依据直接写行号）。这是本轮**唯一**的答案来源。

`pdf_to_text.py` 细节：用 `pypdf`（托管 Python 自带）逐页 `extract_text()`；多个文件之间插入 `### FILE: <名>.pdf` 分隔行（**分隔行本身也占一个行号**，别算错），这样 grep 命中的上下文里能一眼看出条款出自哪份文件。
- 法规类 PDF 排版干净，提取质量很好；
- **输出 0 行 = 扫描件/图片页**，脚本会给提示 → 只能 OCR，或改标 `推断`。
- 多份**不同**资料可以、也建议合到一个 `依据.txt`（便于交叉引用）；但**同一份资料的两个版本绝不能合在一起**（行号会串、无法判断引用的是哪版）。

检索：

```bash
"$PY" "$SK/scripts/grep_evidence.py" 依据.txt 抄袭 夹带 -c 2
"$PY" "$SK/scripts/grep_evidence.py" 依据.txt -r 1578 1584      # 复核行号区间
```

> 别用文档类 MCP 工具解析 docx：中文路径报 `file not found`，换英文名后在 COS 上传环节失败（缺 `upload_to_cos.py`），`doc_get_document_content` 这类工具根本不存在。直接 Python 解 zip 最稳。

细节与检索策略见 [`references/document-evidence.md`](references/document-evidence.md)。

---

## 3. 一次拿全卷（不要逐题翻页抄题）

**整卷型**：全卷已经在 DOM 里了，直接 dump，**不需要碰试卷 API**：

```bash
"$PY" "$SK/scripts/whole_paper.py" --tid <TID> --dump
"$PY" "$SK/scripts/whole_paper.py" --tid <TID> --dump --json 试卷.json   # 落地备用
```

**逐题型**：试卷接口的完整 URL（含 `token` / `yibanId` / `examuserId`）就在页面的 `performance` 里：

```bash
"$PY" "$SK/scripts/fetch_paper.py" <TID> 试卷.json
```

它会在页面上下文用同步 XHR 原样请求那个 URL，落地 JSON 并打印题面清单（题号 / subjectId / 分值 / 题干 / 选项）。

拿不到时的兜底：`auto_answer.py --dump`（逐题翻页抓 DOM，慢但一定能拿到）。

> ⚠️ 返回体里的 `answer` 字段**是占位/干扰值**（整卷所有题密文相同，试过 AES 各种模式都解不开）。绝不能拿来抄答案。

API 与 DOM 细节见 [`references/platform-yooc.md`](references/platform-yooc.md)。

---

## 4. 逐题定答案

对每道题：**题干里挑 2–3 个必然共现的实词 → 在依据文本里检索 → 读上下文条款 → 写下选项原文**。

沉淀成一份答案表（`考试答案清单.md`）：

| 题号 | 题目摘要 | 所选答案 | 依据 |
|---|---|---|---|
| 23 | 考试夹带资料的处理 | 警告处分 | L1580 抄袭夹带=考试作弊 |
| 44 | 优秀毕业生奖学金比例 | 6% | L4545 按毕业生总数 5%（三年制）/ 6%（两年制） |

**答案表里的依据列不能省** —— 那是复核和交付时说明问题的依据。

给脚本用的 `answers.json`，两种卷型的格式不同：

- **逐题型**：`{"23": "警告处分"}` —— 键是**题号**，值是选项文本的关键词。
- **整卷型**：**列表**，每题一项，靠**题干片段**定位（因为题序也会打乱，不能用题号）：

```json
[
  {"q": "中华人民共和国的国旗是", "a": ["五星红旗"]},
  {"q": "国旗使用时，应当遵守的规范有", "a": ["不随意丢弃、毁损国旗", "升国旗时肃立致敬"]}
]
```

`q` 取题干里**唯一的**片段（去空白后子串匹配），`a` 是选项原文。命中多题会报 `AMBIG`、一题不中报 `NOQ`、选项没找到报 `MISS`，三种都必须人工介入。

---

## 5. 注入作答

### 整卷型 → `whole_paper.py`（全卷同页，无翻页、无等待）

```bash
"$PY" "$SK/scripts/whole_paper.py" --tid <TID> --answers answers.json            # 作答
"$PY" "$SK/scripts/whole_paper.py" --tid <TID> --answers answers.json --clear    # 先清空再勾
```

一轮 eval 遍历全卷点完，逐条打印 `OK / AMBIG / NOQ / MISS`，**永不点提交**。

- 定位方式：`div.question-board` 每题一个容器；选项是容器内 `ol > li`，`li` 里含 `<input>`（`name = <subjectId>_1`，单选 `radio`、多选 `checkbox`）。
- **点法**：`li.querySelector('input').click()`。注意这里 `li` 外层**没有 `label`**（`el.closest('label')` 返回 null），所以不能靠 label 找文本，要读 `li.innerText`。
- **复选框必须先判 `!inp.checked` 再点**，否则会把已勾的取消掉（脚本已内置）。
- 题干 = 容器文本减掉 `<ol>` 的文本 → 所以 `--dump` 打出来的题干是干净的。

### 逐题型 → `auto_answer.py`

```bash
"$PY" "$SK/scripts/auto_answer.py" --tid <TID> --answers answers.json --log run.json
```

内部链路：
1. `inject.js` 注入 `window.__Y`（题号 / 题干 / 选项枚举 / 匹配算法 / `step()` / `nav()`）。
2. answers 以 base64 JSON 塞进 `window.__Y.answers`。
3. 循环：读当前题 → `step()`（精确匹配后点击）→ 点「下一题」→ **轮询等题号真的前进**（React 异步渲染，固定 sleep 不可靠）。
4. 每题 `status` 落日志，结束打印统计。

**`MISS` / `AMB` 必须人工介入**（脚本会把题目和选项原样打出来）：

```bash
# 换更长的、唯一的子串当关键词
"$PY" "$SK/scripts/auto_answer.py" --tid <TID> --set 23 --key "警告处分，考察期6个月"
# 或者按下标点（唯一按下标的场景，用前肉眼核对选项原文）
"$PY" "$SK/scripts/auto_answer.py" --tid <TID> --set 23 --index 3
```

匹配算法的坑见 [`references/answer-matching.md`](references/answer-matching.md) —— 尤其「警告处分 ⊂ 严重警告处分」这类包含关系误匹配，改算法前先读它。

---

## 6. 全量复验（必做）

```bash
# 整卷型
"$PY" "$SK/scripts/whole_paper.py" --tid <TID> --verify --answers answers.json
# 逐题型
"$PY" "$SK/scripts/auto_answer.py" --tid <TID> --verify --log verify.json
```

都是**另发一次 eval 回读页面**（React 异步渲染，同一次 eval 读到的还是旧值）。要求：**除标 `推断` 的题外，每题实际勾选非空**；整卷型的 `--verify --answers` 还会把页面勾选与 answers 逐条对照，不一致就逐条列出来。退出码非 0 就是有问题。

平台若「禁止查卷」，交卷后逐题对错就再也看不到 —— 复验是最后一道保险。

---

## 7. 交付

- 写 `考试答案清单.md`（含每题依据行号），用 `present_files` 交给用户。
- 明确说清：**已全部作答、未交卷，请你自己确认后点「提交试卷 / 交卷」**。
- 推断题单独列出，说明为什么（例如：考的是军训队列条令，资料里根本没有对应条款）。
- 收尾：`/close` 关掉自己开的 tab，**保留用户的 tab**。
- 把新发现的站点结构补进 `web-access/references/site-patterns/exam.yooc.me.md`。

---

## 8. 陷阱速查

| 现象 | 原因 / 解法 |
|---|---|
| `/eval` 返回空 body，Python 报 `Expecting value: line 1 column 1` | **tab 已被关闭**（用户交卷后关页）。`/info?target=` 返回 `{}` 即确诊。重新 `/targets` 拿新 id |
| 「警告处分」选中了「严重警告处分」 | 双向 `includes` 匹配的必然结果。**只允许单向**：选项文本包含关键词，且候选唯一 |
| 「III级」匹配到「II级」 | 同上。短关键词要补上下文（写 `预警 III级` 而不是 `III级`） |
| 两个近似选项（`A.只安排一次补考机会` vs `D.只安排一次补考机会，补考不及格只能重修`） | 精确匹配会命中短的那个。用**完整长句**当关键词，或按下标点 |
| 整卷型按题号/下标作答，重跑后全错位 | 平台「**是否顺序打乱：是**」，题目顺序也会变。**必须用题干片段定位**（`whole_paper.py` 的 `q`） |
| 整卷型复选框越点越少 | 已选中的 `input.click()` 会**取消**勾选。必须 `if(!inp.checked)` 再点 |
| 在整卷型页面上找「下一题」按钮 / 找 `main h3` | 整卷型没有翻页按钮，题干也不在 `h3` 里。改用 `div.question-board` |
| 点完选项，同一次 eval 读 className/checked 还是旧的 | React 异步渲染。状态复查必须**另发一次 eval** |
| 多行 JS 的 `for` 循环被 shell 拒绝（`Could not identify command root`） | 写脚本文件再执行；或直接用 Python 驱动（`exam_lib.ev` 会自动 base64 + IIFE 包装） |
| eval 里直接 `return` 报 `Uncaught SyntaxError` | eval 的 JS 必须是表达式，写 IIFE 或末句为表达式 |
| 刷新页面后题目变了 | 平台重新组卷。**每轮都要重新 `--dump` / `fetch_paper`**，不能复用上一轮的题号 |
| 数美（fengkongcloud）滑块 / 点选验证码 | 纯 JS `el.click()` 过不了（校验 `event.isTrusted`）。只能人工过，或 CDP `/clickAt` 真实鼠标。多账号每个都要重过 |
| 「继续考试」点了没反应 | 考试信息页同文本的 DIV 和 BUTTON 都存在，`div.click()` 无效。**只查 `button`** |
| 某题选项列表是空的（`NOOPT`） | 页面还没渲染完 / 有弹窗遮挡 → 用 `state()` 看一眼再决定 |
| pdf 提取出 0 行 | 扫描件/图片页。OCR 或改标 `推断` |
| 部分条款是图片 | 无法 OCR → 按逻辑推断，**交付时标注** |

---

## 9. 脚本清单

| 文件 | 作用 |
|---|---|
| `scripts/whole_paper.py` | **整卷型**主驱动：`--dump` / `--answers`（`--clear`）/ `--verify`，按题干片段定位，永不提交 |
| `scripts/auto_answer.py` | **逐题型**主驱动：作答 / `--verify` 复验 / `--dump` 抓卷 / `--set` 单题改选 |
| `scripts/exam_lib.py` | CDP 原语 + 优课 DOM 封装：`init` / `inject` / `set_answers` / `state` / `step` / `nav_next` / `goto` / `walk` / `dump` / `verify` / `paper_url` / `sync_fetch` |
| `scripts/inject.js` | 逐题型注入页面：`window.__Y`（`state` / `step` / `nav` / 匹配算法 / `pickIndex`） |
| `scripts/fetch_paper.py` | 逐题型：从页面 `performance` 抠试卷 API 并拉全卷 |
| `scripts/docx_to_text.py` | docx → 每段一行的纯文本 |
| `scripts/pdf_to_text.py` | pdf → 每段一行的纯文本（多文件用 `### FILE:` 分隔） |
| `scripts/grep_evidence.py` | 依据文本多关键词 AND 检索 + 上下文 / 行号区间 |

其他语言调用示例：

```bash
"$PY" -c "import sys;sys.path.insert(0,'$SK/scripts');import exam_lib as E;E.init('<TID>');E.inject();print(E.state())"
```

**离线自测**：想验证整卷型脚本而不碰真考试，可以写一个含 `div.question-board > ol > li > input` 结构的本地 HTML，
用 `/new` 打开 `file:///...` 再跑 `--dump` / `--answers` / `--verify`（记得最后 `/close`）。
故意打乱题序与选项顺序来测，最能暴露「按下标定位」的隐患。
