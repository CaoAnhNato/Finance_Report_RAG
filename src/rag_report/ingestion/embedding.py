import logging
from typing import List, Any
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from src.rag_report.config import settings

logger = logging.getLogger(__name__)

class FPTCloudEmbedding(BaseEmbedding):
    """Custom LlamaIndex Embedding class to interface with FPT Cloud's Vietnamese_Embedding."""
    
    _client: OpenAI = PrivateAttr()
    _model_name: str = PrivateAttr()
    _base_url: str = PrivateAttr()
    _api_key: str = PrivateAttr()
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None,
        embed_batch_size: int = 10,
        **kwargs: Any
    ) -> None:
        super().__init__(embed_batch_size=embed_batch_size, **kwargs)
        self._api_key = api_key or settings.FPT_RERANK_API_KEY
        self._base_url = base_url or settings.FPT_RERANK_BASE_URL
        self._model_name = model_name or settings.FPT_EMBEDDING_MODEL
        
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=30.0
        )
        
    @classmethod
    def class_name(cls) -> str:
        return "FPTCloudEmbedding"
        
    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_fpt_api(self, texts: List[str], input_type: str) -> List[List[float]]:
        """Call FPT Cloud API with retry logic."""
        try:
            response = self._client.embeddings.create(
                model=self._model_name,
                input=texts,
                dimensions=1024,
                encoding_format='float',
                extra_body={
                    "input_text_truncate": "none",
                    "input_type": input_type
                }
            )
            # FPT Cloud API returns standard OpenAI-compatible response
            embeddings = [data.embedding for data in response.data]
            return embeddings
        except Exception as e:
            logger.error(f"FPT Cloud Embedding API call failed: {str(e)}")
            raise e

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get query embedding with input_type='query'."""
        embeddings = self._call_fpt_api([query], input_type="query")
        return embeddings[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get text embedding with input_type='passage'."""
        embeddings = self._call_fpt_api([text], input_type="passage")
        return embeddings[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get batch text embeddings with input_type='passage'."""
        if not texts:
            return []
        
        # Batch the embeddings requests based on embed_batch_size
        results = []
        for i in range(0, len(texts), self.embed_batch_size):
            batch = texts[i : i + self.embed_batch_size]
            embeddings = self._call_fpt_api(batch, input_type="passage")
            results.extend(embeddings)
        return results

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Async version of _get_query_embedding (fallback to sync)."""
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Async version of _get_text_embedding (fallback to sync)."""
        return self._get_text_embedding(text)
