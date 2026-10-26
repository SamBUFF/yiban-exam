# -*- coding: utf-8 -*-
"""PDF → 「每段一行」纯文本，供 grep_evidence.py 检索。

用法:
    python pdf_to_text.py 依据.txt a.pdf b.pdf c.pdf ...

输出格式与 docx_to_text.py 完全一致（行号 = 段号，可直接写进答案表的「依据」列），
多个 PDF 之间插入 `### FILE: <文件名>` 分隔行 —— 这样 grep 命中的上下文里
能一眼看出条款出自哪份文件。**分隔行本身也占一行号**，引用行号时不要跳开。

依赖 pypdf：pip install pypdf
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def extract(path, lines):
    lines.append("### FILE: %s" % os.path.basename(path))
    try:
        from pypdf import PdfReader
    except ImportError:
        lines.append("### ERROR: 未安装 pypdf，请用托管 Python 运行")
        lines.append("")
        return 0
    n = 0
    try:
        reader = PdfReader(path)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                pass
        for page in reader.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
                    n += 1
    except Exception as e:  # noqa: BLE001
        lines.append("### ERROR: %s" % e)
    lines.append("")
    return n


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out, pdfs = sys.argv[1], sys.argv[2:]
    lines, total = [], 0
    for p in pdfs:
        if not os.path.exists(p):
            lines.append("### FILE: %s" % os.path.basename(p))
            lines.append("### ERROR: 文件不存在")
            lines.append("")
            continue
        total += extract(p, lines)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("WROTE %s  lines=%d  text_lines=%d  files=%d"
          % (out, len(lines), total, len(pdfs)))
    if total == 0:
        print("!! 一个字的正文都没提取到 —— 很可能是扫描件/图片页，需要 OCR 或改用别的来源")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
