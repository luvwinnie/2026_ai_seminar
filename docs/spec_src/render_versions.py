"""仕様書の正本(spec_src/*.md)から、回ごとの版(v1.0〜v5.0)を書き出す。

使い方:
  python render_versions.py --check                 # 印の書き方だけ確かめる(何も書き出さない)
  python render_versions.py --out <フォルダ>         # <フォルダ>/v1.0_第2回/ … v5.0_第6回/ に書き出す
  python render_versions.py --latest <フォルダ>     # v5.0 だけを <フォルダ> に書き出す(例アプリの docs/ 用)

正本の書き方(VERSIONS.md にも同じ説明):
  - 印の無い行は、そのファイルが出てくる版からずっと入る
  - ファイルの1行目に <!-- file: v2.0 --> と書くと、そのファイルは v2.0 から出てくる(無ければ v1.0 から)
  - 1行だけ:行の終わりに <!-- v3.0 --> (v3.0 から)や <!-- v1.0..v2.1 --> (v1.0〜v2.1 だけ)
  - まとまり:印だけの行 <!-- v1.1 --> または <!-- v1.0..v2.1 --> で始め、<!-- /v --> で閉じる。入れ子にできる
  - 書き出すときに印はすべて消える
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = ["1.0", "1.1", "2.0", "2.1", "3.0", "3.1", "4.0", "4.1", "5.0"]
SESSION = {"1.0": 2, "1.1": 2, "2.0": 3, "2.1": 3, "3.0": 4, "3.1": 4, "4.0": 5, "4.1": 5, "5.0": 6}
MOMENT = {"1.0": "第2回の前半(作る前)", "1.1": "第2回の終わり(確かめて直した版)",
          "2.0": "第3回の前半", "2.1": "第3回の終わり", "3.0": "第4回の前半", "3.1": "第4回の終わり",
          "4.0": "第5回の前半", "4.1": "第5回の終わり", "5.0": "第6回(完成形＝例アプリ)"}
RANK = {v: i for i, v in enumerate(VERSIONS)}

TAG = r"v(\d\.\d)(?:\.\.v(\d\.\d))?"
RE_FILE = re.compile(r"^<!--\s*file:\s*v(\d\.\d)\s*-->\s*$")
RE_OPEN = re.compile(r"^\s*<!--\s*" + TAG + r"\s*-->\s*$")
RE_CLOSE = re.compile(r"^\s*<!--\s*/v\s*-->\s*$")
RE_INLINE = re.compile(r"\s*<!--\s*" + TAG + r"\s*-->\s*$")


class SpecError(Exception):
    pass


def _range(a: str, b: str | None, where: str) -> tuple[int, int]:
    for v in (a, b):
        if v is not None and v not in RANK:
            raise SpecError(f"{where}: 知らない版 v{v}(使える版: {', '.join(VERSIONS)})")
    lo, hi = RANK[a], RANK[b] if b else len(VERSIONS) - 1
    if lo > hi:
        raise SpecError(f"{where}: 範囲の向きが逆 v{a}..v{b}")
    return lo, hi


def parse(path: Path) -> tuple[int, list[tuple[str, tuple[int, int]]]]:
    """(ファイルが出る版の番号, [(行, (出る版, 消える版))])"""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 0
    if lines and RE_FILE.match(lines[0]):
        v = RE_FILE.match(lines[0]).group(1)
        start = _range(v, None, f"{path.name}:1")[0]
        lines = lines[1:]
        offset = 2
    else:
        offset = 1
    stack: list[tuple[int, int, int]] = []   # (lo, hi, 開いた行)
    out = []
    for i, line in enumerate(lines):
        where = f"{path.name}:{i + offset}"
        if RE_CLOSE.match(line):
            if not stack:
                raise SpecError(f"{where}: 閉じる印 <!-- /v --> に対応する開く印が無い")
            stack.pop()
            continue
        m = RE_OPEN.match(line)
        if m:
            lo, hi = _range(m.group(1), m.group(2), where)
            stack.append((lo, hi, i + offset))
            continue
        lo, hi = start, len(VERSIONS) - 1
        for slo, shi, _ in stack:
            lo, hi = max(lo, slo), min(hi, shi)
        m = RE_INLINE.search(line)
        if m:
            ilo, ihi = _range(m.group(1), m.group(2), where)
            lo, hi = max(lo, ilo), min(hi, ihi)
            line = RE_INLINE.sub("", line)
        if "<!-- v" in line or "<!--v" in line:
            raise SpecError(f"{where}: 印の書き方が違う(行の終わりか、印だけの行に書く): {line.strip()[:60]}")
        out.append((line, (lo, hi)))
    if stack:
        raise SpecError(f"{path.name}:{stack[-1][2]}: 開いた印が閉じられていない")
    return start, out


def render(path: Path, version: str) -> str | None:
    start, rows = parse(path)
    k = RANK[version]
    if k < start:
        return None
    text = [line for line, (lo, hi) in rows if lo <= k <= hi]
    s = "\n".join(text)
    s = re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"
    # 題の下に版を入れる
    head = f"> 仕様書 v{version}（{MOMENT[version]}）。前の版から変わったところは `変更点.md`。\n"
    if s.startswith("# "):
        first, _, rest = s.partition("\n")
        s = first + "\n\n" + head + rest
    else:
        s = head + "\n" + s
    return s


def sources() -> list[Path]:
    return sorted(p for p in HERE.glob("[0-9][0-9]_*.md"))


def check() -> int:
    ok = True
    for p in sources():
        try:
            start, rows = parse(p)
            counts = [sum(1 for _, (lo, hi) in rows if lo <= k <= hi) for k in range(len(VERSIONS))]
            shown = " ".join(f"v{v}:{c if k >= start else '-'}" for k, (v, c) in enumerate(zip(VERSIONS, counts)))
            print(f"OK  {p.name}  {shown}")
        except SpecError as exc:
            ok = False
            print(f"NG  {exc}")
    return 0 if ok else 1


def write_all(out: Path) -> None:
    prev: dict[str, str] = {}
    for v in VERSIONS:
        d = out / f"v{v}_第{SESSION[v]}回"
        d.mkdir(parents=True, exist_ok=True)
        stats = []
        for p in sources():
            s = render(p, v)
            if s is None:
                continue
            (d / p.name).write_text(s, encoding="utf-8")
            old = prev.get(p.name)
            body_new = s.splitlines()[3:]
            body_old = old.splitlines()[3:] if old else []
            add = rem = 0
            for line in difflib.ndiff(body_old, body_new):
                if line.startswith("+ ") and line[2:].strip():
                    add += 1
                elif line.startswith("- ") and line[2:].strip():
                    rem += 1
            stats.append((p.name, "新しく出る" if old is None and v != VERSIONS[0] else "", add, rem))
            prev[p.name] = s
        (d / "_変更の行数.tsv").write_text(
            "ファイル\t区分\t足した行\t消した行\n" + "\n".join(f"{a}\t{b}\t{c}\t{e}" for a, b, c, e in stats) + "\n",
            encoding="utf-8")
        print(d.name, [(a, c, e) for a, _, c, e in stats])


def write_latest(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for p in sources():
        s = render(p, VERSIONS[-1])
        if s is not None:
            (out / p.name).write_text(s, encoding="utf-8")
            print(out / p.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--latest")
    a = ap.parse_args()
    if a.check or not (a.out or a.latest):
        sys.exit(check())
    if check() != 0:
        sys.exit(1)
    if a.out:
        write_all(Path(a.out))
    if a.latest:
        write_latest(Path(a.latest))
