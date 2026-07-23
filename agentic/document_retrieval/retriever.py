"""
Document Retrieval Query Rewriter & Entity Parser
==================================================

Expands vague user queries, normalizes stop words, and extracts entity targets.
"""

import re
from typing import Set, List
from dataclasses import dataclass, field

EXPANSIONS = {
    "cdot": ["CDOT", "telecom", "proposal", "bharatnet", "communication"],
    "healthsphere": ["HealthSphere", "healthcare", "medical", "hospital", "AI healthcare", "project"],
    "health sphere": ["HealthSphere", "healthcare", "medical", "hospital", "project"],
    "voltguard": ["VoltGuard", "battery", "energy", "power", "monitoring"],
    "battery": ["VoltGuard", "battery", "energy", "power", "report"],
    "datascience": ["DataScience", "data science", "machine learning", "python", "notes"],
    "data science": ["DataScience", "data science", "machine learning", "python", "notes"],
}

STOP_WORDS = frozenset({
    "open", "search", "find", "document", "file", "explorer", "please", "show",
    "look", "for", "get", "bring", "up", "locate", "my", "old", "recent", "the",
    "a", "an", "i", "need", "want", "to", "see", "view", "display", "fetch"
})

INTENT_EXTENSIONS = {
    "presentation": {"ppt", "pptx"},
    "slide": {"ppt", "pptx"},
    "slides": {"ppt", "pptx"},
    "powerpoint": {"ppt", "pptx"},
    "pdf": {"pdf"},
    "report": {"pdf", "docx", "doc"},
    "word": {"docx", "doc"},
    "excel": {"xlsx", "xls", "csv"},
    "sheet": {"xlsx", "xls", "csv"},
    "spreadsheet": {"xlsx", "xls", "csv"},
    "code": {"py", "ipynb", "cpp", "java", "js", "ts"},
    "script": {"py", "js", "ts", "bat", "ps1"},
    "notebook": {"ipynb"},
    "python": {"py", "ipynb"},
}

ACTION_VERBS = frozenset({
    "open", "search", "find", "show", "look", "get", "bring", "locate", "view", "display", "fetch"
})

TYPE_KEYWORDS = {
    "presentation": "presentation",
    "slides": "presentation",
    "slide": "presentation",
    "powerpoint": "presentation",
    "report": "document",
    "document": "document",
    "doc": "document",
    "pdf": "pdf",
    "notes": "document",
    "spreadsheet": "spreadsheet",
    "excel": "spreadsheet",
    "sheet": "spreadsheet",
    "csv": "spreadsheet",
    "code": "code",
    "script": "code",
    "notebook": "code",
    "python": "code"
}

@dataclass
class ParsedQuery:
    raw_query: str
    normalized_query: str
    target_filename_tokens: List[str] = field(default_factory=list)
    folder_candidates: List[str] = field(default_factory=list)
    preferred_extensions: Set[str] = field(default_factory=set)
    intent: str = "search"  # open | search | find
    doc_type: str = ""      # document | presentation | spreadsheet | code | pdf

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b[a-z0-9]+\b", text.lower())

def normalize_folder_name(name: str) -> str:
    """Normalize folder names into alphanumeric key for uniform matching (money mentor -> moneymentor)."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())

GENERIC_CONTAINER_WORDS = frozenset({
    "documents", "desktop", "downloads", "document", "file", "files", "folder", "folders", "explorer", "my"
})

def extract_folder_candidates(query: str) -> List[str]:
    """Extract probable project/folder name candidates from query (e.g. 'Money Mentor', 'moneymentor')."""
    if not query:
        return []
    words = _tokenize(query)
    meaningful = [
        w for w in words
        if w not in STOP_WORDS and w not in ACTION_VERBS and w not in TYPE_KEYWORDS and w not in GENERIC_CONTAINER_WORDS
    ]
    if not meaningful:
        return []

    candidates = []
    # 1. Full joined meaningful words phrase
    full_phrase = " ".join(meaningful)
    candidates.append(full_phrase)
    candidates.append(normalize_folder_name(full_phrase))
    
    # 2. Bigrams and unigrams
    for i in range(len(meaningful)):
        m_word = meaningful[i]
        if m_word not in GENERIC_CONTAINER_WORDS:
            candidates.append(m_word)
            candidates.append(normalize_folder_name(m_word))
        if i + 1 < len(meaningful):
            bigram = f"{meaningful[i]} {meaningful[i+1]}"
            candidates.append(bigram)
            candidates.append(normalize_folder_name(bigram))
            
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        norm_c = normalize_folder_name(c)
        if c and norm_c and norm_c not in GENERIC_CONTAINER_WORDS and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique

def normalize_query(query: str) -> str:
    """Normalize query into core search terms by stripping action/filler words."""
    if not query:
        return ""
    words = _tokenize(query)
    meaningful = [w for w in words if w not in STOP_WORDS]
    return " ".join(meaningful) if meaningful else query.lower().strip()

def extract_extension_preference(query: str) -> Set[str]:
    """Extract target file extensions based on user query intent."""
    query_lower = query.lower()
    preferred: Set[str] = set()
    for kw, exts in INTENT_EXTENSIONS.items():
        if kw in query_lower:
            preferred.update(exts)
    return preferred

def rewrite_query(query: str) -> str:
    """Expand a short query into a richer search string."""
    if not query:
        return ""
        
    normalized = normalize_query(query)
    query_lower = normalized.lower()
    expanded_terms: Set[str] = set()
    
    for key, terms in EXPANSIONS.items():
        if key in query_lower:
            expanded_terms.update(terms)
            
    words = _tokenize(query_lower)
    for word in words:
        if word in EXPANSIONS:
            expanded_terms.update(EXPANSIONS[word])
            
    if not expanded_terms:
        return normalized
        
    expansions_str = " ".join(expanded_terms)
    return f"{normalized} {expansions_str}".strip()

def parse_query(raw_query: str) -> ParsedQuery:
    """Parse entities, target filename tokens, intent, folder candidates, and extension preference from query."""
    if not raw_query:
        return ParsedQuery(raw_query="", normalized_query="")
        
    query_lower = raw_query.lower().strip()
    words = _tokenize(query_lower)
    
    intent = "search"
    for w in words:
        if w in ACTION_VERBS:
            intent = w
            break
            
    doc_type = ""
    for w in words:
        if w in TYPE_KEYWORDS:
            doc_type = TYPE_KEYWORDS[w]
            break
            
    normalized = normalize_query(raw_query)
    target_tokens = [w for w in words if w not in STOP_WORDS and w not in TYPE_KEYWORDS]
    if not target_tokens:
        target_tokens = _tokenize(normalized)
        
    preferred_exts = extract_extension_preference(raw_query)
    folder_candidates = extract_folder_candidates(raw_query)
    
    return ParsedQuery(
        raw_query=raw_query,
        normalized_query=normalized,
        target_filename_tokens=target_tokens,
        folder_candidates=folder_candidates,
        preferred_extensions=preferred_exts,
        intent=intent,
        doc_type=doc_type
    )
