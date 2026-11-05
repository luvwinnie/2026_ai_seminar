# -*- coding: utf-8 -*-
"""
DefectReport AI — 模擬データ生成スクリプト(完全架空版・ゼロから新規作成)
========================================================================

株式会社霧沢精機・霧沢工場(架空。fictional_world.json の世界観)の不適合報告
100件を、**全文章・帳票レイアウトとも本スクリプト内で新規に author** して生成する。
実在の報告書に由来する語彙・文面・様式は一切使用していない。

- 客先・自社: fictional_world.json の架空企業(Web実在チェック済み)
- 機械: 実在の市販工作機械モデル(ユーザー指示。fictional_world.json の catalog)
- 部品: 霧沢精機の受託品ライン(ポンプP/バルブV/搬送C/航空補機A)として新規設定
- 出力: defect_reports.csv(110件) / forms_xlsx(全件) / forms_pdf(先頭10件)
- 乱数 seed=2026 固定(旧版 seed=42 とはデータ系列も完全に別物)
"""

import csv
import datetime as dt
import json
import os
import random

SEED = 8091417  # 前版(2026)から変更 — 全乱数系列を刷新し、統計量が過去と重ならないようにする
N_ROWS = 117   # 乱数の系列はこの件数で作る(変えると全件の中身が変わる)
N_KEEP = 110   # 2026-09-27: 日付順で先頭の110件だけ残す(KZ25-0001〜0110。2026-03-19 以降の7件を外した)
N_PDF = 10

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "defect_reports.csv")
XLSX_DIR = os.path.join(BASE_DIR, "forms_xlsx")
PDF_DIR = os.path.join(BASE_DIR, "forms_pdf")

DATE_START = dt.date(2025, 4, 1)
DATE_END = dt.date(2026, 3, 31)
TOTAL_DAYS = (DATE_END - DATE_START).days

random.seed(SEED)

# ---------------------------------------------------------------------------
# 0. 世界観(fictional_world.json から読み込み)
# ---------------------------------------------------------------------------
with open(os.path.join(BASE_DIR, "fictional_world.json"), encoding="utf-8") as f:
    WORLD = json.load(f)

COMPANY = WORLD["company"]["name"]          # 株式会社霧沢精機
PLANT = WORLD["company"].get("plant", "霧沢工場")
CUSTOMERS = list(WORLD["customers"].values())          # 架空10社
CUSTOMER_WEIGHTS = [21, 17, 14, 12, 9, 8, 7, 5, 4, 3]  # 上位集中(パレート)

# 機械カタログ(実在市販モデル)を用途で分類
_CAT = WORLD["machine_catalog"]
LATHES = [m["model"] for m in _CAT if "旋盤" in m.get("kind", "")]
MILLS = [m["model"] for m in _CAT if any(k in m.get("kind", "") for k in ("マシニング", "フライス"))]
ALL_MACHINES = [m["model"] for m in _CAT]

PROCESSES = ["旋削", "フライス加工", "マシニング", "研削", "溶接", "組付", "最終検査", "仕上げ"]
PROCESS_WEIGHTS = [18, 20, 21, 9, 6, 9, 9, 8]
PROCESS_MACHINE = {
    "旋削": LATHES,
    "フライス加工": [m for m in MILLS if "汎用" in m or "YZ" in m] or MILLS,
    "マシニング": [m for m in MILLS if "汎用" not in m],
    "研削": ["汎用フライス", "YZ-8WR"],
    "溶接": ["汎用フライス"],
    "組付": ["汎用フライス", "YZ-8WR"],
    "最終検査": ["汎用フライス", "YZ-8WR"],
    "仕上げ": ["汎用フライス", "YZ-8WR"] + LATHES[:1],
}

# 発見者・作業者(架空の従業員。姓のみ)
STAFF = [
    "霧嶋", "早乙女", "峰岸", "五十嵐", "神谷", "真壁", "楠見", "十文字", "刈谷", "汐見",
    "宇佐美", "白鳥", "円城寺", "戸叶", "美濃部", "郡司", "笹森", "波多野", "国枝", "鵜飼",
    "犬飼", "百瀬", "門脇", "荻原", "三雲", "熊代", "梶原", "小早川", "祢津", "風間",
]

# 受託品ライン(P=ポンプ, V=バルブ, C=搬送装置, A=航空補機)と部品カタログ — 新規設定
PARTS = [
    ("インペラハウジング", "P"), ("ケーシングカバー", "P"), ("ロータシャフト", "P"),
    ("メカニカルシール座", "P"), ("吸込ノズルフランジ", "P"),
    ("バルブボディ", "V"), ("ステムガイド", "V"), ("弁座リング", "V"),
    ("グランド押えナット", "V"), ("マニホールドブロック", "V"),
    ("ガイドレールブロック", "C"), ("ローラブラケット", "C"), ("チェーンテンショナ", "C"),
    ("駆動プーリ", "C"), ("カップリングハブ", "C"), ("ギヤケース", "C"),
    ("ベーンプレート", "A"), ("ノズルホルダ", "A"), ("スラストカラー", "A"), ("補機マウントリブ", "A"),
]

def part_number(line: str) -> str:
    return f"KRS-{line}{random.randint(10, 89)}-{random.randint(1000, 9899)}-{random.choice('ABCDE')}"

PHENOMENA = [
    "表面キズ", "寸法公差外れ", "バリ残り",
    "穴位置ずれ", "加工段差", "面粗さ不良",
    "NCプログラム誤り", "ひずみ変形", "工具破損",
    "刻印・表示誤り", "角部欠け", "取付方向誤り",
]
PHENOMENON_WEIGHTS = [21, 17, 13, 11, 9, 8, 6, 5, 4, 3, 2, 2]

FACTORS = [
    "初品確認漏れ", "加工条件の理解不足", "習熟不足", "標準手順の省略", "工具寿命超過",
    "設備不調", "NCデータ設定誤り", "素材欠陥", "図面の読み違い", "変更連絡の不達",
]
FACTOR_4M = {
    "初品確認漏れ": "Man", "加工条件の理解不足": "Man", "習熟不足": "Man", "標準手順の省略": "Method",
    "工具寿命超過": "Machine", "設備不調": "Machine", "NCデータ設定誤り": "Method",
    "素材欠陥": "Material", "図面の読み違い": "Man", "変更連絡の不達": "Method",
}

# ---------------------------------------------------------------------------
# 1. 文章素材(全て本スクリプトで新規に作文)
# ---------------------------------------------------------------------------
SPOTS = ["フランジ合わせ面", "ボス端面", "キー溝側面", "シール摺動面", "オイル溝底",
         "タップ下穴口元", "ポケット隅R", "外周リブ", "位置決めダボ穴", "皿モミ部",
         "Oリング溝", "軸受はめあい面"]
GAUGES = ["三次元測定機", "マイクロメータ", "栓ゲージ", "ハイトゲージ", "表面粗さ計", "投影機"]

def dim():
    base = random.choice([8, 12, 16, 22, 30, 45, 60, 85, 120])
    tol = random.choice([0.02, 0.03, 0.05, 0.1])
    over = round(tol + random.uniform(0.01, 0.15), 3)
    return base, tol, over

def make_description(ph: str, part: str) -> str:
    spot = random.choice(SPOTS)
    gauge = random.choice(GAUGES)
    b, t, o = dim()
    n_h = random.randint(2, 8)
    variants = {
        "寸法公差外れ": [
            f"{part}の{spot}を{gauge}で測定したところ、φ{b}部が公差±{t}に対し{o}mm大きく仕上がっていた。",
            f"出荷前検査で{part}の全長が図面値{b}mmに対して{o}mm不足していることが判明した。ロット内の他品も要確認。",
            f"{spot}の幅寸法が規格を{o}mm超過。仕上げ代の残し過ぎが疑われ、{gauge}での再測定でも同傾向だった。",
        ],
        "穴位置ずれ": [
            f"{part}の取付穴{n_h}箇所のうち1箇所が基準ダボから{o}mmずれており、相手部品と組み合わない。",
            f"{part}のピッチ{b}mmで並ぶタップ穴{n_h}箇所の位置度が{gauge}測定で公差外。穴群全体が同方向にオフセットしていた。",
            f"{spot}近傍の皿モミ位置が図面と左右反転しており、客先ラインで組付け不可と連絡があった。",
        ],
        "表面キズ": [
            f"{part}の{spot}に長さ約{random.randint(3, 25)}mmの線状キズ。搬送トレイ上で隣接品と接触した痕跡があった。",
            f"洗浄後の目視検査で{part}の{spot}に長さ{random.randint(2, 18)}mmの円弧状の擦り傷を確認。チャック爪の当たり面に切粉が噛み込んでいた。",
            f"梱包開封時に{part}の{spot}へ打痕状の凹み(深さ約{o}mm)が{random.randint(1, 3)}点。緩衝材の仕切り欠品が原因とみられる。",
        ],
        "バリ残り": [
            f"{part}の{spot}交差部に返りバリが残存し、Oリング装着時に切れを起こす恐れがある。",
            f"{part}の横穴とオイル溝の交差エッジに高さ約{o}mmの微細バリ。エア吹きでは除去しきれず、客先受入で指摘された。",
            f"タップ穴口元の面取り不足によりネジ挿入時へのバリ噛みが発生。{n_h}穴中{random.randint(1,3)}穴で確認。",
        ],
        "面粗さ不良": [
            f"{spot}の仕上げ面が要求Ra{random.choice([0.8, 1.6, 3.2])}に対し粗く、{gauge}でRa{random.choice([3.2, 6.3, 12.5])}相当。びびり模様も視認できる。",
            f"{part}のシール面に送りマークが濃く残り、粗さ計測定で規格外。工具チップの欠けを後で確認した。",
        ],
        "工具破損": [
            f"φ{random.choice([3, 4, 5, 6])}ドリルが{part}の深穴加工中に折損し、先端が穴底に残留したまま次工程へ流出しかけた。",
            f"{part}のM{random.choice([4, 5, 6, 8])}タップ加工中に折損が発生。折れ込みの摘出時に{spot}へ二次的な傷が入り、当該品は廃却とした。",
        ],
        "刻印・表示誤り": [
            f"ロット番号刻印が指定と異なり、{part}の{spot}付近に前ロットの番号が打刻されていた。",
            f"{part}のレーザー刻印が規定深さ{random.choice([0.15, 0.2, 0.3])}mmに対し浅く、洗浄後に識別番号が判読困難となった。",
        ],
        "加工段差": [
            f"{spot}の再チャック後の加工つなぎ目に約{o}mmの段差が発生し、手仕上げでも許容内に収まらなかった。",
            f"{part}の{spot}で荒加工と仕上げ加工の境界に目視で分かる約{o}mmの段差。工具長補正の入力値相違が疑われる。",
        ],
        "ひずみ変形": [
            f"薄肉部の{part}がクランプ圧により歪み、平面度が{o}mm超過。除去後のスプリングバックも確認された。",
            f"溶接歪みにより{part}の{spot}が{o}mm反り、後工程の研磨で修正しきれなかった。",
        ],
        "角部欠け": [
            f"{part}の{spot}角部に微小な欠けが{random.randint(1, 3)}箇所。切込み過大時の衝撃によるものとみられる。",
            f"搬出時の落下により{part}の{spot}が幅約{random.randint(2, 12)}mmにわたり欠損。床面に破片を確認した。",
        ],
        "取付方向誤り": [
            f"治具への{part}の位相を180度誤って取り付け、{spot}を誤った側に加工した。",
            f"{part}の組立工程でスペーサ{random.randint(1, 2)}枚の入れ忘れがあり、締結後のガタで気付いた。",
        ],
        "NCプログラム誤り": [
            f"NCプログラムの工具径補正呼び出し番号を誤り、{spot}が一律{o}mm深く加工された。",
            f"{part}の新規プログラムの座標系設定ミスで初品の穴群全体が{o}mmオフセット。初品検証で流出は防止した。",
        ],
    }
    return random.choice(variants[ph])

def make_good_condition(ph: str) -> str:
    return random.choice({
        "寸法公差外れ": ["全寸法が図面公差内にあり、基準面からの測定で再現性があること。",
                   "はめあい部が相手ゲージにスムーズに嵌合すること。"],
        "穴位置ずれ": ["穴群の位置度が基準ダボ基準で公差内に収まっていること。",
                     "相手部品との仮組みで無理なくボルトが通ること。"],
        "表面キズ": ["機能面・意匠面に目視で判別できる線状・点状の傷が無いこと。"],
        "バリ残り": ["全エッジが指示どおり面取りされ、指触・目視でバリが無いこと。"],
        "面粗さ不良": ["指定面の粗さが図面要求値以下で、びびり模様が無いこと。"],
        "工具破損": ["穴内に異物・残留物が無く、内面が健全であること。"],
        "刻印・表示誤り": ["指定のロット番号が指定位置に判読可能な深さで刻印されていること。"],
        "加工段差": ["加工つなぎ目に指触で分かる段差が無く、面が連続していること。"],
        "ひずみ変形": ["平面度・真直度が図面要求内で、フリー状態でも保持されること。"],
        "角部欠け": ["角部・エッジに欠損が無く、面取り形状が均一であること。"],
        "取付方向誤り": ["位相・向き・構成部品が図面および手順書の指定どおりであること。"],
        "NCプログラム誤り": ["初品検証で全加工要素が図面と一致していること。"],
    }[ph])

def make_cause(factor: str, ph: str) -> str:
    return random.choice({
        "初品確認漏れ": ["段取り替え後の初品測定を省略し、ずれに気付かないまま連続加工した。",
                   "図面改訂版の反映を確認せず、旧寸法のまま加工した。"],
        "加工条件の理解不足": ["材質ごとの切削条件の使い分けを理解しておらず、不適切な条件で加工した。"],
        "習熟不足": ["配属間もない作業者が単独で段取りを行い、基準面の当たりを誤った。"],
        "標準手順の省略": ["標準書で定める中間検査を飛ばして次工程へ進めた。",
                   "洗浄→検査の順序を入れ替えたため、切粉を挟んだまま測定していた。"],
        "工具寿命超過": ["工具寿命管理表の更新が漏れ、摩耗限度を超えた工具を使用し続けた。"],
        "設備不調": ["主軸のクランプ圧低下により加工中に微小なワークずれが生じていた。"],
        "NCデータ設定誤り": ["プログラム転送時に旧版を呼び出し、修正前の座標で加工した。"],
        "素材欠陥": ["素材ロットに内部欠陥(鋳巣)があり、加工後の面に露出した。"],
        "図面の読み違い": ["対称形状の左右を取り違えて読み、反転した位置に加工した。"],
        "変更連絡の不達": ["設計変更の連絡が現場に届いておらず、変更前の仕様で製作した。"],
    }[factor])

def make_countermeasure(factor: str) -> str:
    return random.choice({
        "初品確認漏れ": ["段取り替え後の初品測定をチェックシート必須項目とし、記録を班長が確認する。",
                   "図面改訂時は旧版を回収し、作業台には最新版のみ置く運用に変更する。"],
        "加工条件の理解不足": ["材質別の推奨切削条件表を機械脇に掲示し、初回は有資格者が立ち会う。"],
        "習熟不足": ["新任者の単独段取りを解禁する前に、技能評価チェックリストでの認定を必須化する。"],
        "標準手順の省略": ["工程順序をポカヨケ化(前工程の検印が無いと次工程の治具が使えない)する。"],
        "工具寿命超過": ["工具寿命を加工数カウンタで自動管理し、限度到達で機械側が警告する設定にする。"],
        "設備不調": ["クランプ圧の始業点検を点検表に追加し、規定値未満は保全へ即連絡とする。"],
        "NCデータ設定誤り": ["プログラムは版番号付きでサーバー一元管理とし、機械側のローカル保存を禁止する。"],
        "素材欠陥": ["受入時の抜き取り探傷を追加し、素材メーカーへ是正を要求する。"],
        "図面の読み違い": ["対称形状部品は加工前に治具上でマーキング照合する手順を追加する。"],
        "変更連絡の不達": ["設計変更は変更通知書の現場受領サインをもって発効とするルールに改める。"],
    }[factor])

NOTES_POOL = [
    "同一ロット残品は全数選別を実施し、良品のみ次工程へ払い出した。",
    "客先へ経緯を報告済み。代替品を特急で製作し納期内に納入した。",
    "暫定処置として当該機械での同品番加工を一時停止した。",
    "類似品番への横展開点検を計画中。",
    "廃却処理済み。材料費は損失計上した。",
    "",
    "",
]

# ---------------------------------------------------------------------------
# 2. 行生成
# ---------------------------------------------------------------------------
FIELDNAMES = [
    "defect_id", "occurrence_date", "report_date", "customer", "discoverer",
    "process", "machine_name", "operator_name", "part_number", "part_name",
    "production_count", "defect_count", "defect_description", "good_condition",
    "phenomenon", "cause", "factor", "category_4m", "severity", "status",
    "countermeasure", "material_cost", "processing_cost", "outsourcing_cost",
    "other_cost", "total_cost", "is_recurrence", "has_procedure", "notes",
]


def weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


# 月別の繁閑ウェイト(7月・11月に山 — 前版とは別の季節性)
_MONTH_W = {4: 9, 5: 6, 6: 8, 7: 15, 8: 7, 9: 10, 10: 8, 11: 14, 12: 6, 1: 7, 2: 5, 3: 11}


def _jitter(weights, lo=0.3, hi=2.5):
    """カテゴリ分布の重みに乗算ジッターをかけ、構成比が既知の値と一致しないようにする。"""
    return [w * random.uniform(lo, hi) for w in weights]


# すべての分布をシード依存でゆがめる(客先シェア・工程比率・現象比率・重大度・状態・季節性)
CUSTOMER_WEIGHTS = _jitter(CUSTOMER_WEIGHTS)
PROCESS_WEIGHTS = _jitter(PROCESS_WEIGHTS)
PHENOMENON_WEIGHTS = _jitter(PHENOMENON_WEIGHTS)
_MONTH_W = {m: w * random.uniform(0.45, 2.2) for m, w in _MONTH_W.items()}
SEV_W_LINE_A = _jitter([10, 34, 40, 16])
SEV_W_OTHER = _jitter([6, 28, 44, 22])
STATUS_W = _jitter([70, 18, 12])
# 重大度ごとの基準コストも±で揺らす
BASE_COSTS = {
    "critical": 60000 * random.uniform(0.7, 1.5),
    "high": 35000 * random.uniform(0.7, 1.5),
    "medium": 18000 * random.uniform(0.7, 1.5),
    "low": 8000 * random.uniform(0.7, 1.5),
}
DAY_WEIGHTS = [
    _MONTH_W[(DATE_START + dt.timedelta(days=d)).month] for d in range(TOTAL_DAYS + 1)
]


# 機械ごとのトラブル係数(0.35〜3.2倍)。同じ工程でも問題機に不良が集中する
_MACHINE_TROUBLE: dict = {}


def _machine_pick(process: str) -> str:
    cands = PROCESS_MACHINE[process]
    ws = []
    for m in cands:
        if m not in _MACHINE_TROUBLE:
            _MACHINE_TROUBLE[m] = 10 ** random.uniform(-0.45, 0.5)
        ws.append(_MACHINE_TROUBLE[m])
    return random.choices(cands, weights=ws, k=1)[0]


def generate_rows():
    rows = []
    seen_desc: set = set()
    for i in range(1, N_ROWS + 1):
        phenomenon = weighted_choice(PHENOMENA, PHENOMENON_WEIGHTS)
        process = weighted_choice(PROCESSES, PROCESS_WEIGHTS)
        machine = _machine_pick(process)
        part_name, line = random.choice(PARTS)
        customer = weighted_choice(CUSTOMERS, CUSTOMER_WEIGHTS)

        # 月ごとの繁閑(季節性): 月別ウェイトで発生日を偏らせる
        occ = DATE_START + dt.timedelta(days=weighted_choice(range(TOTAL_DAYS + 1), DAY_WEIGHTS))
        delay = random.randint(0, 13) if random.random() < 0.93 else random.randint(21, 60)
        rep = min(occ + dt.timedelta(days=delay), DATE_END)

        # 加工数: 混合分布(試作/小ロット/量産/大量産)。1個〜2000個まで大きく散らす
        u = random.random()
        if u < 0.22:            # 試作・一品もの
            production = random.randint(1, 5)
        elif u < 0.72:          # 小〜中ロット(対数一様 5〜80)
            production = int(round(10 ** random.uniform(0.7, 1.9)))
        elif u < 0.95:          # 量産(80〜600)
            production = int(round(10 ** random.uniform(1.9, 2.78)))
        else:                   # 大量産(600〜2000)
            production = int(round(10 ** random.uniform(2.78, 3.3)))
        production = max(1, production)
        # 不適合数: 不良率も0.1%〜全数まで幅広く(全数NG 3% / 微少混入 15% / 通常)
        v = random.random()
        if v < 0.03:
            defect = production                       # ロット全数NG
        elif v < 0.18:
            rate = 10 ** random.uniform(-3, -1.7)     # 0.1〜2% の微少混入
            defect = max(1, int(round(production * rate)))
        else:
            rate = 10 ** random.uniform(-1.7, -0.35)  # 2〜45%
            defect = max(1, min(production, int(round(production * rate))))

        factor = random.choice(FACTORS)
        # 航空補機ラインは重大度が上がりやすい設定(世界観)
        sev_w = SEV_W_LINE_A if line == "A" else SEV_W_OTHER
        severity = weighted_choice(["critical", "high", "medium", "low"], sev_w)
        status = weighted_choice(["completed", "in_progress", "open"], STATUS_W)

        base_cost = BASE_COSTS[severity]
        # 対数正規的な分散で金額を大きくばらけさせる(数千円〜数百万円)。裾を重めに
        scale = (defect ** 0.7) * (10 ** random.gauss(0, 0.5))
        if severity in ("critical", "high") and random.random() < 0.06:
            scale *= random.uniform(3.0, 8.0)  # 選別費・客先ライン停止などの特別費
        material = round(base_cost * 0.35 * scale, 0)
        processing = round(base_cost * 0.5 * scale * random.uniform(0.6, 1.8), 0)
        outsourcing = round(base_cost * 0.3 * scale * random.uniform(0.5, 2.0), 0) if random.random() < 0.25 else 0.0
        other = round(base_cost * 0.15 * scale, 0) if random.random() < 0.4 else 0.0

        desc = make_description(phenomenon, part_name)
        for _ in range(8):  # 同文の完全重複は引き直す(検索・RAGの品質確保)
            if desc not in seen_desc:
                break
            desc = make_description(phenomenon, part_name)
        seen_desc.add(desc)

        rows.append({
            "defect_id": f"KZ25-{i:04d}",
            "occurrence_date": occ.isoformat(),
            "report_date": rep.isoformat(),
            "customer": customer,
            "discoverer": random.choice(STAFF),
            "process": process,
            "machine_name": machine,
            "operator_name": random.choice(STAFF),
            "part_number": part_number(line),
            "part_name": part_name,
            "production_count": production,
            "defect_count": defect,
            "defect_description": desc,
            "good_condition": make_good_condition(phenomenon),
            "phenomenon": phenomenon,
            "cause": make_cause(factor, phenomenon),
            "factor": factor,
            "category_4m": FACTOR_4M[factor] if random.random() < 0.9 else "",
            "severity": severity,
            "status": status,
            "countermeasure": make_countermeasure(factor),
            "material_cost": material,
            "processing_cost": processing,
            "outsourcing_cost": outsourcing,
            "other_cost": other,
            "total_cost": round(material + processing + outsourcing + other, 0),
            "is_recurrence": random.random() < 0.12,
            "has_procedure": random.random() < 0.85,
            "notes": random.choice(NOTES_POOL),
        })
    rows.sort(key=lambda r: r["occurrence_date"])
    for i, r in enumerate(rows, start=1):
        r["defect_id"] = f"KZ25-{i:04d}"
    return rows[:N_KEEP]


def write_csv(rows):
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    print(f"[CSV] {CSV_PATH} に {len(rows)} 件を書き出しました。")


# ---------------------------------------------------------------------------
# 3. Excel 帳票(霧沢精機 社内様式 QF-07-03 — 新規デザイン)
# ---------------------------------------------------------------------------
def write_xlsx(rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    os.makedirs(XLSX_DIR, exist_ok=True)
    thin = Side(style="thin", color="9BA4AE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    sec_fill = PatternFill("solid", fgColor="2F4A5E")
    sec_font = Font(name="Yu Gothic", size=11, bold=True, color="FFFFFF")
    label_fill = PatternFill("solid", fgColor="EDF1F4")
    label_font = Font(name="Yu Gothic", size=9, bold=True, color="42505B")
    value_font = Font(name="Yu Gothic", size=10)
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    def section(ws, row, text):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        c = ws.cell(row=row, column=1, value=text)
        c.fill, c.font = sec_fill, sec_font
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[row].height = 18
        return row + 1

    def pair_row(ws, row, pairs):
        """(label, value) を最大3組、6列に配置。"""
        col = 1
        for label, value in pairs:
            lc = ws.cell(row=row, column=col, value=label)
            lc.fill, lc.font, lc.alignment, lc.border = label_fill, label_font, center, border
            vc = ws.cell(row=row, column=col + 1, value=value)
            vc.font, vc.alignment, vc.border = value_font, left, border
            col += 2
        while col <= 6:
            ws.cell(row=row, column=col).border = border
            col += 1
        return row + 1

    def text_block(ws, row, label, text, height=42):
        r = section(ws, row, label)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        c = ws.cell(row=r, column=1, value=text)
        c.font, c.alignment = value_font, left
        for col in range(1, 7):
            ws.cell(row=r, column=col).border = border
        ws.row_dimensions[r].height = height
        return r + 1

    for r in rows:
        wb = Workbook()
        ws = wb.active
        ws.title = "QF-07-03"
        for col, w in zip("ABCDEF", [13, 21, 13, 21, 13, 21]):
            ws.column_dimensions[col].width = w

        # --- ヘッダー(様式枠 + 承認欄) ---
        ws.merge_cells("A1:C2")
        t = ws["A1"]
        t.value = "不適合報告書"
        t.font = Font(name="Yu Gothic", size=17, bold=True, color="2F4A5E")
        t.alignment = Alignment(horizontal="left", vertical="center")
        ws.merge_cells("D1:D2")
        f_ = ws["D1"]
        f_.value = f"様式 QF-07-03 改訂C\n{COMPANY} {PLANT}"
        f_.font = Font(name="Yu Gothic", size=8, color="42505B")
        f_.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        # 承認/確認 の印欄(E=承認, F=確認)
        ws["E1"].value, ws["F1"].value = "承認", "確認"
        for addr in ("E1", "F1"):
            ws[addr].fill, ws[addr].font = label_fill, label_font
            ws[addr].alignment, ws[addr].border = center, border
        for addr in ("E2", "F2"):
            ws[addr].border = border
        ws.row_dimensions[1].height = 16
        ws.row_dimensions[2].height = 26

        row = 3
        row = pair_row(ws, row, [("報告書番号", r["defect_id"]), ("発行日", r["report_date"]),
                                 ("重大度", r["severity"])])
        row = section(ws, row, "1. 発生状況")
        row = pair_row(ws, row, [("発生日", r["occurrence_date"]), ("発生工程", r["process"]),
                                 ("使用機械", r["machine_name"])])
        row = pair_row(ws, row, [("客先", r["customer"]), ("作業者", r["operator_name"]),
                                 ("発見者", r["discoverer"])])
        row = section(ws, row, "2. 対象品")
        row = pair_row(ws, row, [("部品番号", r["part_number"]), ("品名", r["part_name"]),
                                 ("数量", f"{r['defect_count']} / {r['production_count']}")])
        row = text_block(ws, row, "3. 不適合内容(現象: " + r["phenomenon"] + ")", r["defect_description"])
        row = text_block(ws, row, "4. 良品状態(あるべき姿)", r["good_condition"], height=30)
        row = text_block(ws, row, "5. 原因(要因: " + (r["factor"] or "-") + " / 4M: " + (r["category_4m"] or "-") + ")",
                         r["cause"], height=34)
        row = text_block(ws, row, "6. 対策(恒久)", r["countermeasure"], height=34)
        row = section(ws, row, "7. 費用・処理")
        row = pair_row(ws, row, [("材料費", f"{r['material_cost']:,.0f}円"),
                                 ("加工費", f"{r['processing_cost']:,.0f}円"),
                                 ("外注費", f"{r['outsourcing_cost']:,.0f}円")])
        row = pair_row(ws, row, [("その他", f"{r['other_cost']:,.0f}円"),
                                 ("損失合計", f"{r['total_cost']:,.0f}円"),
                                 ("状態", r["status"])])
        if r["notes"]:
            row = text_block(ws, row, "8. 備考・暫定処置", r["notes"], height=26)

        wb.save(os.path.join(XLSX_DIR, f"{r['defect_id']}.xlsx"))
    print(f"[XLSX] {XLSX_DIR} に {len(rows)} 件のフォームを書き出しました。")


# ---------------------------------------------------------------------------
# 4. PDF 帳票(同じ様式の印刷版 — 新規デザイン)
# ---------------------------------------------------------------------------
def write_pdf(rows):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    os.makedirs(PDF_DIR, exist_ok=True)
    FONT = "HeiseiKakuGo-W5"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))

    navy = colors.HexColor("#2F4A5E")
    pale = colors.HexColor("#EDF1F4")
    line_c = colors.HexColor("#9BA4AE")

    title_style = ParagraphStyle("t", fontName=FONT, fontSize=15, textColor=navy)
    small = ParagraphStyle("s", fontName=FONT, fontSize=7.5, textColor=colors.HexColor("#42505B"))
    body = ParagraphStyle("b", fontName=FONT, fontSize=9, leading=13)

    def sec_table(label, text):
        return Table(
            [[Paragraph(label, ParagraphStyle("h", fontName=FONT, fontSize=9, textColor=colors.white))],
             [Paragraph(text or "-", body)]],
            colWidths=[180 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), navy),
                ("GRID", (0, 0), (-1, -1), 0.5, line_c),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (0, 1), 5),
                ("BOTTOMPADDING", (0, 1), (0, 1), 7),
            ]),
        )

    def grid(pairs):
        cells = []
        for label, value in pairs:
            cells += [Paragraph(label, ParagraphStyle("l", fontName=FONT, fontSize=8, textColor=colors.HexColor("#42505B"))),
                      Paragraph(str(value), body)]
        return Table([cells], colWidths=[24 * mm, 36 * mm] * len(pairs),
                     style=TableStyle([
                         ("BACKGROUND", (0, 0), (0, 0), pale), ("BACKGROUND", (2, 0), (2, 0), pale),
                         ("BACKGROUND", (4, 0), (4, 0), pale),
                         ("GRID", (0, 0), (-1, -1), 0.5, line_c),
                         ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ]))

    for r in rows[:N_PDF]:
        doc = SimpleDocTemplate(os.path.join(PDF_DIR, f"{r['defect_id']}.pdf"), pagesize=A4,
                                leftMargin=15 * mm, rightMargin=15 * mm,
                                topMargin=14 * mm, bottomMargin=14 * mm)
        story = [
            Table([[Paragraph("不適合報告書", title_style),
                    Paragraph(f"様式 QF-07-03 改訂C<br/>{COMPANY} {PLANT}<br/>報告書番号: {r['defect_id']} / 発行日: {r['report_date']}", small)]],
                  colWidths=[90 * mm, 90 * mm],
                  style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LINEBELOW", (0, 0), (-1, 0), 1, navy)])),
            Spacer(1, 4),
            grid([("発生日", r["occurrence_date"]), ("発生工程", r["process"]), ("使用機械", r["machine_name"])]),
            grid([("客先", r["customer"]), ("作業者", r["operator_name"]), ("発見者", r["discoverer"])]),
            grid([("部品番号", r["part_number"]), ("品名", r["part_name"]),
                  ("数量", f"{r['defect_count']} / {r['production_count']}")]),
            Spacer(1, 4),
            sec_table(f"1. 不適合内容(現象: {r['phenomenon']} / 重大度: {r['severity']})", r["defect_description"]),
            Spacer(1, 3),
            sec_table("2. 良品状態(あるべき姿)", r["good_condition"]),
            Spacer(1, 3),
            sec_table(f"3. 原因(要因: {r['factor']} / 4M: {r['category_4m'] or '-'})", r["cause"]),
            Spacer(1, 3),
            sec_table("4. 対策(恒久)", r["countermeasure"]),
            Spacer(1, 3),
            grid([("材料費", f"{r['material_cost']:,.0f}円"), ("加工費", f"{r['processing_cost']:,.0f}円"),
                  ("外注費", f"{r['outsourcing_cost']:,.0f}円")]),
            grid([("その他", f"{r['other_cost']:,.0f}円"), ("損失合計", f"{r['total_cost']:,.0f}円"),
                  ("状態", r["status"])]),
        ]
        if r["notes"]:
            story += [Spacer(1, 3), sec_table("5. 備考・暫定処置", r["notes"])]
        doc.build(story)
    print(f"[PDF] {PDF_DIR} に先頭 {min(N_PDF, len(rows))} 件のフォームを書き出しました。")


if __name__ == "__main__":
    rows = generate_rows()
    write_csv(rows)
    write_xlsx(rows)
    write_pdf(rows)
    print("完了: 完全架空データの生成が終了しました。")
