# -*- coding: utf-8 -*-
"""易班/优课考试自动作答主驱动。

用法:
    # 作答（从 start 到 end，默认 1..末题）
    python auto_answer.py --tid <TID> --answers answers.json

    # 全量复验：回到第 1 题后走到底，逐题回读已选项
    python auto_answer.py --tid <TID> --verify

    # 只读抓卷（API 拿不到时的兜底）
    python auto_answer.py --tid <TID> --dump

    # 单题手工改选
    python auto_answer.py --tid <TID> --set 23 --key "警告处分"
    python auto_answer.py --tid <TID> --set 23 --index 3

answers.json 两种写法都支持：
    {"23": "警告处分"}
    {"23": {"key": "警告处分", "note": "L1580 抄袭夹带=考试作弊"}}

硬边界：本脚本**不会**点「交卷」。作答完由用户自己决定是否交卷。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exam_lib as E  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_answers(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_log(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tid", default=os.environ.get("CDP_TARGET"))
    ap.add_argument("--answers", help="answers.json 路径")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--set", type=int, help="单题改选的题号")
    ap.add_argument("--key", help="配合 --set：新的匹配关键词")
    ap.add_argument("--index", type=int, help="配合 --set：直接按下标点第几个选项")
    ap.add_argument("--log", help="把结果写进 JSON 文件")
    args = ap.parse_args()

    E.init(args.tid)
    E.inject()

    # ------------------------------------------------ 单题改选
    if args.set:
        if not E.goto(args.set):
            print("GOTO_FAIL %d" % args.set)
            return 5
        if args.key:
            E.set_answer(args.set, args.key)
        if args.index is not None:
            print("clickIndex:", E.click_index(args.index))
        print("step:", json.dumps(E.step(), ensure_ascii=False))
        return 0

    # ------------------------------------------------ 只读抓卷
    if args.dump:
        rows = E.dump(end=args.end)
        for s in rows:
            print("%s | %s" % (s.get("q"), s.get("title")))
            for i, o in enumerate(s.get("opts") or []):
                mark = "*" if i in (s.get("sel") or []) else " "
                print("   %s[%d] %s" % (mark, i, o))
        if args.log:
            save_log(args.log, rows)
        print("\n共 %d 题（只读，未作答）" % len(rows))
        return 0

    # ------------------------------------------------ 全量复验
    if args.verify:
        rows = E.verify(end=args.end)
        bad = []
        for s in rows:
            sel = s.get("sel") or []
            tag = "OK " if sel else "!! "
            if not sel:
                bad.append(s.get("q"))
            print("%s%s/%s | sel=%s | %s"
                  % (tag, s.get("q"), s.get("total"), sel, s.get("title")))
        if args.log:
            save_log(args.log, rows)
        print("\n复验 %d 题，未选中 %d 题：%s" % (len(rows), len(bad), bad))
        return 0 if not bad else 6

    # ------------------------------------------------ 作答
    if not args.answers:
        print("需要 --answers answers.json，或 --verify / --dump / --set")
        return 1

    answers = load_answers(args.answers)
    n = E.set_answers(answers)
    print("已注入 %s 条答案" % n)

    rows = E.walk(start=args.start, end=args.end, delay=args.delay,
                  on_row=lambda r: print(json.dumps(r, ensure_ascii=False)))
    if args.log:
        save_log(args.log, rows)

    from collections import Counter
    cnt = Counter(r.get("status") for r in rows)
    print("\n结果统计:", dict(cnt))
    problem = [r for r in rows if r.get("status") not in ("clicked", "already")]
    if problem:
        print("\n需要人工介入的题：")
        for r in problem:
            print("  q=%s status=%s key=%s" % (r.get("q"), r.get("status"), r.get("key")))
            for i, o in enumerate(r.get("opts") or []):
                print("      [%d] %s" % (i, o))
        return 7
    print("\n全部作答完成 —— 未交卷，请用户自行确认后交卷。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
