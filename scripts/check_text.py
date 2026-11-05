#!/usr/bin/env python3
"""Mechanical spelling / punctuation check for Mongolian Cyrillic text, based on
«Монгол хэлний зөв бичих дүрмийн журамласан толь» (ХБҮЗ, 2018).

Usage:
  python3 check_text.py BOOK.(docx|md|txt|pdf) [--json out.json] [--md out.md]
                        [--no-unknown] [--max-unknown 300]

Finds only what a script can find reliably; the reviewer (Claude) must still
read the text against the rule reference in SKILL.md. Severity levels:
  алдаа    – rule clearly violated
  шалгах   – probably wrong, confirm in context
  мэдээлэл – typographic / unknown-word hints
"""
import argparse
import json
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mnlex as M  # noqa: E402

L = M.LETTERS
WORD = re.compile(r"[" + L + r"]+(?:-[" + L + r"]+)*")


# ----------------------------------------------------------------- reading
def read_paragraphs(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        try:
            import docx  # python-docx
            d = docx.Document(path)
            out = []
            for p in d.paragraphs:
                style = (p.style.name or "") if p.style is not None else ""
                out.append((p.text, "heading" if style.lower().startswith(("heading", "title", "гарчиг")) else ""))
            for t in d.tables:
                for row in t.rows:
                    for c in row.cells:
                        for p in c.paragraphs:
                            out.append((p.text, "table"))
            return out
        except ImportError:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8")
            paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
            return [("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)), "") for p in paras]
    if ext == ".pdf":
        t = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
        return [(l, "") for l in t.split("\n")]
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    return [(l, "heading" if re.match(r"^\s*#{1,6}\s", l) else "") for l in lines]


# ----------------------------------------------------------------- helpers
findings = []


_seen_keys = set()


def add(pi, start, text, found, suggest, rule, sev, msg):
    key = (pi, start, found.lower(), suggest.lower())
    if key in _seen_keys or (suggest and (pi, start, found.lower(), "*") in _seen_keys):
        return
    _seen_keys.add(key)
    if suggest:
        _seen_keys.add((pi, start, found.lower(), "*"))
    a = max(0, start - 35)
    ctx = text[a:start + len(found) + 35].replace("\n", " ")
    findings.append(dict(para=pi + 1, col=start + 1, found=found, suggest=suggest,
                         rule=rule, severity=sev, message=msg, context=ctx))


def tokens(text):
    return [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text)]


NUM_HARMONY = {"0": None, "1": "front", "2": "back", "3": "back", "4": "front", "5": "back",
               "6": "back", "7": "back", "8": "back", "9": "front"}
TENS = {"1": "back", "2": "back", "3": "back", "4": "front", "5": "back", "6": "back",
        "7": "back", "8": "back", "9": "front"}


def number_harmony(num):
    num = num.lstrip("0") or "0"
    if num.endswith("000"):
        return "back"           # мянга
    if num.endswith("00"):
        return "back"           # зуу
    if num.endswith("0"):
        return TENS.get(num[-2], "back")
    return NUM_HARMONY.get(num[-1])


def build_error_index():
    exact, prefix = {}, []
    for r in M.load()["errors"]:
        w = r["буруу"].lower()
        if r["тааруулах"] == "угтвар" and len(w) >= 6 and " " not in w:
            prefix.append((w, r))
        else:
            exact[w] = r
    prefix.sort(key=lambda x: -len(x[0]))
    return exact, prefix


ATTACHED_EXCEPT = set()

# verbs whose converb is irregular (§39, Багцалсан дүрэм)
CONVERB_FIX = {
    "авж": "авч", "авжээ": "авчээ", "өгж": "өгч", "өгжээ": "өгчээ",
    "гарж": "гарч", "гаржээ": "гарчээ", "хүрж": "хүрч", "хүржээ": "хүрчээ",
    "сурж": "сурч", "суржээ": "сурчээ",
    "хүсч": "хүсэж", "хүсчээ": "хүсжээ", "засч": "засаж", "засчээ": "засжээ",
    "нисч": "нисэж", "нисчээ": "нисжээ", "хасч": "хасаж", "хасчээ": "хасжээ",
    "хусч": "хусаж", "хусчээ": "хусжээ", "асч": "асаж", "асчээ": "асжээ",
    "дасч": "дасаж", "дасчээ": "дасжээ", "хийсч": "хийсэж",
    "авах": None,
}
CONVERB_FIX = {k: v for k, v in CONVERB_FIX.items() if v}

ABBREV_BEFORE_DOT = re.compile(r"(\b[" + M.UPPER + r"]|\bг\.м|\bө\.х|\bтө|\bмө|\bня\.бо|\bд-р|\bн-р|\bж\.нь|\bт\.\s*\d*|\bх|\bтал)\.$")


# ----------------------------------------------------------------- checks
def check(paras, unknown=True, max_unknown=300):
    d = M.load()
    exact, prefix = build_error_index()
    unknown_seen = {}
    harmony_seen = set()

    for pi, (text, kind) in enumerate(paras):
        text = M.norm(text)
        if not text.strip():
            continue
        toks = tokens(text)

        # --- typography / punctuation (§50–64, Багцалсан дүрэм 3)
        for m in re.finditer(r"(?<=\S)[ \t]+([,.;:!?])(?!\.)", text):
            add(pi, m.start(), text, m.group(0), m.group(1), "§50–56", "мэдээлэл",
                "Цэг тэмдгийн өмнө зай авахгүй")
        for m in re.finditer(r"[" + L + r"][,;](?=[" + L + r"])", text):
            add(pi, m.start(), text, m.group(0), m.group(0)[0] + m.group(0)[1] + " ", "§55", "мэдээлэл",
                "Таслал, цэгтэй таслалын дараа зай авна")
        for m in re.finditer(r"(?<!\.)\.\.(?!\.)", text):
            add(pi, m.start(), text, "..", ". эсвэл ...", "§53", "мэдээлэл", "Хоёр цэг – цуваа цэг (...) эсвэл цэг байх ёстой")
        for m in re.finditer(r"  +", text.strip()):
            pass  # double spaces are reported once per paragraph below
        if re.search(r"\S  +\S", text):
            m = re.search(r"\S  +\S", text)
            add(pi, m.start() + 1, text, "  ", " ", "Хэв зүй", "мэдээлэл", "Давхар зай")
        if '"' in text:
            i = text.index('"')
            add(pi, i, text, '"', "“ ”", "§57", "мэдээлэл", "Хашилтыг “ ” хэлбэрээр бичнэ (нэг номд нэг мөр)")
        if kind == "heading" and text.rstrip().endswith(".") and not text.rstrip().endswith("..."):
            add(pi, len(text.rstrip()) - 1, text, ".", "(цэггүй)", "§50 тэмдэглэх нь", "алдаа",
                "Номын нэр, бүлэг, гарчгийн эцэст цэг тавихгүй")
        for m in re.finditer(r"\b([IVXLCDM]{1,6})\s*-?\s*(р|дугаар|дүгээр|дахь|дэх)\b", text):
            add(pi, m.start(), text, m.group(0), m.group(1), "Багцалсан дүрэм 3.3", "алдаа",
                "Ром тоогоор дэс дугаар заахад -р, дугаар, дүгээр хэрэглэхгүй")
        for m in re.finditer(r"\b(\d+)(р|дугаар|дүгээр)\b", text):
            add(pi, m.start(), text, m.group(0), m.group(1) + "-р", "§59б", "шалгах",
                "Араб тооны дараа товчилсон -р-ийг зураасаар залгана (5-р сар)")
        for m in re.finditer(r"\b([" + M.UPPER + r"])\.\s+([" + M.UPPER + r"][" + M.LOWER + r"]{2,})", text):
            add(pi, m.start(), text, m.group(0), m.group(1) + "." + m.group(2), "§47.5, §50г", "шалгах",
                "Эцэг/эхийн нэрийн эхний үсгийн дараа зайгүй бичнэ (Д.Нацагдорж)")
        for m in re.finditer(r"\b([" + M.UPPER + r"]{2,})([" + M.LOWER + r"]{1,6})\b", text):
            add(pi, m.start(), text, m.group(0), m.group(1) + "-" + m.group(2), "§59в", "алдаа",
                "Товчилсон үгэнд нөхцөлийг богино зураасаар залгана (МУИС-ийн)")
        for m in re.finditer(r"([" + M.LOWER + r"]{2,}[.!?])([" + M.UPPER + r"])", text):
            add(pi, m.start(2), text, m.group(0)[-2:], m.group(0)[-2] + " " + m.group(2), "§50", "мэдээлэл",
                "Өгүүлбэрийн төгсгөлийн тэмдгийн дараа зай авна")
        # sentence start
        for m in re.finditer(r"([.!?])(\s+)([" + M.LOWER + r"])", text):
            before = text[:m.start() + 1]
            nxt = text[m.start(3):m.start(3) + 6]
            if before.endswith("...") or ABBREV_BEFORE_DOT.search(before) or re.match(r"(гэх|гэж|гэсэн|г\.м)", nxt):
                continue
            if re.match(r"[" + M.LOWER + r"][,)]|[" + M.LOWER + r"]\s*$", text[m.start(3):m.start(3) + 2]):
                continue
            add(pi, m.start(3), text, m.group(3), m.group(3).upper(), "§46.1", "шалгах",
                "Өгүүлбэрийн эхний үсгийг томоор бичнэ")
        fs = text.lstrip()
        prev_txt = next((paras[j][0].strip() for j in range(pi - 1, -1, -1) if paras[j][0].strip()), "")
        para_start = (not prev_txt) or prev_txt.endswith((".", "!", "?", "…", ":")) or paras[pi - 1][0].strip() == "" or paras[pi - 1][1] == "heading"
        if fs and fs[0] in M.LOWER and kind != "table" and para_start and not re.match(r"^[" + M.LOWER + r"]{1,3}([),.]|\s*$)", fs):
            add(pi, len(text) - len(fs), text, fs[0], fs[0].upper(), "§46.1", "шалгах",
                "Догол мөр/өгүүлбэрийн эхний үсгийг томоор бичнэ (жагсаалтын мөр бол алгас)")

        # --- word-level checks
        for i, (w, s, e) in enumerate(toks):
            lw = w.lower()
            prev = toks[i - 1] if i > 0 else None
            gap_prev = text[prev[2]:s] if prev else ""
            same_phrase_prev = prev is not None and re.fullmatch(r"[ \t]+", gap_prev or "x") is not None
            after = text[e:e + 3]
            cap = w[0] in M.UPPER

            # common errors (official × notes and curated list)
            r = exact.get(lw)
            hit = None
            if r:
                hit = (r, w)
            else:
                for pw, pr in prefix:
                    if lw.startswith(pw):
                        hit = (pr, w)
                        break
            if hit:
                r, _ = hit
                sev = "алдаа" if r["төрөл"] == "алдаа" else "шалгах"
                sug = r["зөв"]
                if r["тааруулах"] == "угтвар" and lw != r["буруу"].lower() and " | " not in sug:
                    sug = sug + lw[len(r["буруу"]):]
                add(pi, s, text, w, sug, r["эх сурвалж"], sev, r["тайлбар"])

            # two-word errors (гэр рүү, хун тайж, нэг бүр handled above as exact on joined?)
            if prev and same_phrase_prev:
                two = (prev[0] + " " + w).lower()
                r2 = exact.get(two)
                if r2:
                    add(pi, prev[1], text, prev[0] + " " + w, r2["зөв"], r2["эх сурвалж"],
                        "алдаа" if r2["төрөл"] == "алдаа" else "шалгах", r2["тайлбар"])

            # irregular converbs
            if lw in CONVERB_FIX:
                add(pi, s, text, w, CONVERB_FIX[lw], "§39; Багцалсан дүрэм 2.1", "алдаа",
                    "Нөхцөл үйлийн -ж/-ч, өнгөрсөн цагийн -жээ/-чээ")
            elif re.search(r"рж(ээ)?$", lw) and not lw.endswith("рьж") and len(lw) > 3 and not cap:
                stem = re.sub(r"ж(ээ)?$", "", lw)
                syl = len(re.findall(r"[аэиоуөүяеёюы]+", stem))
                if (syl >= 2 or re.search(r"(аа|ээ|оо|уу|өө|үү|ай|ой|эй|уй|үй)р$", stem)) and \
                        stem not in ("хүр", "гар", "сур") and lw not in d["forms"]:
                    add(pi, s, text, w, re.sub(r"рж(ээ)?$", lambda m: "рч" + (m.group(1) or ""), w),
                        "§39.3в", "шалгах",
                        "Урт/хос эгшигтэй эсвэл олон үетэй р-ээр төгссөн үйл үгэнд -ч, -чээ (бутарч, хөөрч, тойрч) — үйл үг мөн эсэхийг шалга")

            # particles бэ / вэ (§49.1, §48.8)
            if lw in ("бэ", "вэ") and prev and same_phrase_prev:
                pl = prev[0].lower()
                want = "бэ" if pl[-1] in "вмнбпф" else "вэ"
                if lw != want:
                    add(pi, s, text, w, want, "§49.1", "алдаа",
                        "в, м, н-ээр төгссөн үгэнд «бэ», бусад үгэнд «вэ»")
            if lw in ("вээ", "бээ"):
                pass  # handled by common_errors

            # question particles уу/үү/юу/юү (§49.2) – only when clearly a particle
            if lw in ("уу", "үү", "юу", "юү") and prev and same_phrase_prev and re.match(r"\s*\?", after):
                pl = prev[0].lower()
                h = M.last_harmony(pl)
                if M.ends_long_or_diphthong(pl):
                    want = "юу" if h == "back" else "юү"
                else:
                    want = "уу" if h == "back" else "үү"
                if lw != want and not (lw == "юу" and pl in ("юу",)):
                    add(pi, s, text, w, want, "§49.2", "алдаа",
                        "Урт, хос эгшгээр төгссөн үгэнд юу/юү, бусад үгэнд уу/үү; эгшиг зохицно")

            # directional руу/рүү/луу/лүү (§49.7)
            if lw in ("руу", "рүү", "луу", "лүү") and prev and same_phrase_prev:
                pl = prev[0].lower()
                h = M.last_harmony(pl)
                lat = pl.endswith("р") or pl.endswith("рь")
                want = ("луу" if h == "back" else "лүү") if lat else ("руу" if h == "back" else "рүү")
                if M.is_foreign(pl) and h == "back" and not re.search(r"[аоыяё]", pl):
                    want = want  # foreign у counts as ү – keep, but lower severity
                if lw != want:
                    add(pi, s, text, w, want, "§49.7", "алдаа",
                        "р, рь-ээр төгссөн үгэнд -луу/-лүү, бусад үгэнд -руу/-рүү; эгшиг зохицно")
            m_att = re.match(r"^(.+?)(руу|рүү|луу|лүү)$", lw)
            if m_att and lw not in d["heads"] and lw not in d["forms"] and len(m_att.group(1)) >= 2:
                stem = m_att.group(1)
                if stem in d["heads"] or stem in d["foreign"]:
                    add(pi, s, text, w, w[:len(stem)] + " " + w[len(stem):], "§49.7", "алдаа",
                        "Чиглэхийн -руу/-луу-г уг үгнээс нь тусад нь бичнэ")

            # даа/дээ/доо/дөө harmony (§49.5)
            if lw in ("даа", "дээ", "доо", "дөө") and prev and same_phrase_prev:
                v = M.first_round_vowel(prev[0])
                want = {"а": "даа", "э": "дээ", "о": "доо", "ө": "дөө"}[v]
                if lw != want:
                    add(pi, s, text, w, want, "§49.5", "алдаа", "даа, дээ, доо, дөө баймж эгшиг зохицно")

            # дахь / дэх (§42, Багцалсан дүрэм 2.1)
            if lw in ("дахь", "дэх"):
                h = None
                pm = re.search(r"(\d+)\s*$", text[:s])
                if pm:
                    h = number_harmony(pm.group(1))
                elif prev and same_phrase_prev:
                    h = M.last_harmony(prev[0])
                if h in ("back", "front"):
                    want = "дахь" if h == "back" else "дэх"
                    if lw != want:
                        add(pi, s, text, w, want, "Багцалсан дүрэм 2.1; §42", "алдаа",
                            "Дэс тоонд эр үгэнд «дахь», эм үгэнд «дэх» (гурав дахь, дөрөв дэх)")
            m_dah = re.match(r"^(.+)(дахь|дэх)$", lw)
            if m_dah and lw not in d["heads"] and m_dah.group(1) in (
                    "нэг", "хоёр", "гурав", "дөрөв", "тав", "зургаа", "долоо", "найм", "ес", "арав"):
                add(pi, s, text, w, w[:len(m_dah.group(1))] + " " + m_dah.group(2), "§42", "алдаа",
                    "«дахь, дэх»-ийг тооны нэрээс тусад нь бичнэ")

            if len(lw) < 2:
                continue
            sent_start = (i == 0 and text.lstrip().startswith(w)) or (re.search(r"[.!?…:“\"«—–-]\s*$", text[:s]) is not None and not re.search(r"\b[" + M.UPPER + r"]\.\s*$", text[:s]))
            cap = (cap and not sent_start) or (len(w) > 1 and w.isupper())
            foreign = M.is_foreign(lw)
            h = M.harmony(lw)

            # ы / ий (§9)
            if not foreign:
                if "ы" in lw and M.harmony(lw.replace("ы", "")) == "front":
                    add(pi, s, text, w, lw.replace("ы", "ий"), "§9", "алдаа",
                        "Эм үгэнд «ы» бичихгүй, «ий» бичнэ")
                if re.search(r"[жчшь]ы", lw):
                    sug = re.sub(r"([жчш])ы", r"\1ий", lw)
                    sug = re.sub(r"ьы", "ий", sug)
                    add(pi, s, text, w, sug, "§9.3", "алдаа",
                        "ж, ч, ш, ь-ээр төгссөн эр үгэнд -ий залгана (багшийн, туужийг)")
                if h == "back" and not cap:
                    m9 = re.search(r"([бвдзлмнпрстх])ий(н|г|нх\w*|гаа|гээ)?$", lw)
                    if m9 and lw not in d["heads"] and lw not in d["forms"]:
                        st = lw[:m9.start() + 1]
                        soft = (st + "ь") in d["heads"] or (st + "и") in d["heads"] or (st + "ь") in d["forms"]
                        if (st in d["stems"] or st in d["heads"]) and not soft:
                            add(pi, s, text, w, st + "ы" + (m9.group(2) or ""), "§9.1", "алдаа",
                                "Эр үгэнд урт «ы» бичнэ (ардын, хотыг)")

            # separating signs ъ / ь (§33)
            if "ъ" in lw and h in ("front",) and not foreign:
                add(pi, s, text, w, lw.replace("ъ", "ь"), "§33", "алдаа",
                    "Эм үгэнд тусгаарлах тэмдэг нь «ь» (өгье, үзье)")
            mq = re.search(r"ъ[яё](?=[" + M.LOWER + r"])", lw)
            if mq and not foreign:
                add(pi, s, text, w, lw.replace("ъ", "ь", 1), "Өмнөх үг 1.11", "шалгах",
                    "Үүсмэл биш үгийн язгуурт «ъ» бичихгүй, «ь» бичнэ (гавьяа, томьёо, харьяа)")
            if not cap and not foreign and len(lw) >= 3:
                if h == "back" and re.search(r"[бвгджзлмнпрстхцчш][яё]$", lw):
                    add(pi, s, text, w, lw[:-1] + "ъ" + lw[-1], "§33.1", "алдаа",
                        "Гийгүүлэгчээр төгссөн эр үгэнд -я, -ё-г «ъ»-ээр тусгаарлана (авъя, олъё)")
                if h == "front" and re.search(r"[бвгджзлмнпрстхцчш]е$", lw):
                    add(pi, s, text, w, lw[:-1] + "ье", "§33.2", "алдаа",
                        "Гийгүүлэгчээр төгссөн эм үгэнд -е-г «ь»-ээр тусгаарлана (өгье, үзье)")
                if re.search(r"[аэиоуөүяеёюы][ъь][яеё]$", lw):
                    add(pi, s, text, w, re.sub(r"[ъь]([яеё])$", r"\1", lw), "§33", "алдаа",
                        "Эгшиг ба зөөлний тэмдгийн дараа я, е, ё-д ъ/ь бичихгүй (саная, байя)")

            # vowel letters
            if re.search(r"(аaa|ааа|эээ|ооо|ууу|өөө|үүү)", lw):
                add(pi, s, text, w, "", "§4.3", "шалгах", "Үндсэн эгшгийг гурав давхарлаж бичихгүй")
            if "өй" in lw and not foreign:
                add(pi, s, text, w, "", "§5", "шалгах", "Монгол хэлэнд «өй» хос эгшиг хэрэглэхгүй")
            if lw.endswith("ия") and lw not in d["heads"] and lw not in d["forms"]:
                base = lw[:-2] if re.search(r"[сцз]ия$", lw) else lw[:-1]
                add(pi, s, text, w, (w[0] + base[1:]) if cap else base, "§48.4; Өмнөх үг 2.4", "алдаа",
                    "Оросоор дамжсан -ия төгсгөл: с, ц, з-ийн дараа «ия»-г, бусад үед «я»-г хасна (станц, компани, Итали)")

            # vowel harmony inside a native-looking word (§7–8)
            if h == "mixed" and not foreign and not cap and lw not in d["heads"] and lw not in d["forms"]:
                core = re.sub(r"(гүй\w*|жээ|чээ)$", "", lw)
                core = core.split("-")[-1]
                if M.harmony(core) == "mixed" and not M.known(core, 0.8) and lw not in harmony_seen:
                    harmony_seen.add(lw)
                    add(pi, s, text, w, "", "§7–8", "шалгах",
                        "Эр, эм эгшиг нэг үгэнд холилдсон — дагавар буруу залгагдсан эсвэл үсгийн алдаа байж магадгүй")
            # labial harmony: first vowel о/ө decides а→о/э→ө in suffixes
            if not foreign and not cap and lw not in d["heads"] and lw not in d["forms"]:
                fv = M.first_round_vowel(lw)
                if fv == "о" and re.search(r"(аар|аас|тай|гаа|даа|лаа|сан)$", lw):
                    st = longest_stem(lw)
                    if st and M.first_round_vowel(st) == "о" and not re.search(r"[уүюи]", lw[len(st):]):
                        add(pi, s, text, w, "", "§8.3", "шалгах",
                            "Эхний үед «о» бол хойшид «о» дагана (онгоцоор, оролцоход)")
                if fv == "ө" and re.search(r"(ээр|ээс|гээ|дээ|лээ|сэн)$", lw):
                    st = longest_stem(lw)
                    if st and M.first_round_vowel(st) == "ө" and not re.search(r"[уүюи]", lw[len(st):]):
                        add(pi, s, text, w, "", "§8.4", "шалгах",
                            "Эхний үед «ө» бол хойшид «ө» дагана (мөнгө, өргөдөл)")

            # dropped vowel (гээгдэх эгшиг §27–28), driven by the official inflection codes
            if not foreign and not cap and len(lw) >= 6:
                mm = None
                for cut in range(len(lw) - 2, 2, -1):
                    h0, suf = lw[:cut], lw[cut:]
                    if h0 in d["entries"] and re.match(r"^(ын|ийн|ыг|ийг|аас|ээс|оос|өөс|аар|ээр|оор|өөр|ууд|үүд)", suf):
                        codes = {e["code"] for e in d["entries"][h0] if e["code"].startswith("I.")}
                        rules = {M.elision_rule(c) for c in codes}
                        if codes and rules == {"elide"} and h0[-2] in "аэоөуүи" and h0[-1] in M.CONS:
                            mm = (h0, suf)
                        break
                if mm and lw not in d["forms"]:
                    h0, suf = mm
                    sug = M.elided(h0) + suf
                    add(pi, s, text, w, sug, "§27–28 (гээгдэх эгшиг)", "алдаа",
                        f"«{h0}» үгэнд урт эгшгээр эхэлсэн залгавар залгахад балархай эгшиг гээгдэнэ (тольд: {sorted(codes)[0]})")

            # unstable н (тогтворгүй н, §43.2; Өмнөх үг 1.15)
            if not foreign and not cap and len(lw) >= 5 and lw not in d["forms"]:
                for cut in range(len(lw) - 2, 2, -1):
                    h0, suf = lw[:cut], lw[cut:]
                    if h0 not in d["entries"]:
                        continue
                    codes = {e["code"] for e in d["entries"][h0] if e["code"].startswith("I.")}
                    rules = {M.n_stem_rule(c) for c in codes}
                    if not codes:
                        break
                    if any(e["pos"] in ("то.н", "ц.н", "о.н") for e in d["entries"][h0]) or \
                            any((h0 + v + "н") in d["heads"] for v in ["", "а", "э", "о", "ө", "и", "у", "ү"]):
                        break
                    if rules == {"plain"} and re.fullmatch(r"(ны|ний|[аоэө]?нд|[аоэө]?ндаа|[аоэө]?ндээ|наас|ноос|нээс|нөөс)", suf):
                        add(pi, s, text, w, "", "§43.2; Өмнөх үг 1.15", "шалгах",
                            f"«{h0}» үг тольд тогтворгүй н-гүй хувилна ({sorted(codes)[0]}: "
                            + M.load()["infl"].get(sorted(codes)[0], "")[:60] + "…)")
                    elif rules == {"n"} and re.fullmatch(r"(ын|ийн)", suf):
                        add(pi, s, text, w, "", "§43.2; Өмнөх үг 1.15", "шалгах",
                            f"«{h0}» үг тольд тогтворгүй н-тэй хувилна ({sorted(codes)[0]}: "
                            + M.load()["infl"].get(sorted(codes)[0], "")[:60] + "…). Утга ялгах эсэхийг шалга")
                    break

            # unknown words (possible typos)
            if unknown and not cap and w[1:] == w[1:].lower() and len(lw) >= 5 and not M.known(lw):
                unknown_seen.setdefault(lw, (pi, s, text, w))

    if unknown:
        for lw, (pi, s, text, w) in list(unknown_seen.items())[:max_unknown]:
            st = longest_stem(lw)
            add(pi, s, text, w, "", "Толь", "мэдээлэл",
                "Журамласан тольд үндэс нь олдсонгүй — үсгийн алдаа эсэхийг lookup.py-аар шалга"
                + (f" (хамгийн урт таарсан үндэс: «{st}»)" if st else ""))


def longest_stem(w):
    return M.longest_stem(w)


# ----------------------------------------------------------------- output
SEV_ORDER = {"алдаа": 0, "шалгах": 1, "мэдээлэл": 2}


def to_markdown(path, nparas):
    fs = sorted(findings, key=lambda f: (SEV_ORDER[f["severity"]], f["para"], f["col"]))
    cnt = {k: sum(1 for f in fs if f["severity"] == k) for k in SEV_ORDER}
    out = [f"# Автомат шалгалтын тайлан: {os.path.basename(path)}", "",
           f"Догол мөр/мөр: {nparas}. Алдаа: {cnt['алдаа']}, шалгах: {cnt['шалгах']}, мэдээлэл: {cnt['мэдээлэл']}.", "",
           "| № | Түвшин | Байршил | Олдсон | Санал | Дүрэм | Тайлбар | Орчин |",
           "|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(fs, 1):
        ctx = f["context"].replace("|", "\\|")
        out.append(f"| {i} | {f['severity']} | {f['para']}:{f['col']} | {f['found']} | {f['suggest']} | "
                   f"{f['rule']} | {f['message']} | …{ctx}… |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--no-unknown", action="store_true")
    ap.add_argument("--max-unknown", type=int, default=300)
    a = ap.parse_args()
    paras = read_paragraphs(a.path)
    check(paras, unknown=not a.no_unknown, max_unknown=a.max_unknown)
    md = to_markdown(a.path, len(paras))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(findings, f, ensure_ascii=False, indent=1)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(md)
    if not a.md and not a.json:
        sys.stdout.write(md)
    else:
        cnt = {k: sum(1 for f in findings if f["severity"] == k) for k in SEV_ORDER}
        print(f"done: {len(findings)} findings {cnt}")


if __name__ == "__main__":
    main()
