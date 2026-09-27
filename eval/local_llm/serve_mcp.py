"""隔離ベンチマークDBの読み取り専用MCP。業務DBには接続しない。"""
import asyncio
from benchmark import READ_TOOLS, setup_runtime
from fastmcp import Client

mcp, _ = setup_runtime()

async def restrict():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    mcp.disable(names=names - READ_TOOLS, components={'tool'})

if __name__ == '__main__':
    asyncio.run(restrict())
    mcp.run(transport='http', host='127.0.0.1', port=8766, path='/mcp/', show_banner=False)
