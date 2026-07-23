"""
Document Retrieval Entities
===========================

Enhanced entity extraction using heuristics and curated dictionaries.
"""

import json
import re
from typing import Dict, List

# Curated dictionary of known entities relevant to the user/project
KNOWN_ENTITIES = {
    "Companies": {"OpenAI", "Microsoft", "Google", "Apple", "Meta", "Amazon", "Flipkart", "Tata", "Reliance", "Infosys", "Wipro", "TCS"},
    "Projects": {"CDOT", "HealthSphere", "VoltGuard", "BharatNet", "Project"},
    "Technologies": {"TensorFlow", "PyTorch", "Whisper", "FastAPI", "React", "Angular", "Vue", "Python", "Java", "C++", "JavaScript", "TypeScript", "SQL", "HTML", "CSS"},
    "Locations": {"India", "USA", "UK", "London", "Delhi", "Mumbai", "Bangalore", "Pune", "Hyderabad", "Chennai"},
}

def extract_entities(text: str) -> str:
    """Extract Entities from text and return as JSON string."""
    if not text:
        return "{}"
        
    entities: Dict[str, List[str]] = {
        "Organizations": [],
        "Projects": [],
        "Technologies": [],
        "Companies": [],
        "Locations": [],
        "People": [],
        "Products": [],
    }
    
    # 1. Match against known entities
    text_lower = text.lower()
    found_known = set()
    for category, items in KNOWN_ENTITIES.items():
        for item in items:
            if item.lower() in text_lower:
                # Basic exact word boundary check
                if re.search(rf"\b{re.escape(item.lower())}\b", text_lower):
                    entities[category].append(item)
                    found_known.add(item.lower())
    
    # 2. Capitalized words heuristic
    words = re.findall(r'\b[A-Z][a-z0-9A-Z]+\b', text)
    unique_words = list(set(words))
    
    for w in unique_words:
        if len(w) < 3 or w.lower() in found_known:
            continue
            
        # Put other capitalized nouns in Organizations tentatively (max 5)
        if len(entities["Organizations"]) < 5:
            entities["Organizations"].append(w)
            
    # Remove empty lists and deduplicate
    clean_entities = {}
    for k, v in entities.items():
        if v:
            clean_entities[k] = list(set(v))
            
    return json.dumps(clean_entities)
