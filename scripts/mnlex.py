"""Shared helpers: load the official dictionary data and basic Mongolian
Cyrillic phonology (vowel harmony, stems). Used by check_text.py and lookup.py."""
import csv
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

LOWER = "абвгдеёжзийклмноөпрстуүфхцчшщъыьэюя"
UPPER = LOWER.upper()
LETTERS = LOWER + UPPER
WORD_RE = re.compile(r"[" + LETTERS + r"]+(?:-[" + LETTERS + r"]+)*")

BACK = set("аоуяёы")          # эр эгшиг (ю is ambiguous)
FRONT = set("эөүе")           # эм эгшиг
NEUTRAL = set("ий")           # саармаг
VOWELS = set("аэиоуөүяеёюыий")
CONS = set("бвгджзклмнпрстфхцчшщ")
FOREIGN_LETTERS = set("кфщ")
LONG_ENDINGS = ("аа", "ээ", "оо", "уу", "өө", "үү", "иа", "ио", "иу", "яа", "еэ",
                "ёо", "юу", "юү", "яу", "ёу", "еү", "ий", "ы", "иэ", "иө")
DIPHTHONGS = ("ай", "эй", "ой", "уй", "үй", "яй", "ёй", "юй", "ей")


def norm(s):
    s = unicodedata.normalize("NFC", s)
    # Latin look-alikes that sneak into Cyrillic text
    return s.translate(str.maketrans({"і": "и", "ү": "ү", "ө": "ө"}))


def harmony(word):
    """'back' (эр үг), 'front' (эм үг), 'neutral' (only и/й), 'mixed'."""
    w = word.lower()
    b = any(c in BACK for c in w)
    f = any(c in FRONT for c in w)
    if b and f:
        return "mixed"
    if b:
        return "back"
    if f:
        return "front"
    return "neutral"


def last_harmony(word):
    """Harmony decided by the last (compound-final) part of the word."""
    w = word.lower().split("-")[-1]
    for c in reversed(w):
        if c in BACK:
            return "back"
        if c in FRONT:
            return "front"
    return "front" if any(c in "иий" for c in w) else "neutral"


def first_round_vowel(word):
    """Return the vowel that governs labial harmony: 'а','э','о','ө'."""
    w = word.lower().split("-")[-1]
    for c in w:
        if c in "ауяы":
            return "а"
        if c in "оё":
            return "о"
        if c == "ө":
            return "ө"
        if c in "эүе":
            return "э"
    return "э"


def ends_long_or_diphthong(word):
    w = word.lower()
    return w.endswith(LONG_ENDINGS) or w.endswith(DIPHTHONGS)


PARTICLES = set("""маань минь чинь нь тань билээ юм шүү биз бэ вэ уу үү юу юү даа дээ доо дөө
л ч за аа ээ оо өө байна байсан байх бол болон буюу эсвэл гэж гэх гэсэн гэвч харин бас мөн
ямар яаж хаана хэзээ хэн юу хэд хэдэн тэр энэ тэд бид та би чи түүн үүн манай танай""".split())

_cache = {}


def load():
    if _cache:
        return _cache
    heads, entries = set(), {}
    with open(os.path.join(DATA, "dictionary.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            h = r["headword"].rstrip("-").lower()
            heads.add(h)
            entries.setdefault(h, []).append(r)
    foreign, forms = {}, set()
    with open(os.path.join(DATA, "foreign_words.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            h = r["headword"].lower()
            foreign[h] = r
            forms.add(h)
            for x in r["forms"].split(","):
                x = x.strip().lower()
                if x:
                    forms.add(x)
    infl = {}
    with open(os.path.join(DATA, "inflection_patterns.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            infl.setdefault(r["code"], r["forms"])
    errors = []
    with open(os.path.join(DATA, "common_errors.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            errors.append(r)
    # stem index: headword plus common alternations so inflected forms match
    stems = set()
    smap = {}

    for h in heads | set(foreign):
        if " " in h:
            continue
        added = [h]
        if len(h) >= 4:
            if h[-1] in "аэоөу" and h[-2] in CONS:          # хана -> хан(ыг)
                added.append(h[:-1])
            if h.endswith("ь"):                              # морь -> мори(н)
                added.append(h[:-1] + "и")
                added.append(h[:-1])
            m = re.match(r"^(.*[" + "".join(CONS) + r"])([аэоөуүи])([" + "".join(CONS) + r"])$", h)
            if m and len(h) >= 4:                            # ажил -> ажл(ын)
                added.append(m.group(1) + m.group(3))
            if h.endswith("н") and len(h) >= 5:              # шатахуун -> шатахуу
                added.append(h[:-1])
        for x in added:
            stems.add(x)
            smap.setdefault(x, h)
        smap.setdefault(h, h)
    _cache.update(heads=heads, entries=entries, foreign=foreign, forms=forms,
                  infl=infl, errors=errors, stems=stems, smap=smap)
    return _cache


def known(word, min_ratio=0.4):
    """True if the word or a plausible stem of it is in the official lists."""
    d = load()
    w = word.lower()
    if w in d["heads"] or w in d["forms"] or w in PARTICLES:
        return True
    parts = w.split("-")
    if len(parts) > 1:
        return all(known(p, min_ratio) for p in parts if len(p) > 2)
    need = 2
    for i in range(len(w), need - 1, -1):
        st = w[:i]
        if st in d["stems"] and suffix_ok(st, w[i:]):
            return True
    return False


def suffix_ok(stem, suf):
    """Suffix vowels must follow the stem's vowel harmony (§7–8).
    уу/үү, и, й are exceptions (§8 гажилт)."""
    if not suf:
        return True
    hs = harmony(stem)
    core = re.sub(r"(уу|үү|юу|юү|яу|ёу|еү|иу|ий|и|й|ы)", "", suf)
    hb = any(c in "аоуяё" for c in core)
    hf = any(c in "эөүе" for c in core)
    if hs == "back" and hf and not re.search(r"гүй|жээ|чээ", suf):
        return False
    if hs == "front" and hb:
        return False
    return True


def longest_stem(word, alternations=False):
    """Longest headword the word begins with. With alternations=True also
    matches elided / softened stems (хүүхд- → хүүхэд, мори- → морь) and
    checks suffix harmony; returns the headword."""
    d = load()
    w = word.lower()
    for i in range(len(w), 1, -1):
        p = w[:i]
        if p in d["heads"] or p in d["foreign"]:
            if not alternations or suffix_ok(p, w[i:]):
                return p
        if alternations and p in d["smap"] and suffix_ok(p, w[i:]):
            return d["smap"][p]
    return ""


def is_foreign(word):
    d = load()
    w = word.lower()
    if w in d["forms"] or any(c in FOREIGN_LETTERS for c in w):
        return True
    st = longest_stem(w)
    return bool(st) and st in d["foreign"] and len(st) >= 4


_ELIDE = {}


def elision_rule(code):
    """From the official inflection example for a code, decide whether the stem's
    last short vowel drops before long-vowel suffixes (§27): returns 'elide',
    'keep' or None (unknown)."""
    if code in _ELIDE:
        return _ELIDE[code]
    forms = [x.strip() for x in load()["infl"].get(code, "").replace(";", ",").split(",") if x.strip()]
    res = None
    if forms:
        b = forms[0].split()[0]
        acc = next((f for f in forms[1:] if re.search(r"(ыг|ийг)$", f) and " " not in f), None)
        if acc:
            st = re.sub(r"(ыг|ийг)$", "", acc)
            if st == b or st == b[:-1] and b.endswith("ь"):
                res = "keep"
            elif len(b) >= 4 and st == b[:-2] + b[-1]:
                res = "elide"
    _ELIDE[code] = res
    return res


def elided(h):
    return h[:-2] + h[-1]


_NSTEM = {}


def n_stem_rule(code):
    """'n' if the official example inserts the unstable н (модны, модонд, модноос),
    'plain' if it does not (номын, номд), None if unknown."""
    if code in _NSTEM:
        return _NSTEM[code]
    forms = [x.strip() for x in load()["infl"].get(code, "").replace(";", ",").split(",") if x.strip()]
    res = None
    if len(forms) > 2:
        b = forms[0].split()[0]
        gen = next((f for f in forms[1:4] if re.search(r"(ын|ийн|ны|ний|н|ы|ий)$", f) and not re.search(r"(ууд|үүд|нууд|нүүд|нар)$", f)), None)
        if gen:
            if re.search(r"(ны|ний)$", gen) and not re.search(r"(ны|ний)$", b + "ы"):
                res = "n"
            elif re.search(r"(ын|ийн)$", gen):
                res = "plain"
    _NSTEM[code] = res
    return res
