import pytest
from automation.applications import (
    resolve_canonical_app,
    resolve_app_launch_strategy,
    is_fuzzy_match,
    clean_query_for_matching
)

def test_resolve_canonical_app_file_explorer():
    assert resolve_canonical_app("open file manager") == "file explorer"
    assert resolve_canonical_app("open explorer") == "file explorer"
    assert resolve_canonical_app("open this pc") == "file explorer"
    assert resolve_canonical_app("launch file manager") == "file explorer"

def test_resolve_canonical_app_task_manager():
    assert resolve_canonical_app("open task manager") == "task manager"
    assert resolve_canonical_app("open system monitor") == "task manager"
    assert resolve_canonical_app("open taskmgr") == "task manager"

def test_resolve_app_launch_strategy_builtins():
    # File Manager -> explorer.exe
    exe, _, _, _ = resolve_app_launch_strategy("open file manager")
    assert exe == "explorer.exe"

    # Task Manager -> taskmgr.exe
    exe, _, _, _ = resolve_app_launch_strategy("open task manager")
    assert exe == "taskmgr.exe"
    
    # Command prompt -> cmd.exe
    exe, _, _, _ = resolve_app_launch_strategy("open command prompt")
    assert exe == "cmd.exe"
    
    # Settings -> ms-settings:
    exe, _, _, _ = resolve_app_launch_strategy("open settings")
    assert exe == "ms-settings:"

def test_fuzzy_match_threshold_rejection():
    # "file manager" shouldn't match "task manager" because ratio is < 0.85
    # (previously ratio was 0.833 > 0.6)
    assert not is_fuzzy_match("file manager", "task manager")
    
    # "task manager" should match "task manager"
    assert is_fuzzy_match("task manager", "task manager")

def test_file_manager_never_maps_to_task_manager():
    query = "open file manager"
    canonical = resolve_canonical_app(query)
    assert canonical == "file explorer"
    assert canonical != "task manager"
    
    # If the system only has "task manager" running/installed, we shouldn't match it
    cleaned = clean_query_for_matching(query)
    # the search_query will become "file explorer"
    search_query = canonical or cleaned
    assert not is_fuzzy_match(search_query, "task manager")
