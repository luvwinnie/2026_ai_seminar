import copy,json
from pathlib import Path
import run_generation as run

D={c['id']:c for c in json.loads((Path(__file__).parent/'dataset.json').read_text())['cases']}
def result(answer,calls=None):return {'status':'completed','error':None,'answer':json.dumps(answer,ensure_ascii=False),'calls':calls or []}

def test_exact_json_prevents_multiple_answer_cherry_picking():
    assert run.parse_object('{"a":1}\n{"a":2}') is None
    assert run.parse_object('説明です\n{"a":1}') is None
    assert run.parse_object('```json\n{"a":1}\n```')=={'a':1}
    assert run.parse_object('[{"a":1}]') is None

def test_null_zero_and_schema_are_distinct():
    c=D['C04'];r=result(c['expected']);assert run.score(c,r)['correct']
    for k in ['known_loss_jpy','recorded_defect_rate']:
        v=copy.deepcopy(c['expected']);v[k]=0;assert not run.score(c,result(v))['correct']
    v=copy.deepcopy(c['expected']);v['missing_loss_reports']='1';assert not run.score(c,result(v))['correct']

def test_unsupported_citations_and_extra_fields_fail():
    c=D['R03'];v=copy.deepcopy(c['expected']);assert run.score(c,result(v))['correct']
    v['report_id']='KZ25-0049';assert not run.score(c,result(v))['correct']
    v=copy.deepcopy(c['expected']);v['extra']='KZ25-0049';assert not run.score(c,result(v))['correct']

def test_tool_extra_call_does_not_pass():
    c=D['T04'];call={**copy.deepcopy(c['expected_call']),'schema_valid':True}
    assert run.score(c,result({},[call]))['correct']
    assert not run.score(c,result({},[call,call]))['correct']
    v=copy.deepcopy(call);v['arguments']['effect_note']='実施済み';assert not run.score(c,result({},[v]))['correct']

def test_answer_without_actual_ontology_execution_fails():
    c=D['O03'];assert not run.score(c,result(c['expected']))['correct']
    requirement=c['required_calls'][-1]
    call={**copy.deepcopy(requirement),'schema_valid':True,'success':True,'output':{'metrics':c['expected']}}
    assert run.score(c,result(c['expected'],[call]))['correct']
    call['arguments']['scope']={};assert not run.score(c,result(c['expected'],[call]))['correct']

def test_failed_or_truncated_answers_never_pass():
    c=D['R01'];r=result(c['expected']);r['status']='output_truncated';assert not run.score(c,r)['correct']

def test_arrays_are_sets_but_no_duplicates_or_scalar_wrapping():
    c=D['R11'];v={'report_ids':list(reversed(c['expected']['report_ids']))};assert run.score(c,result(v))['correct']
    v['report_ids'].append(v['report_ids'][0]);assert not run.score(c,result(v))['correct']
    c=D['R01'];v={k:[x] for k,x in c['expected'].items()};assert not run.score(c,result(v))['correct']

def test_variants_have_equal_gold_and_schema():
    assert len(D)==50
    for c in D.values():
        if c['variant']=='paraphrase':
            base=D[c['base_id']]
            assert c.get('expected')==base.get('expected')
            assert c.get('output_schema')==base.get('output_schema')
