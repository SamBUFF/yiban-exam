# -*- coding: utf-8 -*-
"""在依据文本里检索条款 —— 用于给出每道题的「一手依据」。

用法:
    python grep_evidence.py <依据.txt> 关键词1 [关键词2 ...] [-c 2] [-n 5]

    -c/--context N   命中行前后各打印 N 行（默认 1）
    -n/--max N       最多打印 N 处命中（默认 5）
    -r/--range A B   直接打印 A..B 行的原文（复核已知行号时用）
    -o/--or          任一关键词命中即算（默认是 AND 全部命中）
    -l/--line N      打印第 N 行及其上下文

示例:
    python grep_evidence.py 依据.txt 抄袭 夹带                  # 找「考试作弊」的条款
    python grep_evidence.py 依据.txt 警告 处分 -c 3             # 注意会同时命中「严重警告处分」
    python grep_evidence.py 依据.txt -r 1578 1584               # 复核行号区间
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f]


def parse_args(argv):
    opts = {"context": 1, "max": 5, "or": False, "range": None, "line": None}
    kws = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-c", "--context"):
            i += 1
            opts["context"] = int(argv[i])
        elif a in ("-n", "--max"):
            i += 1
            opts["max"] = int(argv[i])
        elif a in ("-r", "--range"):
            opts["range"] = (int(argv[i + 1]), int(argv[i + 2]))
            i += 2
        elif a in ("-l", "--line"):
            i += 1
            opts["line"] = int(argv[i])
        elif a in ("-o", "--or"):
            opts["or"] = True
        else:
            kws.append(a)
        i += 1
    return kws, opts


def show(lines, lo, hi, hits=None):
    hits = hits or set()
    for j in range(max(0, lo), min(len(lines), hi)):
        mark = ">" if j in hits else " "
        print("%s%5d | %s" % (mark, j + 1, lines[j][:160]))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = sys.argv[1]
    if not os.path.exists(path):
        print("NOT_FOUND:", path)
        return 2
    lines = load(path)
    kws, opts = parse_args(sys.argv[2:])

    print("# %s  共 %d 行" % (path, len(lines)))

    if opts["range"]:
        lo, hi = opts["range"]
        show(lines, lo - 1, hi)
        print()
    if opts["line"]:
        n = opts["line"]
        show(lines, n - 1 - opts["context"], n + opts["context"], hits={n - 1})
        print()

    if not kws:
        return 0

    hit = 0
    hits = set()
    for i, l in enumerate(lines):
        ok = any(k in l for k in kws) if opts["or"] else all(k in l for k in kws)
        if not ok:
            continue
        hit += 1
        hits.add(i)
        if hit <= opts["max"]:
            print("\n--- 命中 %d（关键词 %s） ---" % (hit, " ".join(kws)))
            show(lines, i - opts["context"], i + opts["context"] + 1, hits={i})
    print("\n# 共 %d 处命中" % hit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
