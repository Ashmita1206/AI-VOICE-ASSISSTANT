"""
Document Retrieval Ranker
=========================

Multi-signal hybrid ranking for candidate documents.
Combines:
- Semantic Similarity (Embeddings)
- BM25 Lexical Search
- Filename Match (Tokenized & Substring Boost)
- Folder Match (Project/Directory Context)
- Entity Match (Projects, Technologies, Organizations)
- Keyword Match
- Extension Boost & Intent Preference
- Recency Bonus
"""

import difflib
import logging
import re
import time
from typing import List, Set, Tuple

import numpy as np

from agentic.document_retrieval.schemas import IndexedDocument, SearchResult
from agentic.document_retrieval.retriever import normalize_query, extract_extension_preference

logger = logging.getLogger(__name__)

from agentic.document_retrieval import config
from agentic.document_retrieval.retriever import normalize_query, extract_extension_preference, parse_query, normalize_folder_name

# ── Ranking Weights (Stage 5 Specification) ──────────────────────────────
W_FOLDER    = 0.40
W_FILENAME  = 0.30
W_BM25      = 0.15
W_SEMANTIC  = 0.10
W_RECENCY   = 0.05

RECENCY_WINDOW = 365 * 24 * 3600  # 1 year

def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())

def _bm25_scores(query_tokens: List[str], documents_text: List[str]) -> List[float]:
    """BM25 scoring with fallback to TF."""
    if not query_tokens:
        return [0.0] * len(documents_text)

    tokenized_corpus = [_tokenize(doc) for doc in documents_text]
    
    try:
        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        max_score = float(np.max(scores)) if len(scores) > 0 else 1.0
        if max_score == 0:
            return [0.0] * len(documents_text)
        return [float(s) / max_score for s in scores]
    except ImportError:
        query_set = set(query_tokens)
        result = []
        for tokens in tokenized_corpus:
            if not tokens:
                result.append(0.0)
                continue
            overlap = sum(1 for t in tokens if t in query_set)
            result.append(overlap / len(tokens))
        return result

def _filename_score(query_tokens: List[str], filename: str) -> float:
    """Calculate filename match score with token overlap & substring boost."""
    if not filename or not query_tokens:
        return 0.0
        
    stem = filename.rsplit(".", 1)[0].lower().replace("_", " ").replace("-", " ")
    fn_tokens = set(_tokenize(filename))

    # 1. Exact phrase match in filename stem
    clean_q = " ".join(query_tokens)
    stem_compact = stem.replace(" ", "")
    clean_q_compact = clean_q.replace(" ", "")
    
    if clean_q in stem or clean_q_compact in stem_compact:
        return 1.0

    # 2. Token overlap ratio
    matched = sum(1 for qt in query_tokens if qt in fn_tokens or qt in stem)
    ratio = matched / len(query_tokens)

    # 3. Fuzzy ratio fallback
    fuzzy = difflib.SequenceMatcher(None, clean_q, stem).ratio()

    return max(ratio, fuzzy * 0.8)

def _folder_score(query_tokens: List[str], doc: IndexedDocument, matched_folder_paths: List[str] = None, folder_candidates: List[str] = None) -> float:
    """Calculate folder match score. Gives 1.0 for files inside matched folder/project directory."""
    if matched_folder_paths:
        doc_path_norm = doc.path.lower().replace("/", "\\")
        for mfp in matched_folder_paths:
            mfp_norm = mfp.lower().replace("/", "\\").rstrip("\\")
            if doc_path_norm.startswith(mfp_norm + "\\") or doc_path_norm == mfp_norm:
                return 1.0

    # Check project_folder / parent_folder / folder against folder candidates
    doc_folders = {
        normalize_folder_name(getattr(doc, 'project_folder', '')),
        normalize_folder_name(getattr(doc, 'parent_folder', '')),
        normalize_folder_name(getattr(doc, 'folder', ''))
    }
    
    if folder_candidates:
        for fc in folder_candidates:
            norm_fc = normalize_folder_name(fc)
            if norm_fc and norm_fc in doc_folders:
                return 1.0
                
    if query_tokens:
        clean_q = normalize_folder_name(" ".join(query_tokens))
        for df in doc_folders:
            if df and (clean_q in df or df in clean_q):
                return 1.0
                
    return 0.0

def _recency_score(modified_ts: float) -> float:
    age = time.time() - modified_ts
    if age <= 0:
        return 1.0
    if age >= RECENCY_WINDOW:
        return 0.0
    return 1.0 - (age / RECENCY_WINDOW)

def _extension_score(ext: str, preferred_exts: Set[str]) -> float:
    ext = ext.lower()
    
    # Explicit query intent match
    if preferred_exts and ext in preferred_exts:
        return 1.0
        
    # High Priority Document class
    if ext in config.HIGH_PRIORITY_DOC_EXTENSIONS:
        return 0.85
    # Second Priority Code class
    elif ext in config.SECOND_PRIORITY_CODE_EXTENSIONS:
        return 0.5
    return 0.2

def _generate_match_reason(doc: IndexedDocument, query_tokens: List[str], fn_score: float, fo_score: float, bm_score: float) -> str:
    """Generate human-readable explanation of why this file matched."""
    reasons = []
    
    if fo_score > 0.5:
        reasons.append(f"Folder '{getattr(doc, 'project_folder', doc.folder)}' matches query target")
    if fn_score > 0.5:
        reasons.append(f"Filename contains '{doc.filename}'")
    if doc.keywords:
        matching_kws = [k for k in doc.keywords.split() if k in query_tokens]
        if matching_kws:
            reasons.append(f"Content mentions: {', '.join(matching_kws[:3])}")
            
    if not reasons:
        reasons.append(f"Semantic relevance score match in {doc.filename}")
        
    return " | ".join(reasons)

def _deduplicate_results(scored_candidates: List[Tuple[float, IndexedDocument, float, float, float]]) -> List[Tuple[float, IndexedDocument, float, float, float]]:
    """Deduplicate candidate files by stem and path, preferring newer and non-duplicate filenames."""
    seen_stems = {}
    deduped = []
    
    for item in scored_candidates:
        score, doc, fn, fo, bm = item
        clean_stem = re.sub(r"\s*\(\d+\)$", "", doc.filename.rsplit(".", 1)[0].lower().replace("_", " ").strip())
        
        if clean_stem not in seen_stems:
            seen_stems[clean_stem] = item
            deduped.append(item)
        else:
            prev_score, prev_doc, _, _, _ = seen_stems[clean_stem]
            if doc.modified_ts > prev_doc.modified_ts and score >= prev_score * 0.9:
                idx = deduped.index(seen_stems[clean_stem])
                deduped[idx] = item
                seen_stems[clean_stem] = item
                
    return deduped

def rank_documents(query: str, candidates: List[IndexedDocument], semantic_dists: List[float], top_n: int = 5, matched_folder_paths: List[str] = None) -> List[SearchResult]:
    """Rank documents using stage-based multi-signal hybrid scoring (Folder Dominant)."""
    if not candidates:
        return []
        
    parsed = parse_query(query)
    query_tokens = parsed.target_filename_tokens if parsed.target_filename_tokens else _tokenize(parsed.normalized_query)
    preferred_exts = parsed.preferred_extensions
    folder_candidates = parsed.folder_candidates
    
    # Combine filename, folder, parent_folder, project_folder, keywords, summary for BM25 corpus
    corpus_text = [
        f"{c.filename} {c.folder} {getattr(c, 'parent_folder', '')} {getattr(c, 'project_folder', '')} {c.keywords} {c.summary}"
        for c in candidates
    ]
    bm25_scores = _bm25_scores(query_tokens, corpus_text)
    
    scored_candidates = []
    
    logger.info(f"[RANKER] Ranking {len(candidates)} candidates | Parsed Query: '{parsed.normalized_query}' | Tokens: {query_tokens}")
    
    EXCLUDED_EXT = {"py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "cs", "go", "rb", "php", "swift", "kt", "rs", "sh", "bat", "ps1", "html", "htm", "css", "xml", "dll", "exe", "pyd", "so", "class", "pyc", "obj", "bin", "sys"}
    for idx, (doc, sem_dist) in enumerate(zip(candidates, semantic_dists)):
        if doc.extension.lower() in EXCLUDED_EXT:
            continue
        sem = max(0.0, min(1.0, sem_dist))
        bm = bm25_scores[idx]
        fn = _filename_score(query_tokens, doc.filename)
        fo = _folder_score(query_tokens, doc, matched_folder_paths=matched_folder_paths, folder_candidates=folder_candidates)
        rec = _recency_score(doc.modified_ts)
        ext = _extension_score(doc.extension, preferred_exts)
        
        composite = (
            (W_FOLDER * fo) +
            (W_FILENAME * fn) +
            (W_BM25 * bm) +
            (W_SEMANTIC * sem) +
            (W_RECENCY * rec)
        )
        
        # Detailed Stage 6 Score Logging per candidate
        score_log_msg = (
            f"[SCORE LOG] File: {doc.filename:35s} | FolderScore: {fo:.2f} | "
            f"FilenameScore: {fn:.2f} | BM25Score: {bm:.2f} | SemanticScore: {sem:.2f} | "
            f"RecencyScore: {rec:.2f} => FinalScore: {composite:.4f}"
        )
        logger.debug(score_log_msg)
        
        scored_candidates.append((composite, doc, fn, fo, bm))
        
    # Sort by composite score descending
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Deduplication
    deduped_candidates = _deduplicate_results(scored_candidates)
    
    results = []
    for rank, (score, doc, fn, fo, bm) in enumerate(deduped_candidates[:top_n], start=1):
        conf_pct = min(100, int((score / 0.75) * 100))
        reason = _generate_match_reason(doc, query_tokens, fn, fo, bm)
        
        snippet = doc.summary if doc.summary else f"Document: {doc.filename}"
        if reason:
            snippet = f"[{reason}] {snippet}"
            
        results.append(SearchResult(
            rank=rank,
            score=score,
            path=doc.path,
            filename=doc.filename,
            extension=doc.extension,
            folder=getattr(doc, 'project_folder', doc.folder),
            modified_ts=doc.modified_ts,
            confidence_pct=conf_pct,
            snippet=snippet
        ))
        
    return results
