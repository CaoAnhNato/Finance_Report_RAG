import os
import json
import logging
import duckdb
from typing import List, Dict, Any, Optional

from src.rag_report.config import settings
from src.rag_report.schemas.models import DocumentSchema, ChunkSchema

logger = logging.getLogger(__name__)

class DuckDBStore:
    """Local storage using DuckDB to store document metadata and chunk text for fast keyword queries."""
    
    def __init__(self, db_path: str = None) -> None:
        self.db_path = db_path or settings.LOCAL_DB_PATH_ABS
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        # 1. Documents table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR PRIMARY KEY,
                file_name VARCHAR,
                company_id VARCHAR,
                fiscal_year INTEGER,
                report_type VARCHAR,
                raw_file_path VARCHAR,
                total_pages INTEGER,
                total_chunks INTEGER
            )
        """)
        
        # 2. Chunks table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id VARCHAR PRIMARY KEY,
                doc_id VARCHAR,
                company_id VARCHAR,
                fiscal_year INTEGER,
                report_type VARCHAR,
                page_num INTEGER,
                chunk_index INTEGER,
                text_content VARCHAR,
                chunk_type VARCHAR,
                extracted_facts VARCHAR,
                metadata VARCHAR
            )
        """)
        logger.info("DuckDB tables initialized successfully.")

    def close(self) -> None:
        self.conn.close()

    def add_document(self, doc: DocumentSchema) -> None:
        """Upsert a document metadata into the database."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO documents 
            (doc_id, file_name, company_id, fiscal_year, report_type, raw_file_path, total_pages, total_chunks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc.doc_id, doc.file_name, doc.company_id, doc.fiscal_year, doc.report_type, 
             doc.raw_file_path, doc.total_pages, doc.total_chunks)
        )

    def add_chunks(self, chunks: List[ChunkSchema]) -> None:
        """Bulk insert chunks into the database."""
        # We can construct batch parameters
        params = []
        for c in chunks:
            params.append((
                c.chunk_id, c.doc_id, c.company_id, c.fiscal_year, c.report_type,
                c.page_num, c.chunk_index, c.text_content, c.chunk_type,
                c.extracted_facts or "", json.dumps(c.metadata)
            ))
        
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO chunks
            (chunk_id, doc_id, company_id, fiscal_year, report_type, page_num, chunk_index, text_content, chunk_type, extracted_facts, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params
        )

    def keyword_search(
        self, 
        query_text: str, 
        fiscal_years: Optional[List[int]] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Perform a keyword search using case-insensitive LIKE/ILIKE on text_content."""
        # Simple token-based keyword search using SQL
        # We will split the query into words and search for match occurrences
        words = [w.strip() for w in query_text.split() if w.strip()]
        if not words:
            return []
        
        # Build query
        sql = "SELECT chunk_id, doc_id, company_id, fiscal_year, report_type, page_num, chunk_index, text_content, chunk_type, extracted_facts, metadata FROM chunks WHERE ("
        conditions = []
        params = []
        
        for w in words:
            conditions.append("text_content ILIKE ?")
            params.append(f"%{w}%")
            
        sql += " OR ".join(conditions) + ")"
        
        if fiscal_years:
            year_placeholders = ",".join(["?"] * len(fiscal_years))
            sql += f" AND fiscal_year IN ({year_placeholders})"
            params.extend(fiscal_years)
            
        sql += " LIMIT ?"
        params.append(limit)
        
        results = []
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()
        
        for r in rows:
            results.append({
                "chunk_id": r[0],
                "doc_id": r[1],
                "company_id": r[2],
                "fiscal_year": r[3],
                "report_type": r[4],
                "page_num": r[5],
                "chunk_index": r[6],
                "text_content": r[7],
                "chunk_type": r[8],
                "extracted_facts": r[9],
                "metadata": json.loads(r[10])
            })
            
        return results

    def get_chunks_by_year(self, fiscal_year: int) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a specific fiscal year."""
        cursor = self.conn.execute(
            "SELECT chunk_id, text_content, chunk_type, page_num, chunk_index FROM chunks WHERE fiscal_year = ? ORDER BY page_num, chunk_index",
            (fiscal_year,)
        )
        rows = cursor.fetchall()
        return [
            {
                "chunk_id": r[0],
                "text_content": r[1],
                "chunk_type": r[2],
                "page_num": r[3],
                "chunk_index": r[4]
            }
            for r in rows
        ]
