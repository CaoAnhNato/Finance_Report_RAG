import logging
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from src.rag_report.config import settings
from src.rag_report.schemas.models import ChunkSchema

logger = logging.getLogger(__name__)

class QdrantSync:
    """Synchronizer to upload chunk vectors and metadata payloads to Qdrant Cloud."""
    
    def __init__(self, collection_name: str = None) -> None:
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
            raise ValueError("QDRANT_URL or QDRANT_API_KEY is not configured in environment!")
            
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create Qdrant collection if it does not exist."""
        # Use collection_exists (newer qdrant client standard)
        try:
            exists = self.client.collection_exists(self.collection_name)
            if not exists:
                logger.info(f"Creating collection '{self.collection_name}' in Qdrant Cloud...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
                )
            else:
                logger.info(f"Qdrant collection '{self.collection_name}' already exists.")
                
            # Create payload indices for filtering/deletion fields
            from qdrant_client.models import PayloadSchemaType
            logger.info("Ensuring payload index for 'fiscal_year'...")
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="fiscal_year",
                field_schema=PayloadSchemaType.INTEGER
            )
            logger.info("Ensuring payload index for 'company_id'...")
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="company_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception as e:
            logger.error(f"Error checking/creating Qdrant collection: {str(e)}")
            raise e

    def upsert_chunks(self, chunks: List[ChunkSchema], batch_size: int = 50) -> None:
        """Upsert chunks with embeddings to Qdrant Cloud in batches."""
        points = []
        for c in chunks:
            if c.embedding is None:
                logger.warning(f"Chunk {c.chunk_id} has no embedding, skipping vector sync.")
                continue
                
            payload = {
                "doc_id": c.doc_id,
                "company_id": c.company_id,
                "fiscal_year": c.fiscal_year,
                "report_type": c.report_type,
                "page_num": c.page_num,
                "chunk_index": c.chunk_index,
                "text_content": c.text_content,
                "chunk_type": c.chunk_type,
                "extracted_facts": c.extracted_facts or "",
                **c.metadata
            }
            
            points.append(
                PointStruct(
                    id=c.chunk_id, # String UUID is supported by Qdrant
                    vector=c.embedding,
                    payload=payload
                )
            )
            
        if not points:
            return
            
        logger.info(f"Upserting {len(points)} points into Qdrant collection '{self.collection_name}'...")
        
        # Batch upload
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                logger.info(f"Successfully upserted batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1}")
            except Exception as e:
                logger.error(f"Failed to upsert batch {i // batch_size + 1} to Qdrant: {str(e)}")
                raise e
                
    def delete_by_year(self, fiscal_year: int) -> None:
        """Delete points belonging to a specific year (to support clean reinoculation)."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        logger.info(f"Deleting existing points for year {fiscal_year} in Qdrant...")
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="fiscal_year",
                            match=MatchValue(value=fiscal_year)
                        )
                    ]
                )
            )
        except Exception as e:
            logger.error(f"Failed to delete points by year {fiscal_year}: {str(e)}")
            raise e
