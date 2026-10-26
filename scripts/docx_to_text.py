# -*- coding: utf-8 -*-
"""把 .docx 抽成「每段一行」的纯文本 —— 作为答题的唯一一手依据。

用法:
    python docx_to_text.py <input.docx> [output.txt]

为什么要自己解:
    实测中文路径的 docx 在 doc_to_image / 文档类 MCP 工具上会报 file not found，
    改英文名后又在 COS 上传环节失败（缺 upload_to_cos.py）。
    直接解 docx 的 zip + word/document.xml 最稳，且段落顺序与原文一致
    （表格单元格本身就是 w:p，天然按文档顺序排在流里）。

产出:
    每行一个段落，行号 = 段号。之后引用依据时写成「L1580 抄袭夹带=考试作弊」。
"""
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

PARA_SPLIT = re.compile(r"</w:p>")
TEXT_RUN = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")
BREAK_RUN = re.compile(r"<w:(?:br|tab)\b[^>]*/>")


def extract(path):
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if n == "word/document.xml"]
    if not names:
        raise RuntimeError("不是有效的 docx（缺 word/document.xml）：%s" % path)

    out = []
    for name in names:
        xml = z.read(name).decode("utf-8", "ignore")
        xml = BREAK_RUN.sub("\n", xml)
        for para in PARA_SPLIT.split(xml):
            text = "".join(TEXT_RUN.findall(para))
            for line in text.split("\n"):
                line = re.sub(r"[\u3000\xa0]+", " ", line).strip()
                if line:
                    out.append(line)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    if not os.path.exists(src):
        print("NOT_FOUND:", src)
        return 2

    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".txt"
    lines = extract(src)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("段落数 %d → %s" % (len(lines), dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
