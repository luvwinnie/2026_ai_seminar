"""誤った採点でベンチマークを水増ししないことを検証する。"""
from benchmark import fact_equal,parse_json,score


def test_money_count_rate_and_unknown():
    assert fact_equal('841,072',841072)
    assert not fact_equal(841073,841072)
    assert not fact_equal(False,0)
    assert fact_equal(.1208,.12075471698)
    assert not fact_equal(12.08,.12075471698)
    assert not fact_equal(0,None)
    assert not fact_equal('false',False)


def test_no_cherry_picking_correct_entry_from_multiple_answers():
    assert parse_json('```json\n[{"id":"correct"},{"id":"wrong"}]\n```') is None
    assert parse_json('説明\n```json\n{"id":"correct"}\n```') == {'id':'correct'}


def test_irrelevant_citation_fails_even_with_correct_answer_fields():
    case={'suite':'rag','expected':{'report_id':'KZ25-0117'},'gold_ids':['KZ25-0117']}
    result={'answer':'[KZ25-0001]\n```json\n{"report_id":"KZ25-0117"}\n```'}
    assert not score(case,result)['correct']


def test_exact_tool_requires_valid_schema_and_period():
    case={'id':'T07','suite':'tool','expected_call':{'name':'query_quality_ontology','arguments':{'scope':{'date_from':'2026-01-01'}}}}
    assert not score(case,{'calls':[{'name':'query_quality_ontology','schema_valid':True,'arguments':{'scope':{}}}]})['correct']
    assert not score(case,{'calls':[{'name':'query_quality_ontology','schema_valid':False,'arguments':{'scope':{'date_from':'2026-01-01'}}}]})['correct']


def test_text_tool_call_is_not_executed_tool():
    case={'id':'T01','suite':'tool','expected_call':{'name':'resolve_ontology_entity','arguments':{}}}
    assert not score(case,{'answer':'{"tool_calls":[{"name":"resolve_ontology_entity"}]}','calls':[]})['correct']


def test_agent_requires_successful_data_access_in_order():
    case={'suite':'ontology','expected':{'report_count':2},'required_calls':[
        {'name':'resolve_ontology_entity','arguments':{}},{'name':'query_quality_ontology','arguments':{}}]}
    result={'answer':'{"report_count":2}','calls':[
        {'name':'query_quality_ontology','arguments':{},'success':True},
        {'name':'resolve_ontology_entity','arguments':{},'success':True}]}
    assert not score(case,result)['correct']
    result['calls'].reverse()
    assert score(case,result)['correct']
    result['calls'][1]['success']=False
    assert not score(case,result)['correct']
