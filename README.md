# Mongolian Grammar Checker

A Claude skill and a set of Python scripts that check Mongolian Cyrillic text (books, manuscripts, articles) against the official **«Монгол хэлний зөв бичих дүрмийн журамласан толь»** (ХБҮЗ, 2018). They produce an error report and, if you want, a corrected copy of the file.

You can use it in two ways:

1. **As a Claude skill.** Claude runs the scripts, reads the text by hand against the rule reference in [SKILL.md](SKILL.md), filters out false positives and writes the report.
2. **Manually.** Run the Python scripts yourself from the command line.

## Repository layout

| Path | Contents |
|---|---|
| [SKILL.md](SKILL.md) | Skill instructions for Claude, plus the full rule reference (§1–64) and the common-error list |
| [scripts/check_text.py](scripts/check_text.py) | Automatic checker: finds rule violations and likely errors |
| [scripts/lookup.py](scripts/lookup.py) | Dictionary lookup: headword, stem, inflection, similar spellings |
| [scripts/apply_fixes.py](scripts/apply_fixes.py) | Writes approved corrections into a **copy** of the file |
| [scripts/mnlex.py](scripts/mnlex.py) | Shared library used by the scripts above (data loading, vowel harmony); you don't run it directly |
| [data/dictionary.tsv](data/dictionary.tsv) | ≈34,500 dictionary headwords with inflection code, usage, part of speech and short definition |
| [data/foreign_words.tsv](data/foreign_words.tsv) | ≈870 foreign words with their official spelling and all case forms |
| [data/inflection_patterns.tsv](data/inflection_patterns.tsv) | Example inflections for each inflection code (I.x.x nouns, II.x.x verbs) |
| [data/common_errors.tsv](data/common_errors.tsv) | Common mistakes: wrong form → correct form, with explanation and source |
| [references/place_names.md](references/place_names.md) | Official names of aimags, soums, districts, countries and capitals |

## Requirements

- **Python 3.8+**. No packages are needed for `.md` and `.txt` files.
- **python-docx** for `.docx` files. `check_text.py` can read `.docx` without it, but loses heading detection and tables. `apply_fixes.py` needs it for `.docx`.
  ```bash
  pip install python-docx
  ```
- **pdftotext** (from Poppler) for `.pdf` input.
  ```bash
  brew install poppler          # macOS
  sudo apt install poppler-utils  # Debian/Ubuntu
  ```

## Using it as a Claude skill

### Install

The skill is the whole folder: `SKILL.md` together with `scripts/`, `data/` and `references/`. If only `SKILL.md` is installed, Claude still works from the rule reference, but without the dictionary and the automatic checker.

- **Claude Code:** copy or symlink the folder into your skills directory:
  ```bash
  # for all projects
  ln -s "$PWD" ~/.claude/skills/mongolian-grammar-checker
  # or for one project only
  mkdir -p .claude/skills && cp -R . .claude/skills/mongolian-grammar-checker
  ```
- **Claude.ai / Claude desktop app:** zip the folder (with `SKILL.md` at the top level of the folder) and upload it under **Settings → Capabilities → Skills**.

### Use

Attach or point to a file and ask in plain language, in Mongolian or English:

- «энэ номын алдааг шалгаад өг»
- «2-р бүлгийн зөв бичгийн алдааг засаад засвартай хувийг гаргаж өг»
- "Proofread this Mongolian chapter and give me a report"

Claude then:

1. copies your file and works on the copy (the original is never changed);
2. runs `check_text.py`, removes duplicate hits and counts them;
3. checks doubtful words in the dictionary with `lookup.py`;
4. reads the whole text by hand against the rule reference;
5. writes a report in Mongolian: location, what is written, correct form, rule (§ number or dictionary headword), short explanation;
6. if you ask for one, makes a corrected copy with `apply_fixes.py` and re-checks it.

Claude asks you first before applying uncertain fixes, changing dialect or speech in characters' dialogue, or suggesting style edits. Names, quotations and deliberately misspelled words are not counted as errors.

To teach the skill something permanent (for example "headings in this series end without a period"), tell Claude; it will offer to add a line to the «Сургамж» section of `SKILL.md`.

## Using the scripts manually

All examples assume you're in the repository root. `-I` (isolated mode) is recommended so Python doesn't pick up stray modules from the current directory.

### 1. Check a file: `check_text.py`

```bash
python3 -I scripts/check_text.py BOOK.docx --json findings.json --md findings.md
```

| Option | Meaning |
|---|---|
| `PATH` | Input file: `.docx`, `.md`, `.txt` or `.pdf` |
| `--json FILE` | Save findings as JSON (input for `apply_fixes.py`) |
| `--md FILE` | Save a Markdown report table |
| `--no-unknown` | Don't report words whose stem isn't in the dictionary |
| `--max-unknown N` | Cap on how many unknown words are reported (default 300) |

With neither `--json` nor `--md`, the Markdown report is printed to the terminal.

**Severity levels:**

- **алдаа** (error): a rule is clearly broken (бэ/вэ, уу/юу, руу/луу, ы/ий, ъ/ь, dropped vowels, дахь/дэх, entries from the common-error list…)
- **шалгах** (check): probably wrong; confirm in context (vowel harmony, unstable н, capitalization…)
- **мэдээлэл** (info): typography (spaces, quotation marks) and words not found in the dictionary (possible typos)

**Location** is `paragraph:column` for `.docx` and `line:column` for `.md`, `.txt` and `.pdf`. Both are 1-based.

Example output:

```
| № | Түвшин | Байршил | Олдсон  | Санал   | Дүрэм       | Тайлбар                            |
|---|--------|---------|---------|---------|-------------|------------------------------------|
| 1 | алдаа  | 3:4     | гэр рүү | гэр лүү | Дүрэм §49.7 | р, рь-ээр төгссөн үгэнд -луу/-лүү  |
| 2 | алдаа  | 3:8     | рүү     | лүү     | §49.7       | р, рь-ээр төгссөн үгэнд -луу/-лүү… |
```

Each JSON finding looks like:

```json
{"para": 3, "col": 4, "found": "гэр рүү", "suggest": "гэр лүү",
 "rule": "Дүрэм §49.7", "severity": "алдаа", "message": "…", "context": "…"}
```

**Things to keep in mind:**

- One mistake can be caught by two rules (rows 1 and 2 above). Remove overlaps before counting; [SKILL.md](SKILL.md) step 2 has a short script for that.
- `suggest` is sometimes empty, meaning "suspicious, but no fix known". Look the word up and decide yourself.
- The script only finds what can be found mechanically. Reading the text yourself is still necessary.

### 2. Look up a word: `lookup.py`

```bash
python3 -I scripts/lookup.py гэр хүүхдийн станц   # one or more words
python3 -I scripts/lookup.py --code I.17.1        # official inflection example for a code
python3 -I scripts/lookup.py --grep '^бөмбө'      # headwords matching a regex
```

For each word it prints:

- matching dictionary entries (inflection code, usage, part of speech, definition);
- the foreign-word forms, if it's a foreign word;
- a warning if it's a known common error, with the correct form;
- if the word isn't a headword: the longest matching stem and how that stem inflects;
- similar spellings (likely typo corrections).

The inflection code (e.g. `I.5.4`) tells you officially whether a vowel drops, whether there's an unstable н, and so on. Use `--code` to see the example forms when a case ending is in doubt.

### 3. Apply corrections: `apply_fixes.py`

```bash
python3 -I scripts/apply_fixes.py BOOK.docx approved.json BOOK_fixed.docx
```

`approved.json` is a list of corrections in the same shape that `check_text.py --json` writes. Usually you copy `findings.json`, delete the rows you don't agree with, fill in or edit `suggest` where needed, and add any errors you found by hand:

```json
[
  {"para": 3,  "col": 4, "found": "гэр рүү", "suggest": "гэр лүү"},
  {"para": 12,           "found": "багшын",  "suggest": "багшийн"},
  {                      "found": "МУИС-ын", "suggest": "МУИС-ийн"}
]
```

| Fields given | What gets replaced |
|---|---|
| `para` + `col` | only that one occurrence |
| `para` only | every occurrence in that paragraph/line |
| neither | every occurrence in the whole file |

- Only whole words are replaced, and an initial capital letter is kept.
- Rows with an empty `suggest` are skipped.
- The output path must differ from the input. The original is never overwritten.
- In `.docx`, replacement is done run by run so formatting is kept. If a match crosses formatting runs, the paragraph's formatting is flattened and its number is printed so you can check it.
- `.pdf` can't be written back. Convert it to `.docx` or `.txt` first.
- After applying, run `check_text.py` on the new file to see what's left.

### Full manual workflow

```bash
S=scripts
python3 -I $S/check_text.py book.docx --json findings.json --md findings.md
# read findings.md; look up doubtful words
python3 -I $S/lookup.py хаалга хаалганы
# copy findings.json -> approved.json, keep only the fixes you accept
python3 -I $S/apply_fixes.py book.docx approved.json book_fixed.docx
python3 -I $S/check_text.py book_fixed.docx --md remaining.md
```

## Data files

All data files are UTF-8, tab-separated, with a header row. You can open them in a spreadsheet or search them with `grep`:

```bash
grep $'^станц\t' data/dictionary.tsv
grep 'гэр' data/common_errors.tsv
```

To add a common mistake the checker should catch, add a row to `data/common_errors.tsv`:

| Column | Meaning |
|---|---|
| `буруу` | the wrong form |
| `зөв` | the correct form (alternatives separated by ` \| `) |
| `төрөл` | `алдаа` → reported as **алдаа**; anything else (e.g. `анхаар`) → reported as **шалгах** |
| `тааруулах` | `бүтэн`: whole word only; `угтвар`: prefix, so inflected forms match too (prefix matching applies only to single words of 6+ letters) |
| `тайлбар` | short explanation shown in the report |
| `эх сурвалж` | source: dictionary page/headword or rule § |

## Limitations

- This is an aid, not a final authority. Rule-based checks miss errors and raise false alarms, especially with names, dialogue and dialect, headings and numbered lists, and foreign terms outside the ≈870 listed words.
- It checks spelling and punctuation only, not style or content.
- Traditional Mongolian script (уйгаржин) is not supported.
- For rule changes after 2018, check [toli.gov.mn](https://www.toli.gov.mn).
