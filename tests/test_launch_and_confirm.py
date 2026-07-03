import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentic.memory.pending_action import PendingActionManager
from agentic.memory.session_state import get_session
from web.confirm_service import handle_confirm
from automation.applications import resolve_and_open, resolve_app_launch_strategy
from agentic.llm.fallback import apply_heuristic_fallback
from agentic.llm.schemas import PlannerOutput

@pytest.fixture(autouse=True)
def cleanup():
    PendingActionManager.clear()
    get_session().clear_all()
    yield
    PendingActionManager.clear()
    get_session().clear_all()

def test_proceed_button_resumes_pending_action():
    # Save a pending action plan
    plan_dict = {
        "intent": "delete_file",
        "steps": [
            {"tool": "open_terminal", "args": {}}
        ]
    }
    
    cid = PendingActionManager.save(plan_dict)
    get_session().set_pending_action("open_terminal", {}, "Open terminal?")
    get_session().pending_action["id"] = cid
    
    # Mock the tool registry get_handler/handler execution
    with patch("web.confirm_service.get_handler") as mock_get_handler:
        mock_handler = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True
        mock_res.to_dict.return_value = {"success": True, "tool": "open_terminal", "message": "Dummy success"}
        mock_handler.return_value = mock_res
        mock_get_handler.return_value = mock_handler
        
        res = handle_confirm(cid, "proceed")
        
        assert res["success"] is True
        assert PendingActionManager.get_pending_action() is None
        assert get_session().pending_action is None

def test_cancel_clears_state():
    plan_dict = {
        "intent": "delete_file",
        "steps": [
            {"tool": "open_terminal", "args": {}}
        ]
    }
    cid = PendingActionManager.save(plan_dict)
    get_session().set_pending_action("open_terminal", {}, "Open terminal?")
    get_session().pending_action["id"] = cid
    
    res = handle_confirm(cid, "cancel")
    assert res["success"] is True
    assert "cancelled" in res["message"].lower()
    assert PendingActionManager.get_pending_action() is None
    assert get_session().pending_action is None

@patch("psutil.process_iter")
@patch("automation.applications.bring_process_to_foreground")
def test_running_app_found(mock_bring_fg, mock_process_iter):
    # Mock a running process
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 1234, "name": "Spotify.exe", "exe": "C:\\path\\Spotify.exe"}
    mock_process_iter.return_value = [mock_proc]
    
    res = resolve_and_open({"query": "Open Spotify app"})
    
    # Assertions
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    assert "launched" in res.to_dict()["reason"].lower()
    mock_bring_fg.assert_called_once_with(1234)

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.subprocess.Popen")
def test_microsoft_store_app_found(mock_popen, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    # Simulate Get-StartApps finding Spotify UWP app
    mock_get_start.return_value = [{"name": "Spotify", "appid": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"}]
    
    res = resolve_and_open({"query": "open spotify"})
    
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    assert "launched" in res.to_dict()["reason"].lower()
    mock_popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"])

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.find_indexed_app")
@patch("automation.applications.os.startfile", create=True)
def test_installed_app_found(mock_startfile, mock_find_idx, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = []
    # Registry/Shortcut match
    mock_find_idx.return_value = ("Spotify", "C:\\Program Files\\Spotify\\Spotify.exe")
    
    res = resolve_and_open({"query": "Spotify app"})
    
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    mock_startfile.assert_called_once_with("C:\\Program Files\\Spotify\\Spotify.exe")

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.find_indexed_app")
@patch("automation.applications.find_website_resource")
@patch("webbrowser.open_new_tab")
def test_website_only_resource(mock_open_tab, mock_find_web, mock_find_idx, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = []
    mock_find_idx.return_value = (None, None)
    
    mock_web = MagicMock()
    mock_web.name = "Spotify Web"
    mock_web.url = "https://open.spotify.com"
    mock_find_web.return_value = mock_web
    
    res = resolve_and_open({"query": "open spotify"})
    
    assert res.success is True
    assert res.to_dict()["resource_type"] == "website"
    assert "opened" in res.to_dict()["reason"].lower()
    mock_open_tab.assert_called_once_with("https://open.spotify.com")

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.find_indexed_app")
@patch("automation.applications.find_website_resource")
@patch("webbrowser.open_new_tab")
def test_nothing_found_google_fallback(mock_open_tab, mock_find_web, mock_find_idx, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = []
    mock_find_idx.return_value = (None, None)
    mock_find_web.return_value = None
    
    res = resolve_and_open({"query": "open nonexistentapp"})
    
    assert res.success is True
    assert res.to_dict()["resource_type"] == "website"
    assert "google search" in res.to_dict()["reason"].lower()
    mock_open_tab.assert_called_once_with("https://www.google.com/search?q=nonexistentapp")

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.subprocess.Popen")
def test_open_spotify_app(mock_popen, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = [{"name": "Spotify", "appid": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"}]
    
    res = resolve_and_open({"query": "Open the Spotify app"})
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    mock_popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"])

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.subprocess.Popen")
def test_open_chatgpt(mock_popen, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = [{"name": "ChatGPT", "appid": "ChatGPT_appid"}]
    
    res = resolve_and_open({"query": "Open ChatGPT"})
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    mock_popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\ChatGPT_appid"])

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.subprocess.Popen")
def test_open_vs_code(mock_popen, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = [{"name": "Visual Studio Code", "appid": "VSCode_appid"}]
    
    res = resolve_and_open({"query": "Launch VS Code"})
    assert res.success is True
    assert res.to_dict()["resource_type"] == "application"
    mock_popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\VSCode_appid"])

@patch("psutil.process_iter")
@patch("automation.applications.get_start_apps")
@patch("automation.applications.find_indexed_app")
@patch("automation.applications.find_website_resource")
@patch("webbrowser.open_new_tab")
def test_open_nonexistent_app(mock_open_tab, mock_find_web, mock_find_idx, mock_get_start, mock_process_iter):
    mock_process_iter.return_value = []
    mock_get_start.return_value = []
    mock_find_idx.return_value = (None, None)
    mock_find_web.return_value = None
    
    res = resolve_and_open({"query": "nonexistent app"})
    assert res.success is True
    assert res.to_dict()["resource_type"] == "website"
    assert "google search" in res.to_dict()["reason"].lower()
    mock_open_tab.assert_called_once_with("https://www.google.com/search?q=nonexistent")

def test_planner_never_returns_unknown():
    # 1. Test fallback.py apply_heuristic_fallback
    res_heuristic = apply_heuristic_fallback("garbage command structure")
    assert res_heuristic.intent == "open_resource"
    assert len(res_heuristic.steps) == 1
    assert res_heuristic.steps[0].tool == "resolve_and_open"
    assert res_heuristic.steps[0].args.get("query") == "garbage command structure"
    
    # 2. Test PlannerOutput.fallback
    res_schema = PlannerOutput.fallback("Failed parsing", "some user cmd")
    assert res_schema.intent == "open_resource"
    assert len(res_schema.steps) == 1
    assert res_schema.steps[0].tool == "resolve_and_open"
    assert res_schema.steps[0].args.get("query") == "some user cmd"

from automation.applications import is_app_running, activate_window, get_active_window, perform_app_action

@patch("psutil.process_iter")
def test_is_app_running_tool(mock_process_iter):
    mock_proc = MagicMock()
    mock_proc.info = {"name": "Spotify.exe"}
    mock_process_iter.return_value = [mock_proc]
    
    res = is_app_running({"app": "spotify"})
    assert res.success is True
    assert res.to_dict()["app_running"] is True
    
    res_not_running = is_app_running({"app": "notepad"})
    assert res_not_running.success is True
    assert res_not_running.to_dict()["app_running"] is False

@patch("psutil.process_iter")
@patch("automation.applications.bring_process_to_foreground")
def test_activate_window_tool(mock_bring_fg, mock_process_iter):
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 9999, "name": "Spotify.exe"}
    mock_process_iter.return_value = [mock_proc]
    mock_bring_fg.return_value = True
    
    res = activate_window({"app": "spotify"})
    assert res.success is True
    assert res.to_dict()["app_running"] is True
    assert res.to_dict()["action"] == "activate_window"
    mock_bring_fg.assert_called_once_with(9999)

@patch("agentic.memory.app_context.get_active_window_info")
def test_get_active_window_tool(mock_get_info):
    mock_get_info.return_value = {
        "active_app": "Spotify",
        "window_handle": "123456",
        "window_title": "Spotify Premium"
    }
    
    res = get_active_window({})
    assert res.success is True
    assert res.to_dict()["active_app"] == "Spotify"
    assert res.to_dict()["window_handle"] == "123456"
    assert res.to_dict()["window_title"] == "Spotify Premium"

@patch("psutil.process_iter")
@patch("automation.applications.bring_process_to_foreground")
@patch("win32com.client.Dispatch")
def test_perform_app_action_spotify_play(mock_dispatch, mock_bring_fg, mock_process_iter):
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 9999, "name": "Spotify.exe"}
    mock_process_iter.return_value = [mock_proc]
    
    mock_shell = MagicMock()
    mock_dispatch.return_value = mock_shell
    
    res = perform_app_action({
        "app": "spotify",
        "action": "play",
        "payload": {"song": "Darkhaast"}
    })
    
    assert res.success is True
    assert "Darkhaast" in res.message
    mock_shell.SendKeys.assert_any_call("Darkhaast")
    
    session = get_session()
    assert session.last_song == "Darkhaast"
    assert session.last_active_app == "spotify"

@patch("psutil.process_iter")
@patch("automation.applications.bring_process_to_foreground")
@patch("automation.whatsapp.send_whatsapp_message")
def test_perform_app_action_whatsapp_send(mock_send, mock_bring_fg, mock_process_iter):
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 8888, "name": "WhatsApp.exe"}
    mock_process_iter.return_value = [mock_proc]
    
    from execution.schemas import ExecutionResult
    mock_send.return_value = ExecutionResult(success=True, message="Sent")
    
    res = perform_app_action({
        "app": "whatsapp",
        "action": "send_message",
        "payload": {"contact": "Harshita", "message": "hi"}
    })
    
    assert res.success is True
    mock_send.assert_called_once_with({"contact": "Harshita", "message": "hi"})
    
    session = get_session()
    assert session.last_contact == "Harshita"
    assert session.last_active_app == "whatsapp"

def test_heuristic_fallback_stateful_commands():
    session = get_session()
    session.clear_all()
    session.set_context(app="spotify")
    
    res_play = apply_heuristic_fallback("Play Darkhaast")
    assert res_play.intent == "play_music"
    assert res_play.steps[0].tool == "focus_window"
    assert res_play.steps[1].tool == "search_inside_application"
    assert res_play.steps[1].args["query"] == "darkhaast"
    
    res_pause = apply_heuristic_fallback("Pause it")
    assert res_pause.intent == "pause_music"
    assert res_pause.steps[0].tool == "focus_window"
    assert res_pause.steps[1].tool == "press_key"
    assert res_pause.steps[1].args["key"] == "playpause"
    
    session.set_context(app="whatsapp")
    res_wa = apply_heuristic_fallback("Search Harshita and write hi on WhatsApp")
    assert res_wa.intent == "send_whatsapp"
    assert len(res_wa.steps) == 4
    assert res_wa.steps[0].tool == "focus_window"
    assert res_wa.steps[1].tool == "search_inside_application"
    assert res_wa.steps[2].tool == "type_text"
    assert res_wa.steps[3].tool == "press_key"
    assert res_wa.steps[1].args["query"] == "Harshita"
    assert res_wa.steps[2].args["text"] == "hi"

@patch("psutil.process_iter")
@patch("automation.applications.bring_process_to_foreground")
def test_open_application_does_not_relaunch(mock_bring_fg, mock_process_iter):
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 9999, "name": "Spotify.exe"}
    mock_process_iter.return_value = [mock_proc]
    mock_bring_fg.return_value = True
    
    from automation.applications import open_application
    res = open_application({"application": "spotify"})
    
    assert res.success is True
    assert res.to_dict()["app_running"] is True
    assert res.to_dict()["action"] == "activate_window"
    mock_bring_fg.assert_called_once_with(9999)
