from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class DocumentSchema(BaseModel):
    """Schema representing an ingested financial report file."""
    doc_id: str = Field(description="Unique ID for the document (UUID)")
    file_name: str = Field(description="Original file name")
    company_id: str = Field("A32", description="Company code")
    fiscal_year: int = Field(description="Fiscal year of the report")
    report_type: str = Field("Kiemtoan", description="Type of report (e.g. Kiemtoan)")
    raw_file_path: str = Field(description="Absolute path to the raw text file")
    total_pages: int = Field(default=0, description="Total pages in the report")
    total_chunks: int = Field(default=0, description="Total chunks extracted")

class ChunkSchema(BaseModel):
    """Schema representing a text, table, or fact chunk for retrieval and database storage."""
    chunk_id: str = Field(description="Unique ID for the chunk (UUID)")
    doc_id: str = Field(description="Parent document ID (UUID)")
    company_id: str = Field("A32", description="Company code")
    fiscal_year: int = Field(description="Fiscal year")
    report_type: str = Field("Kiemtoan", description="Report type")
    page_num: int = Field(description="Page number (1-based)")
    chunk_index: int = Field(description="Relative index within document")
    text_content: str = Field(description="Raw text or Markdown representation of the chunk")
    chunk_type: str = Field(description="Type of chunk: 'text', 'table', or 'fact'")
    extracted_facts: Optional[str] = Field(default=None, description="Extracted key numbers or facts in clean format")
    embedding: Optional[List[float]] = Field(default=None, description="1024-dimensional dense embedding")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")
