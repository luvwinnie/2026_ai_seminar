"""① 検索の並べ替えの問題(eval_rerank.py と同じ16問)。rows は {defect_id: DB の行}。"""


def items(rows):
    by = lambda f: {i for i, r in rows.items() if f(r)}
    PH = lambda name: by(lambda r: r.phenomenon == name)
    return [
        ("Q1", "表面がざらざらして仕上がりが悪い", PH("面粗さ不良")),
        ("Q2", "QUICK TURN 250MSY の工具破損", {"KZ25-0039"}),
        ("Q3", "GENOS M560-V の寸法不良の傾向と原因は?", set()),
        ("Q4", "バリが取り切れていなかった", PH("バリ残り")),
        ("Q5", "主軸のクランプ圧低下が原因の報告は何件で、どの現象に出ている?", by(lambda r: "クランプ圧" in (r.cause or ""))),
        ("P1", "ドリルやエンドミルが折れた", PH("工具破損")),
        ("P2", "部品が曲がって反ってしまった", PH("ひずみ変形")),
        ("P3", "穴の位置が図面と合わない", PH("穴位置ずれ")),
        ("P4", "加工面に段がついてしまった", PH("加工段差")),
        ("P5", "加工プログラムの設定を間違えた", PH("NCプログラム誤り")),
        ("P6", "寸法が公差から外れていた", PH("寸法公差外れ")),
        ("P7", "刻印の番号が間違っていた", PH("刻印・表示誤り")),
        ("P8", "部品を逆向きに取り付けた", PH("取付方向誤り")),
        ("N1", "搬送中に隣の品物と当たって付いたキズ", by(lambda r: "隣接品" in (r.defect_description or ""))),
        ("N2", "治具の固定が甘くてずれた事例は？", by(lambda r: "クランプ圧" in (r.cause or ""))),
        ("N3", "チャックに切粉が噛み込んで付いた傷の対策は？",
         by(lambda r: "切粉" in (r.defect_description or "") and "噛み込" in (r.defect_description or ""))),
    ]
