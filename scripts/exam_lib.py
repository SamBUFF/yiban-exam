# -*- coding: utf-8 -*-
"""优课（易班）在线考试自动作答核心库 —— 配合 web-access skill 的 CDP proxy。

依赖：web-access 的 CDP proxy（默认 http://localhost:3456），复用用户已登录的浏览器。

设计要点（每一条都是实测踩出来的）：
  1. 传 JS 一律 base64 + `decodeURIComponent(escape(atob(...)))`，否则中文会坏、proxy 会 500。
  2. 裸表达式统一包 IIFE，避免 proxy 偶发 500。
  3. 状态读取必须「另发一次 eval」。React 是异步渲染，同一次 eval 里点完就读 className 拿到的是旧值。
  4. 翻页后必须**轮询题号变化**，不能用固定 sleep。

典型用法：
    import exam_lib as E
    E.init(TID)
    E.inject()
    E.set_answers({1: '参加社会实践', 2: '学业成绩未达到'})
    for r in E.walk(): print(r)
    for r in E.verify(): print(r)
"""
import base64
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("CDP_PROXY", "http://localhost:3456")
TIMEOUT = float(os.environ.get("CDP_TIMEOUT", "40"))
TID = os.environ.get("CDP_TARGET")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------- 基础

def init(tid=None, base=None):
    """设定 CDP target id（tab id）。tid 为空则保留环境变量里的值。"""
    global TID, BASE
    if tid:
        TID = str(tid).strip()
    if base:
        BASE = base
    if not TID:
        raise RuntimeError("未指定 target id：E.init('<TID>') 或设置环境变量 CDP_TARGET")
    return TID


def _url(path):
    if not TID:
        raise RuntimeError("未指定 target id：先 E.init('<TID>')")
    return "%s%s?target=%s" % (BASE, path, TID)


def ev(js, retries=4):
    """在页面里执行 JS 并返回值。自动 base64 传输 + IIFE 包装 + 重试退避。"""
    s = js.strip()
    if not (s.startswith("(") and s.endswith(")")) and not s.startswith("(0,eval)"):
        js = "(() => { return %s; })()" % s
    b64 = base64.b64encode(js.encode("utf-8")).decode("ascii")
    wrapper = '(0,eval)(decodeURIComponent(escape(atob("%s"))))' % b64
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                _url("/eval"), data=wrapper.encode("utf-8"), method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, dict) and "value" in d:
                return d["value"]
            return d
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise last


def ev_json(expr):
    """执行返回 JSON 字符串的表达式，自动转成 Python 对象。"""
    v = ev(expr)
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return v
    return v


def targets():
    """列出当前浏览器所有 tab。"""
    req = urllib.request.Request("%s/targets" % BASE)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def open_tab(url):
    """新开后台 tab，返回 target id。"""
    req = urllib.request.Request(
        "%s/new" % BASE, data=str(url).encode("utf-8"), method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def close_tab(tid=None):
    t = tid or TID
    req = urllib.request.Request("%s/close?target=%s" % (BASE, t))
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def screenshot(path):
    req = urllib.request.Request(_url("/screenshot"), method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------------------------------------------------------------- 页面封装

def inject():
    """注入 window.__Y（幂等，保留已设答案）。"""
    with open(os.path.join(HERE, "inject.js"), "r", encoding="utf-8") as f:
        src = f.read()
    return ev(src)


def set_answers(mapping):
    """设置答案表。mapping 形如 {23: '警告处分'} 或 {23: {'key': '警告处分'}}。"""
    payload = {}
    for k, v in mapping.items():
        if isinstance(v, dict):
            v = v.get("key") or v.get("answer") or ""
        payload[str(int(k))] = v
    b64 = base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    # 注意：Y.answers 的键在 JS 里一律是字符串
    js = ('JSON.stringify(window.__Y.setAnswers('
          'JSON.parse(decodeURIComponent(escape(atob("%s"))))))' % b64)
    return ev_json(js)


def set_answer(q, key):
    return ev_json('JSON.stringify(window.__Y.setAnswer(%d, %s))'
                   % (int(q), json.dumps(str(key), ensure_ascii=False)))


def state():
    """读当前页：{q, total, title, opts, sel}。"""
    return ev_json("JSON.stringify(window.__Y.state())")


def step():
    """给当前题选答案，返回 {q, total, status, idx?, title?, opts?}。"""
    return ev_json("JSON.stringify(window.__Y.step())")


def nav_raw(dirn):
    return ev_json("JSON.stringify(window.__Y.nav(%d))" % (1 if dirn >= 0 else -1))


def click_index(i):
    """按下标点第 i 个选项（MISS/AMB 时的手工兜底）。"""
    return ev_json("JSON.stringify(window.__Y.clickIndex(%d))" % int(i))


def _wait_q_change(cur, timeout=8.0, interval=0.15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(interval)
        q = (state() or {}).get("q")
        if q is not None and q != cur:
            return q
    return None


def nav_next(timeout=8.0):
    """点「下一题」并轮询等待题号真的前进。"""
    cur = (state() or {}).get("q")
    nav_raw(1)
    return _wait_q_change(cur, timeout) is not None


def nav_prev(timeout=8.0):
    cur = (state() or {}).get("q")
    nav_raw(-1)
    return _wait_q_change(cur, timeout) is not None


def goto(q, timeout=60.0):
    """一路翻页到第 q 题（双向）。"""
    q = int(q)
    t0 = time.time()
    while time.time() - t0 < timeout:
        cur = (state() or {}).get("q")
        if cur is None:
            return False
        if cur == q:
            return True
        nav_raw(1 if q > cur else -1)
        _wait_q_change(cur, 8.0)
    return False


# ---------------------------------------------------------------- 主流程

def walk(start=None, end=None, delay=0.35, on_row=None):
    """从当前位置顺序作答到 end（默认末题）。返回每题的 step 结果列表。

    start：若当前位置在 start 之前，先快进到 start 再开始答。
    """
    out = []
    while True:
        s = state() or {}
        q, total = s.get("q"), s.get("total")
        if q is None:
            out.append({"status": "NOQ"})
            break
        if start is not None and q < int(start):
            if not nav_next():
                out.append({"q": q, "status": "NAVFAIL"})
                break
            continue
        if end is not None and q > int(end):
            break
        r = step() or {}
        r.setdefault("title", s.get("title"))
        out.append(r)
        if on_row:
            on_row(r)
        if total is not None and q >= total:
            break
        time.sleep(delay)
        if not nav_next():
            out.append({"q": q, "status": "NAVFAIL"})
            break
    return out


def dump(end=None):
    """只读方式走完全卷：题号 / 题干 / 选项 / 已选。用于 API 拿不到卷子时的兜底。"""
    goto(1)
    rows = []
    while True:
        s = state() or {}
        q, total = s.get("q"), s.get("total")
        if q is None:
            break
        rows.append(s)
        if end is not None and q >= int(end):
            break
        if total is not None and q >= total:
            break
        if not nav_next():
            break
    return rows


def verify(end=None):
    """全量复验：回到第 1 题后走到底，逐题回读 sel。"""
    return dump(end=end)


# ---------------------------------------------------------------- 试卷 API

def paper_url():
    """从 performance 里抠出试卷接口的完整 URL（含 token / yibanId / examuserId）。"""
    js = ("(()=>{var es=performance.getEntriesByType('resource');var u='';"
          "for(var i=0;i<es.length;i++){"
          "if(es[i].name.indexOf('/api/exam/paper/get')>=0)u=es[i].name;}"
          "return u;})()")
    return ev(js)


def sync_fetch(url):
    """在页面上下文里同步 XHR 拉取（同源/已 CORS 的接口，自动带 Cookie）。"""
    js = ("(()=>{var x=new XMLHttpRequest();"
          "x.open('GET',%s,false);x.withCredentials=true;x.send();"
          "return x.responseText;})()" % json.dumps(url))
    return ev(js, retries=1)
