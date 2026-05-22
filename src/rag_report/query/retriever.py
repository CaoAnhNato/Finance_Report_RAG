import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.rag_report.config import settings
from src.rag_report.ingestion.embedding import FPTCloudEmbedding
from src.rag_report.ingestion.store import DuckDBStore

logger = logging.getLogger(__name__)

class HybridRetriever:
    """Combines Qdrant Dense Vector Search and DuckDB Keyword Search using Reciprocal Rank Fusion (RRF)."""
    
    def __init__(self, db_path: str = None, collection_name: str = None) -> None:
        self.db_store = DuckDBStore(db_path or settings.LOCAL_DB_PATH_ABS)
        self.embed_model = FPTCloudEmbedding()
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        
        if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
            raise ValueError("QDRANT_URL or QDRANT_API_KEY is not configured in environment!")
            
        self.qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )

    def retrieve_dense(self, query: str, fiscal_year: Optional[int] = None, top_k: int = 30) -> List[Dict[str, Any]]:
        """Dense Vector Retrieval using FPT Vietnamese Embedding and Qdrant Cloud."""
        # Get query embedding
        query_vector = self.embed_model.get_query_embedding(query)
        
        # Build filter conditions
        filter_conds = []
        if fiscal_year:
            filter_conds.append(
                FieldCondition(
                    key="fiscal_year",
                    match=MatchValue(value=fiscal_year)
                )
            )
            
        qdrant_filter = Filter(must=filter_conds) if filter_conds else None
        
        try:
            # Query Qdrant Cloud (using query_points since search is deprecated in newer client)
            response = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True
            )
            
            results = []
            for point in response.points:
                payload = point.payload or {}
                results.append({
                    "chunk_id": str(point.id),
                    "doc_id": payload.get("doc_id"),
                    "company_id": payload.get("company_id"),
                    "fiscal_year": payload.get("fiscal_year"),
                    "page_num": payload.get("page_num"),
                    "text_content": payload.get("text_content"),
                    "chunk_type": payload.get("chunk_type"),
                    "score": point.score,
                    "extracted_facts": payload.get("extracted_facts", "")
                })
            return results
        except Exception as e:
            logger.error(f"Qdrant dense search failed: {str(e)}")
            return []

    def retrieve_keyword(self, query: str, fiscal_year: Optional[int] = None, top_k: int = 30) -> List[Dict[str, Any]]:
        """Keyword Search using DuckDB ILIKE on text content."""
        try:
            years = [fiscal_year] if fiscal_year else None
            return self.db_store.keyword_search(query, fiscal_years=years, limit=top_k)
        except Exception as e:
            logger.error(f"DuckDB keyword search failed: {str(e)}")
            return []

    def retrieve_hybrid_rrf(
        self,
        query: str,
        fiscal_year: Optional[int] = None,
        vector_top_k: int = 30,
        keyword_top_k: int = 30,
        rrf_constant: int = 60
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion (RRF) combining Dense and Keyword retrievals."""
        dense_results = self.retrieve_dense(query, fiscal_year=fiscal_year, top_k=vector_top_k)
        keyword_results = self.retrieve_keyword(query, fiscal_year=fiscal_year, top_k=keyword_top_k)
        
        # Unique list of chunks
        chunk_dict = {}
        for r in dense_results:
            chunk_dict[r["chunk_id"]] = r
        for r in keyword_results:
            if r["chunk_id"] not in chunk_dict:
                chunk_dict[r["chunk_id"]] = r
                
        # RRF Rank Scores
        rrf_scores = {}
        
        for rank, r in enumerate(dense_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_constant + rank + 1)
            
        for rank, r in enumerate(keyword_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_constant + rank + 1)
            
        # Sort chunks by RRF score descending
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        hybrid_results = []
        for cid, rrf_score in sorted_chunks:
            chunk = chunk_dict[cid].copy()
            chunk["rrf_score"] = rrf_score
            hybrid_results.append(chunk)
            
        return hybrid_results

    def retrieve_for_questions(
        self,
        questions: List[str],
        fiscal_year: Optional[int] = None,
        vector_top_k: int = 30,
        keyword_top_k: int = 30
    ) -> List[Dict[str, Any]]:
        """Retrieve and merge context chunks for multiple sub-questions, removing duplicates."""
        all_results = []
        seen_chunks = set()
        
        # Retrieve results for each sub-question and combine
        for q in questions:
            q_results = self.retrieve_hybrid_rrf(
                q,
                fiscal_year=fiscal_year,
                vector_top_k=vector_top_k,
                keyword_top_k=keyword_top_k
            )
            for r in q_results:
                if r["chunk_id"] not in seen_chunks:
                    seen_chunks.add(r["chunk_id"])
                    all_results.append(r)
                    
        return all_results
