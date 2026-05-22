import logging
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.rag_report.config import settings

logger = logging.getLogger(__name__)

class FPTCloudReranker:
    """Interfaces with FPT Cloud Reranker to rank and filter retrieved document chunks."""
    
    def __init__(self) -> None:
        self.url = f"{settings.FPT_RERANK_BASE_URL}/v1/rerank"
        self.api_key = settings.FPT_RERANK_API_KEY
        self.model = settings.FPT_RERANK_MODEL
        
        if not self.api_key:
            raise ValueError("FPT_RERANK_API_KEY is not configured in environment!")

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        reraise=True
    )
    def _call_rerank_api(self, query: str, docs: List[str], top_n: int) -> List[Dict[str, Any]]:
        """Call FPT Rerank API with retry mechanism."""
        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": top_n
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json().get("results", [])
        except Exception as e:
            logger.error(f"FPT Cloud Rerank API request failed: {str(e)}")
            raise e

    def rerank_contexts(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        top_n: int = 15,
        min_score: float = 0.35
    ) -> List[Dict[str, Any]]:
        """Rerank contexts, sorting and filtering based on the reranker score."""
        if not contexts:
            return []
            
        # Standardized texts to feed into reranker
        # Include metadata like year and page for better semantic alignment
        docs_to_rerank = [
            f"Báo cáo tài chính năm {c['fiscal_year']} trang {c['page_num']}: {c['text_content']}"
            for c in contexts
        ]
        
        # Limit top_n to the number of contexts available
        actual_top_n = min(len(contexts), top_n)
        
        logger.info(f"Reranking {len(contexts)} contexts for query: '{query}'...")
        try:
            results = self._call_rerank_api(query, docs_to_rerank, actual_top_n)
            
            reranked = []
            for r in results:
                idx = r["index"]
                # Handle either relevance_score or score
                score = r.get("relevance_score", r.get("score", 0.0))
                
                # Check threshold
                if score >= min_score:
                    chunk = contexts[idx].copy()
                    chunk["rerank_score"] = score
                    reranked.append(chunk)
                    
            # Sort by score descending
            reranked = sorted(reranked, key=lambda x: x["rerank_score"], reverse=True)
            logger.info(f"Reranked finished: {len(reranked)} contexts kept (above score threshold {min_score}).")
            return reranked
            
        except Exception as e:
            logger.error(f"Rerank failed: {str(e)}. Falling back to original order.")
            # Fallback: return original contexts with default scores
            for c in contexts:
                c["rerank_score"] = c.get("score", 0.5)
            return contexts[:top_n]
