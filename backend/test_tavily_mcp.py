import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from app.core.config import settings
import sys

async def main():
    print(f"Connecting to MCP with token {settings.TAVILY_API_KEY[:5]}...")
    url = "https://mcp.tavily.com/mcp/sse"
    headers = {
        "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
        "x-api-key": settings.TAVILY_API_KEY,
    }
    
    try:
        async with sse_client(url, headers=headers) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("Tools:", tools)
                
                result = await session.call_tool("tavily-search", {"query": "Latest Next.js version", "search_depth": "basic", "include_answer": True})
                print("Result:", result)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
