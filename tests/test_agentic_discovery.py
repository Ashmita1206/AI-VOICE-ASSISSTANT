"""
Integration & Unit Tests for Agentic Discovery
===============================================
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from agentic.discovery.schemas import Resource
from agentic.discovery.indexer import SystemIndexer, INDEX_PATH
from agentic.discovery.manager import find_best_resource, get_system_context
from agentic.llm.fallback import apply_heuristic_fallback
from execution.registry import get_handler, load_all_tools
load_all_tools()

# 1. Test schemas
def test_resource_schema():
    res = Resource(
        name="ChatGPT",
        type="website",
        source="browser_bookmark",
        url="https://chat.openai.com",
        confidence=0.94
    )
    d = res.to_dict()
    assert d["name"] == "ChatGPT"
    assert d["type"] == "website"
    assert d["source"] == "browser_bookmark"
    assert d["url"] == "https://chat.openai.com"
    assert d["confidence"] == 0.94
    assert "executable" not in d  # Filtered out None values
    
    res2 = Resource.from_dict(d)
    assert res2.name == "ChatGPT"
    assert res2.url == "https://chat.openai.com"

# 2. Test Indexer deduplication and persistence
def test_indexer_scan_and_save():
    indexer = SystemIndexer()
    
    mock_apps = [
        Resource(name="Visual Studio Code", type="application", source="start_menu", executable="code.exe", confidence=0.9),
        Resource(name="VS Code", type="application", source="desktop", executable="code.exe", confidence=0.95),
    ]
    mock_bookmarks = [
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
    ]
    mock_history = [
        Resource(name="chatgpt", type="website", source="browser_history", url="https://chat.openai.com/chat", confidence=0.75),
    ]
    mock_files = [
        Resource(name="MachineLearningProject", type="folder", source="filesystem", path="C:\\Projects\\ML", confidence=0.85)
    ]
    
    with patch("agentic.discovery.indexer.scan_installed_apps", return_value=mock_apps), \
         patch("agentic.discovery.indexer.scan_bookmarks", return_value=mock_bookmarks), \
         patch("agentic.discovery.indexer.scan_history", return_value=mock_history), \
         patch("agentic.discovery.indexer.scan_home_directories", return_value=[]), \
         patch("agentic.discovery.indexer.search_recent_files", return_value=mock_files), \
         patch("agentic.discovery.indexer.search_recent_folders", return_value=[]), \
         patch("agentic.discovery.indexer.scan_running_processes", return_value=[]):
        
        indexer.scan_and_save()
        
        # Verify resources got populated & deduped
        # VS Code and Visual Studio Code are treated as separate named items here since we dedupe by exact name+type
        # But ChatGPT should be deduped: bookmark (0.9) vs history (0.75) -> bookmark wins.
        assert len(indexer.resources) > 0
        names = [r.name.lower() for r in indexer.resources]
        assert "vs code" in names
        assert "visual studio code" in names
        
        # Check ChatGPT is deduped
        chatgpts = [r for r in indexer.resources if r.name.lower() == "chatgpt"]
        assert len(chatgpts) == 1
        assert chatgpts[0].confidence == 0.9
        
        # Ensure it is persisted to disk
        assert os.path.exists(INDEX_PATH)
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == len(indexer.resources)

# 3. Test Fuzzy Search matching
def test_fuzzy_search_engine():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="Visual Studio Code", type="application", source="start_menu", executable="code.exe", confidence=0.9),
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
        Resource(name="MachineLearningProject", type="folder", source="filesystem", path="C:\\Projects\\ML", confidence=0.8)
    ]
    
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer):
        # Test exact match
        res = find_best_resource("ChatGPT")
        assert res is not None
        assert res.name == "ChatGPT"
        
        # Test fuzzy match
        res_fuzzy = find_best_resource("vs code")
        assert res_fuzzy is not None
        assert res_fuzzy.name == "Visual Studio Code"
        
        # Test lowercase / substring match
        res_folder = find_best_resource("machine learning")
        assert res_folder is not None
        assert res_folder.name == "MachineLearningProject"
        
        # Test no match
        res_none = find_best_resource("xyz123abc")
        assert res_none is None

# 4. Test Local Heuristic Fallback with discovery integration
def test_fallback_with_discovery():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
        Resource(name="Visual Studio Code", type="application", source="start_menu", executable="code.exe", confidence=0.9)
    ]
    
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer):
        # Fallback query "open chatgpt"
        plan = apply_heuristic_fallback("open chatgpt")
        assert plan.intent == "open_resource"
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "open_browser"
        assert plan.steps[0].args["url"] == "https://chat.openai.com"
        
        # Fallback query "launch vs code"
        plan_app = apply_heuristic_fallback("launch vs code")
        assert plan_app.intent == "open_resource"
        assert len(plan_app.steps) == 1
        assert plan_app.steps[0].tool == "open_application"
        assert plan_app.steps[0].args["application"] == "Visual Studio Code"

# 5. Test Registry and handlers are loaded
def test_executor_handlers_registered():
    assert get_handler("open_folder") is not None
    assert get_handler("open_file") is not None
    assert get_handler("open_browser") is not None
    assert get_handler("open_application") is not None

# 6. Test Enhanced Ranking Engine
from agentic.discovery.manager import resolve_best_resource

def test_ranking_app_and_website_both_exist():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="application", source="start_menu", executable="chatgpt.exe", confidence=0.9),
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
    ]
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer), \
         patch("agentic.discovery.manager.load_user_preferences", return_value={}):
         
        best = resolve_best_resource("ChatGPT", "Open ChatGPT")
        assert best is not None
        assert best.type == "application"
        assert best.executable == "chatgpt.exe"

def test_ranking_only_website_exists():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
    ]
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer), \
         patch("agentic.discovery.manager.load_user_preferences", return_value={}):
         
        best = resolve_best_resource("ChatGPT", "Open ChatGPT")
        assert best is not None
        assert best.type == "website"
        assert best.url == "https://chat.openai.com"

def test_ranking_app_already_running():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="application", source="start_menu", executable="chatgpt.exe", confidence=0.9, is_running=True),
        Resource(name="ChatGPT", type="application", source="desktop", executable="chatgpt_other.exe", confidence=0.9, is_running=False),
    ]
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer), \
         patch("agentic.discovery.manager.load_user_preferences", return_value={}):
         
        best = resolve_best_resource("ChatGPT", "Open ChatGPT")
        assert best is not None
        assert best.is_running is True
        assert best.executable == "chatgpt.exe"

def test_ranking_preference_overrides():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="application", source="start_menu", executable="chatgpt.exe", confidence=0.9),
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
        Resource(name="WhatsApp", type="application", source="start_menu", executable="whatsapp.exe", confidence=0.9),
        Resource(name="WhatsApp", type="website", source="browser_bookmark", url="https://web.whatsapp.com", confidence=0.9),
    ]
    
    mock_prefs = {
        "ChatGPT": {"preferred_type": "application"},
        "WhatsApp": {"preferred_type": "website"}
    }
    
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer), \
         patch("agentic.discovery.manager.load_user_preferences", return_value=mock_prefs):
         
        best_chat = resolve_best_resource("ChatGPT", "Open ChatGPT")
        assert best_chat.type == "application"
        
        best_wa = resolve_best_resource("WhatsApp", "Open WhatsApp")
        assert best_wa.type == "website"

def test_ranking_intent_modifiers():
    indexer = SystemIndexer()
    indexer.resources = [
        Resource(name="ChatGPT", type="application", source="start_menu", executable="chatgpt.exe", confidence=0.9),
        Resource(name="ChatGPT", type="website", source="browser_bookmark", url="https://chat.openai.com", confidence=0.9),
    ]
    
    with patch("agentic.discovery.manager.get_indexer", return_value=indexer), \
         patch("agentic.discovery.manager.load_user_preferences", return_value={}):
         
        # 1. "Open ChatGPT website" -> force website
        best_web = resolve_best_resource("ChatGPT", "Open ChatGPT website")
        assert best_web.type == "website"
        
        # 2. "Open ChatGPT app" -> force application
        best_app = resolve_best_resource("ChatGPT", "Open ChatGPT app")
        assert best_app.type == "application"
        
        # 3. "Search ChatGPT" -> perform web search only
        best_search = resolve_best_resource("ChatGPT", "Search ChatGPT")
        assert best_search.source == "web_search_fallback"
        assert "google.com" in best_search.url
