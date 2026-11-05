#!/usr/bin/env python3
"""Apply approved corrections to a copy of the manuscript.

  python3 apply_fixes.py INPUT.(docx|md|txt) FIXES.json OUTPUT

FIXES.json: list of {"para": 12, "col": 7, "found": "багшын", "suggest": "багшийн"}
(the same objects check_text.py --json writes). "para"/"col" are optional:
with both, only that occurrence is changed; with "para" only, every
occurrence in that paragraph; with neither, every whole-word occurrence.
Only whole words are replaced; case of the first letter is preserved.
For .docx the replacement is done run by run, so formatting is kept; a match
split across runs is replaced in the first run of the paragraph and reported.
Never overwrites INPUT."""
import json
import os
import re
import shutil
import sys

LET = "абвгдеёжзийклмноөпрстуүфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОӨПРСТУҮФХЦЧШЩЪЫЬЭЮЯ"


def pattern(found):
    return re.compile(r"(?<![" + LET + r"])" + re.escape(found) + r"(?![" + LET + r"])", re.I)


def keep_case(src, rep):
    if src[:1].isupper() and rep:
        return rep[0].upper() + rep[1:]
    return rep


def nth_of(text, f):
    """Which occurrence (0-based) the finding's column points to, or None = all."""
    if not f.get("col"):
        return None
    pos = int(f["col"]) - 1
    for k, m in enumerate(pattern(f["found"]).finditer(text)):
        if m.start() == pos:
            return k
    return None


def sub_nth(rx, text, rep, nth, counter):
    def r(m):
        k = counter[0]
        counter[0] += 1
        return keep_case(m.group(0), rep) if nth is None or k == nth else m.group(0)
    new = rx.sub(r, text)
    return new, int(new != text)


def fix_text(s, fixes_for_para):
    n = 0
    for f in sorted(fixes_for_para, key=lambda f: -int(f.get("col") or 0)):
        nth = nth_of(s, f)
        s, k = sub_nth(pattern(f["found"]), s, f["suggest"], nth, [0])
        n += k
    return s, n


def main():
    src, fx, out = sys.argv[1:4]
    if os.path.abspath(src) == os.path.abspath(out):
        sys.exit("OUTPUT must differ from INPUT")
    fixes = [f for f in json.load(open(fx, encoding="utf-8")) if f.get("suggest") and f.get("found")]
    by_para, glob = {}, []
    for f in fixes:
        (by_para.setdefault(int(f["para"]), []) if f.get("para") else glob).append(f)
    total, split = 0, []
    if src.lower().endswith(".docx"):
        import docx
        shutil.copy(src, out)
        d = docx.Document(out)
        paras = list(d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                for c in row.cells:
                    paras.extend(c.paragraphs)
        for i, p in enumerate(paras, 1):
            todo = by_para.get(i, []) + glob
            if not todo:
                continue
            for f in todo:
                rx = pattern(f["found"])
                nth = nth_of(p.text, f) if f in by_para.get(i, []) else None
                hit, counter = False, [0]
                for r in p.runs:
                    new, k = sub_nth(rx, r.text, f["suggest"], nth, counter)
                    if k:
                        r.text, hit = new, True
                        total += k
                if not hit and rx.search(p.text):
                    new, k = rx.subn(lambda m: keep_case(m.group(0), f["suggest"]), p.text)
                    for r in p.runs[1:]:
                        r.text = ""
                    if p.runs:
                        p.runs[0].text = new
                    total += k
                    split.append(i)
        d.save(out)
    else:
        lines = open(src, encoding="utf-8").read().split("\n")
        for i in range(len(lines)):
            todo = by_para.get(i + 1, []) + glob
            if todo:
                lines[i], k = fix_text(lines[i], todo)
                total += k
        open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"replaced {total} occurrence(s) -> {out}")
    if split:
        print("formatting inside these paragraphs was flattened (match crossed runs):", sorted(set(split)))


if __name__ == "__main__":
    main()
