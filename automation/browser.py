"""
Browser Automation & Search Tools
==================================

Provides tools for opening websites, searching the web, and launching browsers.
"""

import webbrowser
import urllib.parse
from typing import Any

from execution.registry import register_tool
from execution.schemas import ExecutionResult, ExecutionTimer

# Alias mapping for the `webbrowser` module
_BROWSER_ALIASES = {
    "chrome": "google-chrome",
    "firefox": "firefox",
    "edge": "edge",
}

@register_tool("open_browser")
def open_browser(args: dict[str, Any]) -> ExecutionResult:
    """Launch the default web browser and open an optional URL."""
    browser_name = args.get("browser", "").lower()
    url = args.get("url", "")
    
    # If the URL is actually a website query name (e.g. "chatgpt"), resolve it
    if url and not (url.startswith("http://") or url.startswith("https://")):
        from agentic.discovery.manager import resolve_best_resource
        res = resolve_best_resource(url, f"open {url}")
        if res:
            if res.type == "application":
                from automation.applications import open_application
                return open_application({"application": res.name})
            elif res.type == "folder":
                from automation.filesystem import open_folder
                return open_folder({"path": res.path})
            elif res.type == "file":
                from automation.filesystem import open_file
                return open_file({"path": res.path})
            elif res.type == "website" and res.url:
                url = res.url
        else:
            if "." in url:
                url = "https://" + url
            else:
                # Treat as search query if no domain extension is present
                return search_web({"query": url, "application": browser_name})
                
    with ExecutionTimer() as timer:
        try:
            if browser_name and browser_name in _BROWSER_ALIASES:
                webbrowser.get(_BROWSER_ALIASES[browser_name]).open_new_tab(url)
            else:
                webbrowser.open_new_tab(url)
            
            msg = f"Opened browser to {url}." if url else f"Opened browser {browser_name or 'default'}."
            return ExecutionResult(
                success=True,
                tool="open_browser",
                message=msg,
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="open_browser",
                message=f"Failed to open browser: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("open_website")
def open_website(args: dict[str, Any]) -> ExecutionResult:
    """Open a specific URL in the default browser."""
    url = args.get("url", "")
    if not url:
        return ExecutionResult(success=False, tool="open_website", message="No URL provided.")
        
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
        
    with ExecutionTimer() as timer:
        try:
            webbrowser.open(url)
            return ExecutionResult(
                success=True,
                tool="open_website",
                message=f"Opened website: {url}",
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="open_website",
                message=f"Failed to open website: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("search_web")
def search_web(args: dict[str, Any]) -> ExecutionResult:
    """Search the internet for a specific query."""
    query = args.get("query", "")
    if not query:
        return ExecutionResult(
            success=False,
            tool="search_web",
            message="No search query provided."
        )
        
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}"
    
    with ExecutionTimer() as timer:
        try:
            webbrowser.open_new_tab(url)
            return ExecutionResult(
                success=True,
                tool="search_web",
                message=f"Searched web for: {query}",
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="search_web",
                message=f"Failed to perform search: {e}",
                execution_time_ms=timer.elapsed_ms
            )
