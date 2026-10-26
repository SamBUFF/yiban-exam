# -*- coding: utf-8 -*-
"""从优课（易班）考试页面抠出试卷 API 并一次拉全卷。

用法:
    python fetch_paper.py <targetId> [out.json]

原理:
    试卷接口的完整 URL（带 token / yibanId / examuserId）就躺在页面的
    performance resource timeline 里，不用自己拼参数。
    拿到 URL 后在**页面上下文**里同步 XHR 请求 —— 同源策略/CORS/Cookie 全部天然满足。

输出:
    落地一份 JSON（原始响应）+ 打印可读题面清单。

注意:
    返回体里的 answer 字段是占位/干扰值（整卷所有题密文相同），**不能拿来抄答案**。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exam_lib as E  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main():
    tid = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CDP_TARGET")
    out = sys.argv[2] if len(sys.argv) > 2 else "试卷.json"
    E.init(tid)

    url = E.paper_url()
    if not url:
        print("PAPER_URL_NOT_FOUND")
        print("  → 确认当前 tab 停在答题页，且页面已经加载过一次试卷（刷新一下再试）")
        print("  → 若该账号的接口是 examuserId=0，可能只能调一次；改用 auto_answer.py --dump")
        return 2
    print("URL:", url)

    text = E.sync_fetch(url)
    if not text:
        print("EMPTY_RESPONSE")
        return 3
    try:
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        print("BAD_JSON:", e, text[:300])
        return 3

    if isinstance(data, dict) and data.get("result") is False:
        print("API_ERROR:", data.get("message"))
        return 4

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    n = 0
    for sec in (data.get("data") or []):
        print("\n== %s ==" % sec.get("sectionName"))
        for s in (sec.get("subjects") or []):
            n += 1
            title = s.get("title")
            if isinstance(title, list):
                title = title[0] if title else ""
            print("%d | sid=%s | %s分 | %s"
                  % (n, s.get("subjectId"), s.get("points"), title))
            for o in (s.get("option") or []):
                print("      -", o if isinstance(o, str) else " / ".join(map(str, o)))

    print("\n共 %d 题 → %s" % (n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
