"""
Local Heuristic Fallback
========================

Provides rule-based plan generation when the remote LLM is offline.
Maps compound desktop queries to fine-grained sequential steps.
"""

import re
from agentic.llm.schemas import PlannerOutput, PlannerStep

def apply_heuristic_fallback(transcription: str) -> PlannerOutput:
    """Parse transcription with heuristics to generate an offline plan."""
    text = transcription.lower().strip()
    
    from agentic.memory.session_state import get_session
    session = get_session()
    
    # Rule 1: Get active window
    if text in ("get active window", "check active window", "what is the active window", "what app is open", "what app is active"):
        return PlannerOutput(
            intent="check_status",
            confidence=0.9,
            reasoning="Matched active window check.",
            steps=[PlannerStep(tool="get_active_window", args={})]
        )
        
    # Rule 2: Check if app is running
    is_running_match = re.match(r"(?:check\s+if\s+)?(?:is\s+)?(\w+)\s+running", text)
    if is_running_match:
        app = is_running_match.group(1).strip()
        return PlannerOutput(
            intent="check_status",
            confidence=0.9,
            reasoning=f"Matched is app running check for '{app}'.",
            steps=[PlannerStep(tool="is_app_running", args={"app": app})]
        )
        
    # Rule 3: Focus/activate window
    activate_match = re.match(r"(?:focus|activate\s+window|bring\s+to\s+foreground)\s+(.+)", text)
    if activate_match:
        app = activate_match.group(1).strip()
        app = re.sub(r"\s+app$", "", app)
        return PlannerOutput(
            intent="focus_window",
            confidence=0.9,
            reasoning=f"Matched focus window for '{app}'.",
            steps=[PlannerStep(tool="focus_window", args={"target": app})]
        )

    # Rule 4: WhatsApp automation (decomposed)
    whatsapp_match = re.match(r"search\s+(?:for\s+)?(\w+)\s+and\s+write\s+(.+?)(?:\s+on\s+whatsapp)?$", text)
    if not whatsapp_match:
        whatsapp_match = re.match(r"write\s+(.+?)\s+to\s+(\w+)(?:\s+on\s+whatsapp)?$", text)
    if not whatsapp_match:
        whatsapp_match = re.match(r"send\s+(.+?)\s+to\s+(\w+)(?:\s+on\s+whatsapp)?$", text)
        
    whatsapp_robust = False
    contact = None
    message = None
    if whatsapp_match:
        whatsapp_robust = True
        if "and write" in text:
            contact = whatsapp_match.group(1).strip()
            message = whatsapp_match.group(2).strip()
        else:
            message = whatsapp_match.group(1).strip()
            contact = whatsapp_match.group(2).strip()
    elif "whatsapp" in text:
        if any(word in text for word in ("send", "write", "message", "msg", "text")):
            whatsapp_robust = True
            to_match = re.search(r"\bto\s+([a-zA-Z0-9_]+)\b", text, re.IGNORECASE)
            if to_match:
                contact = to_match.group(1).strip()
            
            quote_match = re.search(r"['\"](.+?)['\"]", text)
            if quote_match:
                message = quote_match.group(1).strip()
                
            if not message:
                m1 = re.search(r"\b(send|write|message|msg|text)\w*\s+(.+?)\s+to\s+", text, re.IGNORECASE)
                if m1:
                    message = m1.group(2).strip()
                    message = re.sub(r"\b(a|the|some|msg|message)\b", "", message, flags=re.IGNORECASE).strip()
                    
            if not contact:
                m2 = re.search(r"\b(send|write|message|msg|text)\w*\s+([a-zA-Z0-9_]+)\s+(.+)$", text, re.IGNORECASE)
                if m2:
                    contact = m2.group(2).strip()
                    message = m2.group(3).strip()

    if whatsapp_robust:
        contact = contact or "Harshita"
        message = message or "Hi!"
        contact = re.sub(r"[.!?]+$", "", contact).strip()
        message = re.sub(r"[.!?]+$", "", message).strip()
        contact = contact.capitalize()
        
        return PlannerOutput(
            intent="send_whatsapp",
            confidence=0.9,
            reasoning=f"Matched WhatsApp messaging flow for '{contact}'.",
            steps=[
                PlannerStep(tool="launch_application", args={"application": "WhatsApp"}, wait_for="ui_ready", timeout=60),
                PlannerStep(tool="search_inside_application", args={"query": contact}),
                PlannerStep(tool="press_key", args={"key": "enter"}),
                PlannerStep(tool="type_text", args={"text": message}),
                PlannerStep(tool="press_key", args={"key": "enter"})
            ]
        )

    # Rule 5: Spotify automation (play/pause/resume)
    spotify_play_pattern = r"^(?:open\s+spotify\s+and\s+play|spotify\s+play|listen\s+to|play\s+song|play\s+music|play)\s+(.+)"
    spotify_play_match = re.match(spotify_play_pattern, text)
    if spotify_play_match:
        song = spotify_play_match.group(1).strip()
        song = re.sub(r"\b(on|in)\s+spotify$", "", song, flags=re.IGNORECASE).strip()
        song = re.sub(r"[.!?]+$", "", song).strip()
        
        return PlannerOutput(
            intent="play_music",
            confidence=0.9,
            reasoning=f"Matched Spotify play for song: '{song}'.",
            steps=[
                PlannerStep(tool="launch_application", args={"application": "Spotify"}, wait_for="ui_ready", timeout=60),
                PlannerStep(tool="search_inside_application", args={"query": song}),
                PlannerStep(tool="press_key", args={"key": "enter"}),
                PlannerStep(tool="press_key", args={"key": "enter"})
            ]
        )
            
    if text in ("pause", "pause it", "pause spotify", "pause music", "stop music", "pause song", "resume", "resume play", "play", "play music", "play song"):
        return PlannerOutput(
            intent="pause_music" if text in ("pause", "pause it", "pause spotify", "pause music", "stop music", "pause song") else "play_music",
            confidence=0.9,
            reasoning="Matched Spotify playback control.",
            steps=[
                PlannerStep(tool="launch_application", args={"application": "Spotify"}),
                PlannerStep(tool="press_key", args={"key": "playpause"})
            ]
        )

    # Intercept any other Spotify command before falling back to resolve_and_open
    if "spotify" in text:
        return PlannerOutput(
            intent="open_resource",
            confidence=0.9,
            reasoning="Matched Spotify application launch.",
            steps=[
                PlannerStep(tool="launch_application", args={"application": "Spotify"}, wait_for="ui_ready", timeout=60)
            ]
        )

    # Rule 6: Open browser and search
    if "open" in text and "browser" in text and "search" in text:
        query_match = re.search(r"search\s+(.*)", text)
        query = query_match.group(1).strip() if query_match else ""
        query = re.sub(r"[.!?]+$", "", query).strip()

        return PlannerOutput(
            intent="search_web",
            confidence=0.8,
            reasoning="Matched browser search.",
            steps=[
                PlannerStep(tool="launch_application", args={"application": "chrome"}, wait_for="ui_ready", timeout=60),
                PlannerStep(tool="search_inside_application", args={"query": query})
            ]
        )

    # Rule 7: Open/launch resource dynamically (e.g. "open chatgpt", "launch vs code")
    match = re.match(r"(?:open|launch|run|start|go\s+to)\s+(.+)", text)
    if match:
        query = match.group(1).strip()
        query = re.sub(r"[.!?]+$", "", query).strip()
        
        from agentic.discovery.manager import find_best_resource
        res = find_best_resource(query)
        if res:
            if res.type == "website":
                return PlannerOutput(
                    intent="open_resource",
                    confidence=res.confidence,
                    reasoning=f"Fallback matched '{query}' to website: {res.name}",
                    steps=[PlannerStep(tool="open_browser", args={"url": res.url})]
                )
            elif res.type == "application":
                return PlannerOutput(
                    intent="open_resource",
                    confidence=res.confidence,
                    reasoning=f"Fallback matched '{query}' to application: {res.name}",
                    steps=[PlannerStep(tool="open_application", args={"application": res.name})]
                )
            elif res.type == "folder":
                return PlannerOutput(
                    intent="open_resource",
                    confidence=res.confidence,
                    reasoning=f"Fallback matched '{query}' to folder: {res.name}",
                    steps=[PlannerStep(tool="open_folder", args={"path": res.path})]
                )
            elif res.type == "file":
                return PlannerOutput(
                    intent="open_resource",
                    confidence=res.confidence,
                    reasoning=f"Fallback matched '{query}' to file: {res.name}",
                    steps=[PlannerStep(tool="open_file", args={"path": res.path})]
                )

    # If no rules match, return standard safe fallback resolve_and_open
    return PlannerOutput.fallback("Could not parse offline plan.", query=transcription)
