"""実OpenCode + MCPを通す読み取り質問。生成した検証チャットのみ最後に削除する。"""
import asyncio
import json
import os
from pathlib import Path

import httpx
from fastmcp import Client

BASE = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
OUT = Path(__file__).resolve().parents[2] / "docs" / "validation" / "ontology_20260915"
OUT.mkdir(parents=True, exist_ok=True)


async def check_protocol():
    async with Client(BASE + "/mcp/") as mcp:
        tools = [t.name for t in await mcp.list_tools()]
        assert "query_quality_ontology" in tools and "preview_capa_update" in tools
        resource = await mcp.read_resource("ontology://quality/definition")
        assert '"MachineLabel"' in resource[0].text
        result = await mcp.call_tool("query_quality_ontology", {"scope": {}, "limit": 1})
        assert result.data["total"] > 0
        return {"tool_count": len(tools), "ontology_tools": [t for t in tools if "ontology" in t or t == "preview_capa_update"]}


protocol = asyncio.run(check_protocol())
print(json.dumps(protocol, ensure_ascii=False), flush=True)
c = httpx.Client(base_url=BASE, timeout=180)
row = c.post('/api/ontology/query', json={'limit': 1}).raise_for_status().json()['objects'][0]
machine = row['properties']['machine_name']
resolved = c.get('/api/ontology/resolve', params={'object_type': 'MachineLabel', 'query': machine}).raise_for_status().json()
scope = {'machine_id': resolved['candidates'][0]['object_id']}
expected = c.post('/api/ontology/query', json={'scope': scope, 'limit': 1}).raise_for_status().json()['metrics']
prompt = f"{machine}について、報告件数・記録上の不適合率・既知の損失額・未クローズCAPA件数を調べてください。工場全体の不良率と呼んでよいかも説明してください。データの登録や更新は不要です。"
events = []
session_id = None
try:
    with c.stream('POST', '/api/chat/stream', json={'message': prompt}) as response:
        response.raise_for_status()
        event = ''
        for line in response.iter_lines():
            if line.startswith('event: '):
                event = line[7:]
            elif line.startswith('data: '):
                value = json.loads(line[6:])
                if event == 'session':
                    session_id = value['id']
                if event in ('tool', 'token', 'error', 'done'):
                    events.append({'type': event, **value})
                if event in ('tool', 'error'):
                    print(json.dumps({'type': event, **value}, ensure_ascii=False), flush=True)
    answer = ''.join(e.get('text', '') for e in events if e['type'] == 'token')
    completed = {e.get('name') for e in events if e['type'] == 'tool' and e.get('status') == 'completed'}
    checks = {
        'entity_resolution_tool': any('resolve_ontology_entity' in str(n) for n in completed),
        'quality_query_tool': any('query_quality_ontology' in str(n) for n in completed),
        'no_error': not any(e['type'] == 'error' for e in events),
        'answer_nonempty': bool(answer.strip()),
    }
    (OUT / 'live_agent.json').write_text(json.dumps({'protocol': protocol, 'question': prompt,
        'expected_metrics': expected, 'checks': checks, 'answer': answer, 'events': events}, ensure_ascii=False, indent=2))
    print(answer, flush=True)
    print(json.dumps(checks, ensure_ascii=False), flush=True)
    assert all(checks.values()), checks
finally:
    if session_id is not None:
        c.delete(f'/api/chat/sessions/{session_id}').raise_for_status()
    c.close()
