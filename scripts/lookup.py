#!/usr/bin/env python3
"""Look up words in «Монгол хэлний зөв бичих дүрмийн журамласан толь».

  python3 lookup.py ҮГ [ҮГ ...]        exact headword, stem guess, similar words
  python3 lookup.py --code I.17.1      show the official inflection example
  python3 lookup.py --grep РЕГЕКС      search headwords by regex (e.g. '^бөмбө')

For each word prints: headword entries (код, хэрэглээ, хэл зүйн ангилал,
тайлбар), foreign-word forms, known common errors, the longest headword
that the word starts with (likely stem) with its inflection example, and
close spellings (possible typo corrections)."""
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mnlex as M  # noqa: E402


def show_entries(h, d):
    for e in d["entries"].get(h, []):
        print(f"  • {e['headword']}  {e['code'] or '—'}  [{e['pos']}] {e['tags']} ({e['usage']}): {e['definition']}")


def lookup(word):
    d = M.load()
    w = M.norm(word).lower().rstrip("-")
    print(f"=== {word}")
    found = False
    if w in d["entries"]:
        found = True
        print("Толгой үг:")
        show_entries(w, d)
    if w in d["foreign"]:
        found = True
        r = d["foreign"][w]
        print(f"Гадаад үг: {r['headword']} {r['code']}: {r['forms']}")
    elif w in d["forms"]:
        found = True
        for h, r in d["foreign"].items():
            if w in [x.strip().lower() for x in r["forms"].split(",")]:
                print(f"Гадаад үгийн хувилсан хэлбэр: {r['headword']} {r['code']}: {r['forms']}")
                break
    for r in d["errors"]:
        b = r["буруу"].lower()
        if w == b or (r["тааруулах"] == "угтвар" and w.startswith(b)):
            print(f"!! Түгээмэл алдаа: «{r['буруу']}» → «{r['зөв']}» ({r['төрөл']}) — {r['тайлбар']} [{r['эх сурвалж']}]")
            found = True
        elif w in [c.strip().lower() for c in r["зөв"].split("|")]:
            print(f"(Зөв хэлбэр. Буруу бичдэг нь: «{r['буруу']}» — {r['тайлбар']})")
    if not found:
        st = M.longest_stem(w, alternations=True)
        if st:
            print(f"Тольд яг ийм толгой үг алга. Хамгийн урт таарсан үндэс: «{st}»" +
                  (" (гадаад үг)" if st in d["foreign"] else ""))
            show_entries(st, d)
            codes = sorted({e["code"] for e in d["entries"].get(st, []) if e["code"]})
            for c in codes:
                print(f"  Хувилал {c}: {d['infl'].get(c, '')[:400]}")
            if st in d["foreign"]:
                print(f"  Хэлбэрүүд: {d['foreign'][st]['forms']}")
        print("  Үндэс+залгавар байдлаар таниж байна уу:", "тийм" if M.known(w) else "ҮГҮЙ — үсгийн алдаа байж болзошгүй")
    pool = list(d["heads"]) + list(d["foreign"])
    near = difflib.get_close_matches(w, pool, n=8, cutoff=0.78)
    near = [x for x in near if x != w]
    if near:
        print("Ойролцоо бичлэгтэй толгой үгс:", ", ".join(near))
    print()


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    d = M.load()
    if a[0] == "--code":
        for c in a[1:]:
            print(c, d["infl"].get(c, "(олдсонгүй)"))
        return
    if a[0] == "--grep":
        rx = re.compile(a[1])
        hits = sorted(h for h in set(d["heads"]) | set(d["foreign"]) if rx.search(h))
        print(f"{len(hits)} үг:", ", ".join(hits[:300]))
        return
    for w in a:
        lookup(w)


if __name__ == "__main__":
    main()
