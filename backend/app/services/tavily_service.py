import httpx
from typing import Dict, Any, List
import asyncio
from app.core.config import settings
from fastmcp import FastMCP
from fastmcp.client import Client, FastMCPTransport

# 1. Define the FastMCP Server
mcp_server = FastMCP("Tavily Search Server")

@mcp_server.tool()
def search_tavily(query: str, search_depth: str = "basic") -> dict:
    """
    Search the web using Tavily API.
    """
    if not settings.TAVILY_API_KEY:
        return {"error": "Tavily API Key is missing"}
        
    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query,
        "search_depth": search_depth,
        "include_answer": True
    }
    
    try:
        with httpx.Client() as client:
            response = client.post("https://api.tavily.com/search", json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"error": str(e)}

class TavilyService:
    @classmethod
    def get_version_evidence(cls, application_name: str) -> str:
        """
        Uses Tavily (via FastMCP) to search for the current latest version of an application.
        Returns the raw results string for the LLM to interpret.
        """
        query = f"latest official release version of {application_name} software release notes"
        
        async def _run_mcp():
            # Use FastMCP Client to connect to the in-memory FastMCP server
            async with Client(FastMCPTransport(mcp_server)) as client:
                result = await client.call_tool("search_tavily", {"query": query, "search_depth": "advanced"})
                # In fastmcp 3.4.7, the return value is often wrapped in `data` or `structured_content`
                return getattr(result, "data", result)
                
        # Handle asyncio event loop gracefully regardless of calling context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import threading
            res_val = None
            def run_in_thread():
                nonlocal res_val
                res_val = asyncio.run(_run_mcp())
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            result = res_val
        else:
            result = loop.run_until_complete(_run_mcp())

        if isinstance(result, dict) and "error" in result:
            return f"Error querying Tavily via MCP: {result['error']}"
            
        evidence = []
        if isinstance(result, dict):
            if "answer" in result and result["answer"]:
                evidence.append(f"Tavily Answer: {result['answer']}")
                
            for idx, res in enumerate(result.get("results", [])[:5]):
                evidence.append(f"Source {idx + 1}: {res.get('url')}\nContent: {res.get('content')}")
                
        return "\n\n".join(evidence) if evidence else "No evidence found via MCP."
