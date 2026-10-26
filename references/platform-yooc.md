# 优课（易班）考试平台 —— 平台特征 / API / DOM

> 实测日期：2026-08-26（广东工程职业技术学院「学生手册」考试，3 套卷 × 50 题）
> 早期实测：2026-09-20（判断题套卷，25 题 × 4 分，3 个账号）
> 新增：2026-10-05（「丹心贺华诞 戎装砺青春」知识竞答，**整卷型** 10 题 = 6 单选 + 4 多选）
> 当作「可能有效的提示」，不是「保证正确的事实」。对不上就回退通用模式并更新本文。

## 域名与架构

| 项 | 值 |
|---|---|
| 前端 | `exam.yooc.me`（易班旗下优课） |
| 后端 API | `exambackend.yooc.me`（跨域，但前端自己 fetch，所以在页面上下文里请求天然满足 CORS + Cookie） |
| 技术栈 | React + SSR 水合；样式全是 `jsx-<hash>` 类名（**哈希随构建变化，绝不能当选择器**） |
| 渲染方式 | **两种卷型**（见下）：逐题型一次只渲染一题；整卷型全卷同页 |
| 鉴权 | 全靠 URL query：`token=<32位hex>` + `yibanId=<易班ID>`，另带 `userId` / `examuserId`。没有额外签名 |

## 两种卷型（2026-10-05 新增）

考试设置区会写「答题提交方式」和「出题类型」，据此分流：

| | 逐题型 | 整卷型 |
|---|---|---|
| 设置 | 逐题提交 / 未标注 | **整卷提交** + 出题类型「整卷型」 |
| URL | `/exam/<id>/take` | **`/exam/<id>/detail`**（标题写「考试详情」，实为答题界面） |
| 渲染 | 一次一题 | 全卷一次性渲染同页 |
| 翻页 | 「上一题 / 下一题」按钮 | **没有**翻页按钮；页脚「保存试卷 / 提交试卷」+ 侧栏「题目大纲」 |
| 定位 | `main h3` 题干 + `ul > li` 选项 | `div.question-board` 每题一个容器 + 容器内 `ol > li` |
| 脚本 | `auto_answer.py` | `whole_paper.py` |

判据一句话：`document.querySelectorAll('div.question-board').length > 0` → 整卷型。

整卷型实测卷面（10 题 / 100 分 / 90 分钟）：6 单选 × 10 分 + 4 多选 × 10 分，
两个 section 的中文题号**各自从 1 重新计数**（单选 1..6、多选 1..4），所以「题号」在整卷型里不是全局唯一的，
**别用题号当答案表的键**。


## API 端点

| 用途 | 端点 |
|---|---|
| 试卷（含全部 section/subjects） | `GET /api/exam/paper/get?examuserId=<id>&token=<t>&yibanId=<y>` |
| 考试设置 | `GET /api/exam/setting/get?examId=<id>&userId=<u>&token=<t>&yibanId=<y>` |
| 开始考试 | `GET /api/exam/start/action?token=<t>&yibanId=<y>` |
| 数美验证结果校验 | `GET /api/shumei/captcha/check?token=<t>&yibanId=<y>` |
| 进入前校验 | `GET /api/exam/user/check?groupId=<g>&userId=<u>&token=<t>&yibanId=<y>` |

**不要自己拼 URL** —— 直接从 `performance` 里捞页面刚发过的那一条（见 `fetch_paper.py`），token 每次会话都不同。

### 返回体结构

```json
{"result": true,
 "end": "<base64 32 字节>",
 "data": [
   {"sectionId": "...", "sectionName": "...",
    "subjects": [
      {"subjectId": "...", "type": "choice", "points": 2,
       "inputs": 1,
       "title": ["题干..."],
       "option": [["A. xxx"], ["B. xxx"], ["C. xxx"], ["D. xxx"]],
       "answer": "aWrE2QvX7bIkLrH0f/uLVw=="}
    ]}
 ]}
```

### ⚠️ `answer` 字段不可用（两次独立实测）

- 整卷**所有题的 `answer` 密文完全相同**。
- 拿 `end`（32 字节，疑似 AES-256 key）试过 `aes-256-ecb / 192 / 128` 及常见固定 key，全是乱码。
- 结论：**占位/干扰值**。答案只能来自用户给的资料。

### `examuserId=0` 的坑

部分账号拿到的接口是 `?examuserId=0&token=...`，页面首次调用成功，**再 fetch 一次返回 `{"result":false,"message":"当前用户未参加考试！"}`**（一次性）。
这类账号改走 `auto_answer.py --dump`（逐题翻页抓 DOM），或「正序读题 + 倒序作答」省一趟路。

## 页面 DOM 约定

### 逐题型

| 目标 | 定位方式 |
|---|---|
| 选项列表 | `document.querySelectorAll('ul')` 中，第一个 `li` 文本匹配 `/^[AＡ]\s*[.．、]/` 且所有 `li` 非空的那个；多个命中取 `li` 最多的 |
| 选项节点 | 上面的 `ul` 下的 `li`（实测类名形如 `jsx-2160564469 flex items-center`，**别写死**） |
| 选中标志 | 点中后 `li.className` 追加 `_c` |
| 题号 | `h3` 文本形如 `1、[2分] 题干...`，取 `^(\d+)[、.．]`；兜底用 `body.innerText` 匹配 `(\d+)\s*\/\s*(\d+)` |
| 总题数 | `body.innerText` 里的 `(\d+)\s*\/\s*(\d+)` 第二组（如 `1 / 50`） |
| 题干 | `document.querySelector('main h3')` → 剥掉 `^\d+[、.]` 与 `^\[[^\]]*\]` 前缀 |
| 翻页 | `button` 里 `innerText.trim() === '下一题'` / `'上一题'` |
| 交卷 | `button` 里 `innerText.trim() === '交卷'`（**本 skill 不点**） |

**选项顺序每次组卷都会打乱** —— 同一道题在两套卷里 A/B/C/D 位置不同。必须按文本内容匹配。

### 整卷型（2026-10-05 实测）

```html
<div class="question-board">
  <h3>1、[10分] 中华人民共和国的国旗是（）</h3>
  <ol>
    <li><input type="radio" name="87897550_1"> C. 红旗</li>
    <li><input type="radio" name="87897550_1"> B. 五星红旗</li>
    <li><input type="radio" name="87897550_1"> A. 星条旗</li>
    <li><input type="radio" name="87897550_1"> D. 三色旗</li>
  </ol>
</div>
```

| 目标 | 定位方式 |
|---|---|
| 题目容器 | `document.querySelectorAll('div.question-board')`（一题一个，顺序随组卷打乱） |
| 选项 | 容器内 `ol > li`，**每个 `li` 里含一个 `<input>`** |
| 题型 | `input.type`：`radio` = 单选、`checkbox` = 多选 |
| 分组 | `input.name = <subjectId>_1`（如 `87897550_1`），同组 4 个 |
| 选项文本 | **`li.innerText`**（形如 `B. 五星红旗`）—— 注意 `li` 外层**没有 `label` 包裹**，`el.closest('label')` 返回 `null`，不能靠 label 找文本 |
| 选中标志 | `input.checked`（比逐题型的 `_c` 类名可靠） |
| 题干 | 容器 `innerText` 减掉 `ol.innerText`（整卷型题干**不在 `h3` 里**，虽然 DOM 里有 `h3` 但 `whole_paper.py` 走的是"容器文本 − 选项文本"这条路，更抗改版） |
| 提交 | 页脚「保存试卷 / 提交试卷」（**本 skill 不点**） |

整卷型实测数字：10 题 → 24 个 `radio` + 16 个 `checkbox` = 41 个 `input`（多出来的 1 个是页面里无关的 `type=text`，别按总数判断）。

**点击方式**：`li.querySelector('input').click()` 直接生效，React 会同步 `checked`。
- 复选**必须先判 `!inp.checked`**，否则会把已勾的取消掉。
- 单选直接点即可（同组互斥由浏览器保证）。

⚠️ **整卷型的「是否顺序打乱」也可能是「是」** → 题目顺序和选项顺序都会变。
所以答案表**绝不能按题号或下标**，只能按题干文本片段定位（`whole_paper.py` 的 `q` 字段）。


## 交互要点

- 点选项：直接 `li.click()` 即可（React 事件委托在 root，冒泡能触发）。
- **点击后同一次 eval 读到的 className 是旧值**（React 异步渲染）→ 状态复查必须另发一次 eval。
- 翻页后**轮询题号变化**再继续，别用固定 sleep。`exam_lib.nav_next()` 已封装（默认 8s 超时，间隔 150ms）。
- 同步 XHR（`xhr.open(..., false)`）**不能**等待 React 重渲染完成 → 翻页节奏只能由外部循环驱动。

## 反爬 / 验证码

进入正式答题前可能弹一层 **数美（fengkongcloud）滑块 / 点选验证码**：

- 纯 JS 合成点击（`el.click()`）**过不了** —— 数美校验 `event.isTrusted`。
- 只能人工过，或用 CDP `Input.dispatchMouseEvent`（proxy 的 `/clickAt`）派发真实鼠标事件。
- 验证码图 URL（`castatic.fengkongcloud.cn/crb/spatial_select/...`）**是一次性的**，事后再下载会 404，只能靠截图分析。
- 多账号场景：**每个新账号都会重新弹一次**，且是进入答题页之后才弹。流程只能做成「脚本进入 → 通知用户过验证码 → 用户说好了 → 继续」。

## 交卷（仅作说明，本 skill 不执行）

```
button[innerText='交卷'].click()
→ 等 ~1.2s，浮层出现「取消 / 确定」
→ 找 innerText === '确定' 的叶子元素（el.children.length === 0）并 .click()
→ 等 ~3s，body.innerText 出现「本次考试成绩 X分 / 实际得分率 X%」
```

出分页若显示「该考试禁止查卷」，交卷后看不到逐题对错 → **交卷前务必自查**。

## 入口按钮的坑

考试信息页的「继续考试」在 DOM 里**同时存在外层 DIV 和内层 BUTTON 两个同文本节点**。
`querySelectorAll('button, div, a')` 按文本匹配会先命中 DIV，而 `div.click()` 什么都不会发生，看起来像脚本失效。
**只查 `button`** 再按文本匹配。

## 诊断：tab 被关掉了（2026-10-05 踩到）

答题页一旦被用户关闭（很常见：交完卷顺手关页），proxy 还在、`/targets` 也正常返回别的 tab，
但对旧 target 的任何请求都会**静默失败**：

| 请求 | 表现 |
|---|---|
| `GET /info?target=<旧id>` | 返回 `{}`（正常是带 `title` / `url` / `ready` 的 JSON） |
| `POST /eval?target=<旧id>` | **HTTP 200 但 body 为空串** |
| Python 侧 | `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` |

**排查顺序**（别一上来就怀疑 proxy 或脚本）：
1. `curl -s http://localhost:3456/targets` —— 列表里还有没有那个 target id？
2. `curl -s "http://localhost:3456/info?target=<TID>"` —— 是不是 `{}`？
3. 确认是 tab 没了 → 重新 `/targets` 拿新 id，或请用户重新打开考试页。

同理，`exam_lib.ev()` 有 4 次重试，遇到这种"空 body"会重试 4 次再抛错，
看起来像是网络抖动，实际是 target 已失效。

