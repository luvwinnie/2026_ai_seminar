from analyze import value_score, passed, grounded


def test_single_item_array_is_diagnostic_only():
    case={'suite':'rag','expected':{'report_id':'KZ25-0114'}}
    r={'answer':'```json\n[{"report_id":"KZ25-0114"}]\n```',
       'status':'completed','score':{'correct':False,'citation_supported':True}}
    assert value_score(case,r)
    assert passed(case,r)
    assert r['score']['correct'] is False


def test_multiple_candidates_and_wrong_citations_still_fail():
    case={'suite':'rag','expected':{'report_id':'KZ25-0114'}}
    r={'answer':'```json\n[{"report_id":"KZ25-0114"},{"report_id":"KZ25-0049"}]\n```',
       'status':'completed','score':{'correct':False,'citation_supported':False}}
    assert not value_score(case,r)
    assert not passed(case,r)


def test_ontology_requires_real_workflow_even_when_values_match():
    case={'suite':'ontology','expected':{'report_count':2,'capa_ids':['CA-1']}}
    r={'answer':'```json\n{"report_count":[2],"capa_ids":["CA-1"]}\n```',
       'status':'completed','score':{'tool_workflow_correct':False}}
    assert value_score(case,r)
    assert not passed(case,r)


def test_grounded_query_checks_scope_and_tool_output():
    case={'id':'O03','suite':'ontology','expected':{'report_count':2},
          'required_calls':[{'name':'query_quality_ontology','arguments':{'scope':{'machine_id':'A'}}}]}
    call={'name':'query_quality_ontology','arguments':{'scope':{'machine_id':'A'}},
          'success':True,'schema_valid':True,'output':{'metrics':{'report_count':2}}}
    r={'answer':'{"report_count":2}','status':'completed','calls':[call],'score':{}}
    assert grounded(case,r)
    call['output']['metrics']['report_count']=3
    assert not grounded(case,r)
    call['output']['metrics']['report_count']=2
    call['arguments']['scope']={}
    assert not grounded(case,r)
    r['calls']=[]
    assert not grounded(case,r)


def test_grounded_ambiguity_accepts_short_query_only_with_real_candidates():
    case={'id':'O07','suite':'ontology','expected':{'needs_clarification':True}}
    call={'name':'resolve_ontology_entity','arguments':{'object_type':'MachineLabel','query':'BENCH'},
          'success':True,'schema_valid':True,'output':{'can_auto_select':False,'candidates':[{'label':'BENCH設備A'},{'label':'BENCH設備B'}]}}
    r={'answer':'{"needs_clarification":true}','status':'completed','calls':[call],'score':{}}
    assert grounded(case,r)
    call['output']['candidates']=[]
    assert not grounded(case,r)


def test_grounded_link_follows_actual_capa_foreign_key():
    case={'id':'O10','suite':'ontology','expected':{'report_id':'KZ25-9001','machine_name':'BENCH設備A'}}
    capa={'name':'get_ontology_object','arguments':{'object_type':'CapaAction','object_id':'CA-BENCH-1'},'success':True,'schema_valid':True,'output':{'properties':{'defect_id':'KZ25-9001'}}}
    report={'name':'get_defect_report','arguments':{'defect_id':'KZ25-9001'},'success':True,'schema_valid':True,'output':{'machine_name':'BENCH設備A'}}
    r={'answer':'{"report_id":"KZ25-9001","machine_name":"BENCH設備A"}','status':'completed','calls':[capa,report],'score':{}}
    assert grounded(case,r)
    capa['output']['properties']['defect_id']='KZ25-9002'
    assert not grounded(case,r)
