import httpx
from typing import Dict, Any, List
import asyncio
from app.core.config import settings
from fastmcp import FastMCP

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
    def get_version_evidence(cls, application_name: str, current_version: str = "", installation_method: str = "", os_name: str = "", architecture: str = "") -> str:
        """
        Uses Tavily (via FastMCP) to search for the current latest version of an application.
        Returns the raw results string for the LLM to interpret.
        """
        query = f"What is the current latest stable release version of {application_name}"
        if os_name and os_name.lower() != "unknown":
            query += f" compatible with {os_name}"
            if architecture and architecture.lower() != "unknown":
                query += f" ({architecture} architecture)"
        query += "? "
        
        if current_version:
            query += f"The current installed version is {current_version}. "
        if installation_method:
            query += f"The detected installation method is {installation_method}. "
        query += "(Provide official sources, GitHub releases, or Wikipedia)"
        
        result = search_tavily(query, search_depth="advanced")

        if isinstance(result, dict) and "error" in result:
            return f"Error querying Tavily via MCP: {result['error']}"
            
        evidence = []
        if isinstance(result, dict):
            if "answer" in result and result["answer"]:
                evidence.append(f"Tavily Answer: {result['answer']}")
                
            for idx, res in enumerate(result.get("results", [])[:5]):
                evidence.append(f"Source {idx + 1}: {res.get('url')}\nContent: {res.get('content')}")
                
        return "\n\n".join(evidence) if evidence else "No evidence found via MCP."

    @classmethod
    def get_installation_evidence(cls, application_name: str, os_name: str) -> str:
        """
        Uses Tavily to search for the official installation commands and repository setup 
        for a specific application on a specific OS.
        """
        query = f"official installation guide terminal commands repository setup for {application_name} compatible with {os_name} linux"
        
        result = search_tavily(query, search_depth="advanced")

        if isinstance(result, dict) and "error" in result:
            return f"Error querying Tavily via MCP: {result['error']}"
            
        evidence = []
        if isinstance(result, dict):
            if "answer" in result and result["answer"]:
                evidence.append(f"Tavily Answer: {result['answer']}")
                
            for idx, res in enumerate(result.get("results", [])[:5]):
                evidence.append(f"Source {idx + 1}: {res.get('url')}\nContent: {res.get('content')}")
                
        return "\n\n".join(evidence) if evidence else "No evidence found via MCP."

    @staticmethod
    def _fetch_page_text(url: str, max_chars: int = 4000) -> str:
        if not url or any(k in url.lower() for k in ["youtube.com", "youtu.be", "twitter.com", "x.com"]):
            return ""
        import re
        try:
            with httpx.Client(timeout=6.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                if resp.status_code == 200:
                    text = resp.text
                    clean = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'<style.*?</style>', '', clean, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'<[^>]+>', ' ', clean)
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    return clean[:max_chars]
        except Exception:
            pass
        return ""

    @classmethod
    def get_detailed_installation_evidence(cls, application_name: str, os_name: str, architecture: str, failure_context: str = "", version: str = "") -> str:
        """
        Uses Tavily to search for detailed installation facts specifically tailored for script generation.
        """
        ver_clause = f"{version} " if version and version.lower() not in ("latest", "unknown", "") else ""
        query = f"{application_name} {ver_clause}official installation download package repository documentation {os_name} {architecture}".strip()
        if failure_context:
            query += f" alternative methods {failure_context}"
            
        result = search_tavily(query, search_depth="advanced")

        if isinstance(result, dict) and "error" in result:
            return f"Error querying Tavily via MCP: {result['error']}"
            
        evidence = []
        if isinstance(result, dict):
            if "answer" in result and result["answer"]:
                evidence.append(f"Tavily Answer: {result['answer']}")
                
            for idx, res in enumerate(result.get("results", [])[:5]):
                u = res.get("url", "")
                c = res.get("content", "")
                evidence.append(f"Source {idx + 1}: {u}\nContent: {c}")
                if idx < 3 and any(k in u.lower() for k in ["linux", "install", "download", "docs", "setup", "github.com"]):
                    doc_snippet = cls._fetch_page_text(u, max_chars=3500)
                    if doc_snippet and len(doc_snippet) > len(c):
                        evidence.append(f"Full Documentation Page Extract ({u}):\n{doc_snippet}")
                
        return "\n\n".join(evidence) if evidence else "No evidence found via MCP."
