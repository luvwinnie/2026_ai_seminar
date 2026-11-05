"""④ 読み取りの確かめ：VL モデルが帳票の画像から読んだ値(tmp/series6/s4/ocr/results.json の12回分)を、
判断モデルが画像と照らして「合っているか」を当てられるかを、モデルごとに測る。
Box(Jev 1.14 だけ)は、きれいな画像2枚で、欄の位置が PDF の文字の位置に当たるかを確かめる。
使い方：python eval_ocr.py [モデル…]   → ocr_verify.json
"""
import json
import os
import sys
import time
from pathlib import Path

from common import IMAGE_MODELS, load_env, save, zdr_for

load_env()
from services import decision_client as dc  # noqa: E402
from services import decisions  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]  # 例アプリの1つ上の作業フォルダ
OCR = ROOT / "tmp/series6/s4/ocr"
runs = json.loads((OCR / "results.json").read_text())


def img_of(name):
    p = OCR / ("forms" if name.endswith(".png") else "scan") / name
    return p.read_bytes(), ("image/png" if name.endswith(".png") else "image/jpeg")


def auroc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def checks_for(model):
    rows, cost = [], 0.0
    for r in runs:
        ext = json.loads(r["raw"]) if r.get("raw") else {}
        ext = {k: v for k, v in ext.items() if v not in (None, "")}
        b, mime = img_of(r["image"])
        state = ["製造業の不適合報告書(または不良報告書)の画像:", decisions.image_part(b, mime)]
        qs = {f"m_{f}": dc.noul(
            f"画像の帳票の「{decisions.FIELD_LABELS[f]}」の欄に書かれている値は「{v}」である。"
            "日付の書き方・桁区切りのカンマ・「個」「円」・■や□の印の違いは同じとみなす。読めない・欄が空なら当てはまらない。",
            "書かれている値と同じ", "違う値が書かれている、または欄が空・読めない")
            for f, v in ext.items() if f in decisions.FIELD_LABELS}
        try:
            res = dc.decide(state, qs, model=model, zdr=zdr_for(model), use_cache=False)
        except dc.DecisionError as e:
            rows.append({"run": f"{r['model']}|{r['image']}", "error": str(e)[:200]})
            continue
        cost += res.cost_usd
        for q, a in res.answers.items():
            f = q[2:]
            rows.append({"run": f"{r['model']}|{r['image']}", "field": f, "value": ext[f], "correct": f not in r["wrong"],
                         "p": float(a.value)})
    return rows, cost


def text_box(pdf_path, value):
    """PDF の上で value の文字が書かれている位置(画像の割合)。見つからなければ None。"""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    w, h = page.get_size()
    tp = page.get_textpage()
    m = tp.search(value).get_next()
    if not m:
        return None
    i, n = m
    bs = [tp.get_charbox(k) for k in range(i, i + n)]
    return {"left": min(b[0] for b in bs) / w, "right": max(b[2] for b in bs) / w,
            "top": 1 - max(b[3] for b in bs) / h, "bottom": 1 - min(b[1] for b in bs) / h}


def iou(a, b):
    ix = max(0, min(a["right"], b["right"]) - max(a["left"], b["left"]))
    iy = max(0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))
    inter = ix * iy
    ua = (a["right"] - a["left"]) * (a["bottom"] - a["top"]) + (b["right"] - b["left"]) * (b["bottom"] - b["top"]) - inter
    return inter / ua if ua > 0 else 0


def eval_boxes():
    import csv
    truth = {r["defect_id"]: r for r in csv.DictReader(open(
        ROOT / "example_app/data/defect_reports.csv", encoding="utf-8"))}
    out = []
    for did in ("KZ25-0050", "KZ25-0005"):
        t = truth[did]
        fields = {f: t[f] for f in ("defect_id", "process", "machine_name", "customer", "operator_name", "discoverer",
                                    "part_number", "part_name", "factor") if t.get(f)}
        b, mime = img_of(f"{did}.png")
        state = ["製造業の不適合報告書(または不良報告書)の画像:", decisions.image_part(b, mime)]
        qs = {f"b_{f}": {"type": "box", "instructions": f"帳票の画像の中で「{decisions.FIELD_LABELS[f]}」の欄に書かれている値"} for f in fields}
        res = dc.decide(state, qs, model="typesafe/jev-1.14", use_cache=False)
        for f, v in fields.items():
            gt = text_box(OCR / "forms" / f"{did}.pdf", v)
            pb = res.answers[f"b_{f}"].value
            if gt is None:
                out.append({"form": did, "field": f, "value": v, "gt": None, "pred": pb})
                continue
            cx, cy = (gt["left"] + gt["right"]) / 2, (gt["top"] + gt["bottom"]) / 2
            hit = pb["left"] <= cx <= pb["right"] and pb["top"] <= cy <= pb["bottom"]
            out.append({"form": did, "field": f, "value": v, "gt": gt, "pred": pb, "center_hit": hit, "iou": round(iou(gt, pb), 3),
                        "confidence": res.answers[f"b_{f}"].confidence})
    return out, res.cost_usd


models = sys.argv[1:] or IMAGE_MODELS
out = {"runs": len(runs), "results": {}}
for m in models:
    t0 = time.monotonic()
    rows, cost = checks_for(m)
    ok = [r for r in rows if "p" in r]
    wrong = [r for r in ok if not r["correct"]]
    right = [r for r in ok if r["correct"]]
    summ = {"fields": len(ok), "wrong_fields": len(wrong),
            "auroc_detect_wrong": round(auroc([-r["p"] for r in ok], [not r["correct"] for r in ok]) or 0, 3),
            "caught@0.5": f"{sum(r['p'] < 0.5 for r in wrong)}/{len(wrong)}",
            "false_alarm@0.5": f"{sum(r['p'] < 0.5 for r in right)}/{len(right)}",
            "errors": sum(1 for r in rows if "error" in r), "cost_usd": round(cost, 5), "sec": round(time.monotonic() - t0, 1)}
    out["results"][m] = {"summary": summ, "rows": rows}
    print(m, summ)
    save("ocr_verify.json", out)
if os.environ.get("SKIP_BOXES") or os.environ.get("OUT_PREFIX"):   # 無料のモデルだけで測るときは、Box(有料の Jev 1.14)を呼ばない
    sys.exit(0)
bx, bcost = eval_boxes()
hits = [r for r in bx if r.get("gt")]
out["boxes"] = {"rows": bx, "center_hit": f"{sum(r['center_hit'] for r in hits)}/{len(hits)}",
                "mean_iou": round(sum(r["iou"] for r in hits) / len(hits), 3) if hits else None, "cost_usd": bcost}
print("boxes", out["boxes"]["center_hit"], out["boxes"]["mean_iou"])
save("ocr_verify.json", out)
