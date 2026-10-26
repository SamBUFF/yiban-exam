# yiban-exam

> 优课 / 易班在线考试（exam.yooc.me）自动作答 Skill：依据你给的本地资料（学生手册、复习资料、法规原文等 docx / pdf / txt），一次拉全卷、逐题在资料里找到条款、按**选项文本**匹配注入、全量复验 —— 但**绝不点交卷**。

这是一个 **Agent Skill**（`SKILL.md` + Python 驱动脚本），供支持 skill 机制的 AI Agent（如 [WorkBuddy](https://www.workbuddy.cn)）加载后按流程操作浏览器，不是开箱即用的独立程序。

---

## 三条硬边界

这三条写在脚本层面，不靠自觉：

1. **不点「交卷」。** 交卷不可逆。脚本只负责把选项选上，做完明确告诉你「已全部作答、未交卷」。同理不点任何"提交 / 确认"类按钮（含整卷型的「提交试卷」）。
2. **不猜答案。** 每题必须能在依据文本里指出条款（行号 + 原句）。查不到就标 `推断`，并在交付时单独列出原因，绝不静默。
3. **按文本匹配选项，不按字母也不按下标。** 平台会打乱**选项顺序**，整卷型连**题目顺序**也打乱，`A/B/C/D` 和下标都不可靠。

---

## 支持两种卷型

| 卷型 | 判据 | 页面特征 | 驱动脚本 |
|---|---|---|---|
| **逐题型** | 未标注「整卷」/「逐题提交」 | 一次渲染一题，有「上一题 / 下一题」 | `auto_answer.py` |
| **整卷型** | 「整卷提交」+「整卷型」 | 全卷同页，无翻页，页脚「保存试卷 / 提交试卷」+ 侧栏题目大纲 | `whole_paper.py` |

一行判据：`document.querySelectorAll('div.question-board').length > 0` 即整卷型。
（整卷型的 URL 是 `/exam/<id>/detail`，标题写着「考试详情」，但它就是答题界面 —— 别去找「开始考试」。）

---

## 工作流

```
资料(docx/pdf) → 每段一行的依据文本 → 一次拿全卷 → 逐题定答案(带行号) → 注入勾选 → 另发一次 eval 复验 → 交给用户交卷
```

| 步骤 | 命令 |
|---|---|
| 资料转文本 | `docx_to_text.py 学生手册.docx 依据.txt` / `pdf_to_text.py 依据.txt 国旗法.pdf ...` |
| 检索条款 | `grep_evidence.py 依据.txt 抄袭 夹带 -c 2` |
| 拉全卷 | 整卷型 `whole_paper.py --tid <TID> --dump`；逐题型 `fetch_paper.py <TID> 试卷.json` |
| 注入作答 | `whole_paper.py --tid <TID> --answers answers.json` / `auto_answer.py --tid <TID> --answers answers.json` |
| 全量复验 | 加 `--verify`（另发一次 eval 回读，React 异步渲染必须分两次读） |

产出物是一份 `考试答案清单.md`：题号 / 题目摘要 / 所选答案 / **资料条款行号**。依据列不能省，那是复核的依据。

---

## 安装

```bash
git clone https://github.com/SamBUFF/yiban-exam.git "$HOME/.workbuddy/skills/yiban-exam"
```

### 依赖

| 依赖 | 说明 |
|---|---|
| **Python 3.9+** | 脚本只用标准库 + `pypdf`（PDF 场景）|
| `pypdf` | `pip install pypdf`，仅处理 PDF 资料时需要 |
| **web-access** Skill | 提供 CDP proxy，复用你已登录的浏览器；考试有状态，必须在**你已进入答题的那个 tab** 上操作 |

```bash
node "$HOME/.workbuddy/skills/web-access/scripts/check-deps.mjs"
SK="$HOME/.workbuddy/skills/yiban-exam"
```

---

## 快速开始

```bash
# 1. 从 /targets 里找到你正在答题的那个 tab id
curl -s http://localhost:3456/targets

# 2. 先把资料变成可检索文本
python "$SK/scripts/docx_to_text.py" "~/Downloads/学生手册.docx" 依据.txt

# 3. 一次拿全卷（整卷型；逐题型改用 fetch_paper.py）
python "$SK/scripts/whole_paper.py" --tid <TID> --dump --json 试卷.json

# 4. 逐题在依据里找条款 → 写 answers.json（整卷型用题干片段定位）
python "$SK/scripts/grep_evidence.py" 依据.txt 抄袭 夹带 -c 2

# 5. 注入作答（永不提交）
python "$SK/scripts/whole_paper.py" --tid <TID> --answers answers.json --clear

# 6. 另发一次 eval 复验
python "$SK/scripts/whole_paper.py" --tid <TID> --verify --answers answers.json
```

---

## 目录结构

```
SKILL.md
references/
  platform-yooc.md      # 优课 API 与 DOM 结构、鉴权方式、已知陷阱
  answer-matching.md    # 匹配算法：包含关系误匹配等
  document-evidence.md  # docx/pdf 取文本与检索策略
scripts/
  whole_paper.py        # 整卷型主驱动：--dump / --answers / --verify
  auto_answer.py        # 逐题型主驱动：作答 / 复验 / 抓卷 / 单题改选
  exam_lib.py           # CDP 原语 + 优课 DOM 封装
  inject.js             # 逐题型注入页面的 window.__Y
  fetch_paper.py        # 从 performance 抠试卷 API 并拉全卷
  docx_to_text.py       # docx → 每段一行
  pdf_to_text.py        # pdf  → 每段一行（多文件 ### FILE: 分隔）
  grep_evidence.py      # 多关键词 AND 检索 + 行号区间
```

---

## 几个踩过的坑

| 现象 | 原因 |
|---|---|
| `/eval` 返回空 body，Python 报 `Expecting value: line 1 column 1` | tab 已被关闭（多是交卷后关了页）。`/info?target=` 返回 `{}` 即确诊 |
| 「警告处分」选中了「严重警告处分」 | 双向 `includes` 的必然结果。只允许单向匹配（选项包含关键词且候选唯一） |
| 整卷型按题号作答，重跑后全错位 | 题序被打乱。必须用**题干片段**定位 |
| 复选框越点越少 | 已选中的 `input.click()` 会取消勾选，必须先判 `!inp.checked` |
| 点完选项立刻读 `checked` 还是旧值 | React 异步渲染，复验必须另发一次 eval |
| 试卷接口返回的 `answer` 字段 | 是占位 / 干扰值（全卷密文相同，各种 AES 模式都解不开），绝不能抄 |
| 数美（fengkongcloud）滑块 / 点选 | 纯 JS `el.click()` 过不了（校验 `event.isTrusted`），只能人工过 |

---

## 免责声明

本项目仅供**个人学习效率**用途，作答结果需由使用者自行确认后再交卷。使用前请确认符合所在学校的考试纪律与平台服务条款；自动化操作可能被平台判定为异常行为，由此产生的后果由使用者自行承担。

## License

[MIT](LICENSE) © 2026 SamBUFF
