"""現在のアプリの検索結果を固定し、独立に計算した正解付き評価問題を作る。"""
import asyncio
import base64
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from fastmcp import Client

HERE = Path(__file__).resolve().parent


def label_id(kind, value):
    return kind + ':' + base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')


def fixtures():
    reports = []
    for i, machine, production, defects, cost in [
        (1, 'BENCH設備A', 100, 10, 100), (2, 'BENCH設備A', 900, 9, 200),
        (3, 'BENCH設備B', 0, 0, None),
    ]:
        reports.append(dict(defect_id=f'KZ25-9{i:03d}', occurrence_date=f'2026-01-0{i}',
            customer='BENCH顧客', process='BENCH工程', machine_name=machine,
            operator_name='BENCH作業者', part_number='BENCH-P1', part_name='評価専用部品',
            production_count=production, defect_count=defects, total_cost=cost,
            defect_description='評価専用の不適合報告。実業務データではない。', phenomenon='評価傷',
            severity='high', status='open'))
    capas = [dict(capa_id=f'CA-BENCH-{i}', defect_id=did, title=f'評価専用処置{i}',
                  status=status, action_type='corrective', effect_note='再検査済み' if status == 'closed' else None)
             for i, did, status in [(1,'KZ25-9001','open'),(2,'KZ25-9001','in_progress'),(3,'KZ25-9002','closed')]]
    return reports, capas


def aggregate(rows):
    prod = sum(r['production_count'] for r in rows)
    defect = sum(r['defect_count'] for r in rows)
    known = [Decimal(str(r['total_cost'])) for r in rows if r.get('total_cost') is not None]
    return dict(report_count=len(rows), known_loss_jpy=float(sum(known)) if known else None if rows else 0,
                recorded_defect_rate=defect/prod if prod else None)


async def main():
    snapshot = json.loads((HERE/'snapshot.json').read_text())
    rows = snapshot['reports']
    byid = {r['defect_id']:r for r in rows}
    cases = []
    paraphrases = [
        ('KZ25-0117', 'オイル溝を再度つかみ直して削ったつなぎ目に0.191mmの段が残り、手仕上げでも直せなかった事例'),
        ('KZ25-0116', 'フランジの合わせ面の幅が0.046mm大きく、仕上げ代の残し過ぎが疑われた事例'),
        ('KZ25-0114', '洗浄後にケーシングカバーの合わせ面へ10mmの弧状の擦り傷が見つかり、チャック爪に切粉が挟まっていた事例'),
        ('KZ25-0115', '梱包を開けたインペラハウジングの皿モミ部に0.124mmのへこみがあり、緩衝材の仕切り不足が疑われた事例'),
        ('KZ25-0113', 'バルブボディの新しいプログラムで座標系を誤り、穴のまとまり全体が0.192mmずれた初品の事例'),
        ('KZ25-0112', 'マニホールドブロックの皿モミ部に15mmの円弧状の擦り傷があり、新任者の段取りが原因と記録された事例'),
    ]
    retrieval = []
    async with Client('http://localhost:8000/mcp/') as mcp:
        for i,(did, description) in enumerate(paraphrases,1):
            result = await mcp.call_tool('search_defect_reports', {'query':description,'top_k':5})
            raw = result.data
            hits = raw if isinstance(raw,list) else raw.get('items',raw.get('results',[]))
            ids = [r['defect_id'] for r in hits]
            ctx = [{k:byid[x].get(k) for k in ['defect_id','machine_name','process','defect_description','cause','countermeasure']}
                   for x in ids if x in byid]
            rank = ids.index(did)+1 if did in ids else None
            retrieval.append({'id':f'R{i:02}', 'query':description, 'gold_ids':[did], 'retrieved_ids':ids,
                              'rank':rank, 'hit_at_5':rank is not None,'reciprocal_rank':1/rank if rank else 0})
            cases.append(dict(id=f'R{i:02}',suite='rag',question=f'{description}を探し、報告書ID・機械名・工程名を答えてください。',
                 output_keys=['report_id','machine_name','process'],
                 expected={'report_id':did,'machine_name':byid[did]['machine_name'],'process':byid[did]['process']},
                 context=ctx,gold_ids=[did]))
    def tool(i, question, name, args):
        cases.append(dict(id=f'T{i:02}',suite='tool',question=question,expected_call={'name':name,'arguments':args}))
    tool(1,'機械名 a61nx が実在するか、最初に正確な対象を確認してください。','resolve_ontology_entity',{'object_type':'MachineLabel','query':'a61nx'})
    tool(2,'KZ25-0117の報告書の全文を取得してください。','get_defect_report',{'defect_id':'KZ25-0117'})
    tool(3,'KZ25-9001の報告書に関連するCAPAを、Ontologyの関係からたどってください。','traverse_ontology_relation',{'object_type':'DefectReport','object_id':'KZ25-9001','relation':'has_capa'})
    tool(4,'CA-BENCH-1をclosedにした場合の検証だけをしてください。効果確認メモはまだありません。保存はしないでください。','preview_capa_update',{'capa_id':'CA-BENCH-1','status':'closed'})
    tool(5,'Ontologyのグラフを画面に表示してください。','ui_navigate',{'page':'ontology_graph'})
    tool(6,'画面をダークモードにしてください。','ui_set_theme',{'mode':'dark'})
    tool(7,'2025年10月1日から12月31日までに発生したhighの報告について、Ontologyで損失額と件数を集計してください。','query_quality_ontology',{'scope':{'date_from':'2025-10-01','date_to':'2025-12-31','severity':'high'}})
    tool(8,'「工具の摩耗で寸法がずれた」に似た不具合を検索してください。','search_defect_reports',{'query':'工具の摩耗で寸法がずれた'})
    def agent(i,q,expected,requirements,**extra):
        cases.append(dict(id=f'O{i:02}',suite='ontology',question=q,output_keys=list(expected),expected=expected,
                          required_calls=requirements,**extra))
    def req(name, **args):return {'name':name,'arguments':args}
    a = [r for r in rows if r['machine_name']=='a61nx']
    agent(1,'a61nxの報告件数、既知の損失額、記録上の不適合率を調べてください。',aggregate(a),
          [req('resolve_ontology_entity',object_type='MachineLabel',query='a61nx'),req('query_quality_ontology',scope={'machine_id':label_id('MachineLabel','a61nx')})])
    sub = [r for r in a if '2025-07-01'<=r['occurrence_date']<='2025-12-31']
    agent(2,'a61nxについて、発生日が2025年7月1日から12月31日の報告件数と既知損失を調べてください。',
          {k:v for k,v in aggregate(sub).items() if k!='recorded_defect_rate'},
          [req('resolve_ontology_entity',object_type='MachineLabel',query='a61nx'),req('query_quality_ontology',scope={'machine_id':label_id('MachineLabel','a61nx'),'date_from':'2025-07-01','date_to':'2025-12-31'})])
    agent(3,'BENCH設備Aの報告件数、既知損失、記録上の不適合率、未クローズCAPA件数を調べてください。',
          dict(report_count=2,known_loss_jpy=300,recorded_defect_rate=.019,open_capa_count=2),
          [req('resolve_ontology_entity',object_type='MachineLabel',query='BENCH設備A'),req('query_quality_ontology',scope={'machine_id':label_id('MachineLabel','BENCH設備A')})])
    agent(4,'BENCH設備Bの記録上の不適合率、既知の損失額、損失額未入力の報告件数を調べてください。不明はnullとしてください。',
          dict(recorded_defect_rate=None,known_loss_jpy=None,missing_loss_reports=1),
          [req('resolve_ontology_entity',object_type='MachineLabel',query='BENCH設備B'),req('query_quality_ontology',scope={'machine_id':label_id('MachineLabel','BENCH設備B')})])
    agent(5,'KZ25-9001に関連する全CAPAのIDを調べてください。',{'capa_ids':['CA-BENCH-1','CA-BENCH-2']},
          [{'alternatives':[req('traverse_ontology_relation',object_type='DefectReport',object_id='KZ25-9001',relation='has_capa'),req('list_capa_actions',defect_id='KZ25-9001')]}])
    agent(6,'TXG-9000という機械名が実在しますか。似た名前へ読み替えず確認してください。',{'exists':False},
          [{'alternatives':[req('resolve_ontology_entity',object_type='MachineLabel',query='TXG-9000'),req('list_masters',category='machine')]}],forbidden_calls=['query_quality_ontology'])
    agent(7,'BENCH設備の損失額を知りたいです。対象を一意に選べるか確認し、確認が必要ならその旨を答えてください。',{'needs_clarification':True},
          [req('resolve_ontology_entity',object_type='MachineLabel',query='BENCH設備')],forbidden_calls=['query_quality_ontology'])
    agent(8,'CA-BENCH-1をclosedにできるか検証してください。効果確認メモは空欄です。保存はしないでください。',{'valid':False,'saved':False},
          [req('preview_capa_update',capa_id='CA-BENCH-1',status='closed')])
    agent(9,'BENCH設備Aで、未クローズCAPAがある報告だけの件数・既知損失・未クローズCAPA件数を調べてください。',
          dict(report_count=1,known_loss_jpy=100,open_capa_count=2),
          [req('resolve_ontology_entity',object_type='MachineLabel',query='BENCH設備A'),req('query_quality_ontology',scope={'machine_id':label_id('MachineLabel','BENCH設備A'),'has_open_capa':True})])
    agent(10,'CA-BENCH-1の対象報告書IDと、その報告に記録された機械名をOntologyの関係から調べてください。',
          {'report_id':'KZ25-9001','machine_name':'BENCH設備A'},
          [req('traverse_ontology_relation',object_type='CapaAction',object_id='CA-BENCH-1',relation='for_report')])
    payload={'version':'1.0','source_sha256':hashlib.sha256((HERE/'snapshot.json').read_bytes()).hexdigest(),
             'fixture_reports':fixtures()[0],'fixture_capas':fixtures()[1],'cases':cases,'retrieval':retrieval}
    (HERE/'dataset.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print('cases',len(cases),'retrieval hit@5',sum(x['hit_at_5'] for x in retrieval),'/',len(retrieval))


if __name__=='__main__':asyncio.run(main())
