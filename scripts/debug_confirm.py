"""Quick diagnostic: simulate confirmation flow without audio."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentic.memory.session_state import get_session

# 1. Simulate what the executor does
session = get_session()
session.clear_all()

cid = session.set_pending_action(
    tool="delete_file",
    args={"path": "report.pdf"},
    message="Delete report.pdf?"
)
print(f"[1] Created pending action with ID: {cid}")
print(f"    pending_action = {session.pending_action}")

# 2. Simulate what GET /pending returns
pending = session.get_pending_confirmation()
print(f"\n[2] GET /pending would return: {pending}")

# 3. Simulate what POST /confirm does
from web.confirm_service import handle_confirm
result = handle_confirm(cid, "proceed")
print(f"\n[3] POST /confirm proceed result: {result}")
print(f"    pending_action after proceed: {session.pending_action}")

# 4. Test cancel flow
session.clear_all()
cid2 = session.set_pending_action(
    tool="shutdown_system",
    args={},
    message="Shutdown the system?"
)
result2 = handle_confirm(cid2, "cancel")
print(f"\n[4] POST /confirm cancel result: {result2}")
print(f"    pending_action after cancel: {session.pending_action}")

# 5. Test with tool that has a handler
session.clear_all()
from execution.registry import load_all_tools, get_handler, _REGISTRY
print(f"\n[5] Registered tool handlers: {list(_REGISTRY.keys())}")

# Check which tools in DANGEROUS list actually have handlers
from agentic.permissions import PermissionManager
for tool in PermissionManager.DANGEROUS_TOOLS:
    handler = get_handler(tool)
    print(f"    {tool}: handler={'YES' if handler else 'NO'}")
