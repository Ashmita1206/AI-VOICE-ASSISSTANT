import re
import json

def extract_entities(text: str) -> str:
    """Extract Entities like Organizations, Projects, Technologies from text.
    
    Returns a JSON string of a dictionary mapping entity types to lists of strings.
    """
    if not text:
        return "{}"
        
    entities = {
        "Organizations": [],
        "Projects": [],
        "Technologies": [],
        "Companies": [],
        "Locations": [],
    }
    
    # Very simple heuristic: capitalized words that appear together
    words = re.findall(r'\b[A-Z][a-z0-9A-Z]*\b', text)
    unique_words = list(set(words))
    
    for w in unique_words:
        if len(w) < 3:
            continue
            
        # Basic bucket logic (could be improved with LLM/NLP)
        if w in ["Google", "Microsoft", "Flipkart", "Apple", "Meta", "Amazon"]:
            entities["Companies"].append(w)
        elif w in ["TensorFlow", "PyTorch", "React", "Angular", "Vue", "Whisper", "Python", "Java", "C++"]:
            entities["Technologies"].append(w)
        elif w in ["CDOT", "VoltGuard", "HealthSphere", "BharatNet", "Project"]:
            entities["Projects"].append(w)
        elif w in ["India", "USA", "UK", "London", "Delhi", "Mumbai", "Bangalore"]:
            entities["Locations"].append(w)
        else:
            # Put other capitalized nouns in Organizations tentatively
            if len(entities["Organizations"]) < 5:
                entities["Organizations"].append(w)
                
    # Filter empty lists
    entities = {k: v for k, v in entities.items() if v}
    return json.dumps(entities)
