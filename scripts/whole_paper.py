# -*- coding: utf-8 -*-
"""整卷型（「整卷提交 / 整卷型」）优课考试页面驱动 —— 所有题同页渲染，无翻页。

与逐题型的 auto_answer.py 是**两条独立链路**，别混用：
  · 逐题型：`div.question-board` 不存在，题目一次只渲染一题，靠「上一题/下一题」翻页。
  · 整卷型：URL 就是 /exam/<id>/detail（标题写“考试详情”但其实就是答题界面），
            全卷一次性 SSR 出来，无翻页按钮，页脚是「保存试卷 / 提交试卷」。

**本脚本永不点提交/交卷。**

用法:
    # 1) 先看卷子（打印题号/题型/题干/选项/当前是否已选）
    python whole_paper.py --tid <TID> --dump
    python whole_paper.py --tid <TID> --dump --json paper.json

    # 2) 作答（answers.json 见下）
    python whole_paper.py --tid <TID> --answers answers.json
    python whole_paper.py --tid <TID> --answers answers.json --clear   # 先清空再勾

    # 3) 全量复验（另发一次 eval 回读，必做）
    python whole_paper.py --tid <TID> --verify --answers answers.json

answers.json 格式（**列表**，每项一题）:
    [
      {"q": "中华人民共和国的国旗是", "a": ["五星红旗"]},
      {"q": "国庆节是每年",           "a": ["10月1日"]},
      {"q": "校园军训基本要求包含",     "a": ["按要求统一着装", "训练中严禁嬉笑打闹"]}
    ]
  · `q` 是**题干里唯一的片段**（去掉所有空白后做子串匹配）。命中必须唯一，否则报 AMBIG。
  · `a` 是选项**原文**（或唯一子串），脚本会归一化后精确相等匹配，逐个点击。
  · 也接受 {"i": 3, "a": [...]} 形式（0-based 题序）—— 仅在题干不好摘录时用，
    **注意本卷型「是否顺序打乱」可能是「是」，刷新/重渲染后下标会变**，能用 q 就别用 i。

为什么按题干定位而不是按下标：整卷型同样可能开启「顺序打乱」和「选项打乱」，
下标在重新组卷后完全不可靠；题干片段是唯一稳定的锚。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exam_lib as E  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# ---------------------------------------------------------------- 页面 JS

NORM_JS = ('function norm(s){return (s||"").replace(/^[A-DＡ-Ｄ]\\s*[.．、]\\s*/,"")'
           '.replace(/\\s+/g,"").trim();}')

# 扫描全卷：返回 JSON 字符串。题干 = 容器文本减掉 <ol> 的文本。
SCAN_JS = """
(function(){
  __NORM__
  var boards=document.querySelectorAll("div.question-board");
  var out=[];
  for(var i=0;i<boards.length;i++){
    var b=boards[i];
    var ins=b.querySelectorAll("input");
    var ol=b.querySelector("ol");
    var lis=b.querySelectorAll("li");
    var opts=[];
    for(var j=0;j<lis.length;j++){
      var raw=lis[j].innerText.trim().replace(/\\s+/g," ");
      var inp=lis[j].querySelector("input");
      opts.push({t:raw,n:norm(raw),sel:!!(inp&&inp.checked)});
    }
    var full=b.innerText.trim().replace(/\\s+/g," ");
    var stem=full;
    if(ol){var ot=ol.innerText.trim().replace(/\\s+/g," ");if(ot)stem=full.split(ot).join(" ");}
    stem=stem.replace(/\\s+/g,"");
    if(stem.length<4)stem=full.replace(/\\s+/g,"");
    out.push({i:i,type:ins.length?ins[0].type:"",name:(ins.length&&ins[0].name)||"",
              stem:stem,opts:opts});
  }
  return JSON.stringify(out);
})()
""".replace("__NORM__", NORM_JS)

CLEAR_JS = """
(function(){
  var n=0,bs=document.querySelectorAll("div.question-board");
  for(var i=0;i<bs.length;i++){
    var ins=bs[i].querySelectorAll("input");
    for(var j=0;j<ins.length;j++){if(ins[j].checked){ins[j].click();n++;}}
  }
  return n;
})()
"""

FILL_JS = """
(function(){
  __NORM__
  var ANS=__ANS__;
  var items=JSON.parse((__SCAN__));
  var boards=document.querySelectorAll("div.question-board");
  var rep=[];
  for(var k=0;k<ANS.length;k++){
    var w=ANS[k]||{};
    var arr=w.a; if(typeof arr==="string")arr=[arr]; if(!arr)arr=[];
    var keys=[]; for(var z=0;z<arr.length;z++)keys.push(norm(arr[z]));
    var hit=-1;
    if(w.q){
      var q=norm(w.q);
      for(var i=0;i<items.length;i++){
        if(items[i].stem.indexOf(q)>=0){ if(hit>=0){hit=-2;break;} hit=i; }
      }
    }else if(typeof w.i==="number"){ hit=w.i; }
    if(hit<0){ rep.push({k:k,q:w.q,status:(hit===-2)?"AMBIG":"NOQ"}); continue; }
    var it=items[hit],got=[],miss=[];
    for(var j=0;j<it.opts.length;j++){
      if(keys.indexOf(it.opts[j].n)>=0){
        got.push(it.opts[j].t);
        var li=boards[it.i].querySelectorAll("li")[j];
        var inp=li.querySelector("input");
        /* 复选必须先判 checked，否则会把已勾的取消掉 */
        if(inp&&!inp.checked)inp.click();
      }
    }
    for(var m=0;m<keys.length;m++){
      var ok=false;
      for(var j2=0;j2<it.opts.length;j2++)if(it.opts[j2].n===keys[m])ok=true;
      if(!ok)miss.push(arr[m]);
    }
    var row={k:k,q:w.q,qi:it.i,type:it.type,stem:it.stem,
             status:(miss.length?"MISS":"OK"),want:arr,got:got,miss:miss};
    if(miss.length)row.opts=it.opts.map(function(o){return o.t;});
    rep.push(row);
  }
  return JSON.stringify(rep);
})()
"""


def fill_js(answers):
    return (FILL_JS.replace("__NORM__", NORM_JS)
                   .replace("__ANS__", json.dumps(answers, ensure_ascii=False))
                   .replace("__SCAN__", SCAN_JS))


_LEAD = re.compile(r"^[A-DＡ-Ｄ]\s*[.．、]\s*")


def pnorm(s):
    """Python 侧同款归一化：去选项字母前缀 + 去所有空白。"""
    return re.sub(r"\s+", "", _LEAD.sub("", (s or "").strip()))


# ---------------------------------------------------------------- 动作

def scan():
    return E.ev_json(SCAN_JS)


def do_dump(rows):
    print("共 %d 题" % len(rows))
    for r in rows:
        print("\nQ%-3d [%s] %s" % (r["i"] + 1, r["type"], r["stem"]))
        for o in r["opts"]:
            print("      %s %s" % ("[x]" if o.get("sel") else "[ ]", o["t"]))
    return rows


def do_fill(answers, clear=False):
    if clear:
        print("已清空 %d 处勾选" % E.ev(CLEAR_JS))
    rows = scan()
    print("页面共 %d 题；answers 共 %d 条" % (len(rows), len(answers)))
    rep = E.ev_json(fill_js(answers))
    bad = 0
    for r in rep:
        st = r.get("status")
        if st == "OK":
            print("  OK   Q%-3d <- %s" % (r["qi"] + 1, "、".join(r.get("got") or [])))
        else:
            bad += 1
            print("  !!   #%d [%s] q=%r" % (r["k"] + 1, st, r.get("q")))
            if st == "AMBIG":
                print("       题干片段命中多题 → 换更长、更唯一的片段")
            elif st == "NOQ":
                print("       题干片段一题都没命中 → 检查是否抄错（已去空白后做子串匹配）")
            elif st == "MISS":
                print("       要选的选项没找到：%s"
                      % json.dumps(r.get("miss"), ensure_ascii=False))
                print("       该题实际选项：%s"
                      % json.dumps(r.get("opts"), ensure_ascii=False))
    print("\n结果：%d/%d 条成功勾选" % (len(rep) - bad, len(rep)))
    return rep


def do_verify(answers):
    """必须由**另一次** eval 回读（React 异步渲染，同一次读到的还是旧值）。"""
    rows = scan()
    answered = 0
    for r in rows:
        sel = [o["t"] for o in r["opts"] if o.get("sel")]
        if sel:
            answered += 1
        print("%s Q%-3d [%s] sel=%s"
              % ("  " if sel else "!!", r["i"] + 1, r["type"],
                 json.dumps(sel, ensure_ascii=False)))
    print("\n已作答 %d / %d 题；未作答 %d 题" % (answered, len(rows), len(rows) - answered))

    rc = 0 if answered == len(rows) else 1
    if not answers:
        return rc

    bad = []
    for w in answers:
        arr = w.get("a")
        if isinstance(arr, str):
            arr = [arr]
        arr = arr or []
        key = re.sub(r"\s+", "", w.get("q") or "")
        target = None
        if key:
            for r in rows:
                if key in r["stem"]:
                    target = r
                    break
        if target is None and isinstance(w.get("i"), int) and w["i"] < len(rows):
            target = rows[w["i"]]
        if target is None:
            bad.append((w, "题干未命中页面任何一题"))
            continue
        seln = [pnorm(o["t"]) for o in target["opts"] if o.get("sel")]
        for a in arr:
            if pnorm(a) not in seln:
                bad.append((w, "漏选/错选：%s" % a))
    if bad:
        print("\n[FAIL] answers 与页面实际勾选不一致 %d 处：" % len(bad))
        for w, why in bad:
            print("   - q=%r  %s" % (w.get("q"), why))
        return 1
    print("\n[OK] answers 与页面实际勾选完全一致")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tid", required=True, help="考试页所在 tab 的 CDP target id")
    ap.add_argument("--base", default=None, help="CDP proxy 地址（默认 localhost:3456）")
    ap.add_argument("--dump", action="store_true", help="只读打印全卷")
    ap.add_argument("--json", default=None, help="配合 --dump 落地 JSON")
    ap.add_argument("--answers", default=None, help="answers.json 路径")
    ap.add_argument("--clear", action="store_true", help="作答前先清空所有勾选")
    ap.add_argument("--verify", action="store_true", help="回读页面实际勾选并对照 answers")
    a = ap.parse_args()

    E.init(a.tid, a.base)
    if not (a.dump or a.verify or a.answers):
        ap.error("至少给一个动作：--dump / --answers / --verify")

    answers = None
    if a.answers:
        with open(a.answers, "r", encoding="utf-8") as f:
            answers = json.load(f)
        if isinstance(answers, dict):  # 兼容 {"0": ["A选项"], ...}
            answers = [{"i": int(k), "a": v} for k, v in answers.items()]

    if a.dump:
        rows = scan()
        do_dump(rows)
        if a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            print("\n已写 %s" % a.json)
        return 0

    if a.verify:
        return do_verify(answers)

    rep = do_fill(answers, clear=a.clear)
    print("\n提示：下一步另跑一次 --verify 复核；**不要点「提交试卷」**。")
    return 0 if all(r.get("status") == "OK" for r in rep) else 1


if __name__ == "__main__":
    sys.exit(main())
