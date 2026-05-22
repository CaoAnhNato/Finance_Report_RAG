import os
import glob
import logging
from typing import List
from prefect import task, flow

from src.rag_report.config import settings
from src.rag_report.config.logging import setup_logger
from src.rag_report.ingestion.parser import FinancialReportParser
from src.rag_report.ingestion.store import DuckDBStore
from src.rag_report.ingestion.vector_sync import QdrantSync

logger = setup_logger("prefect_ingestion_flow")

@task(name="Scan OCR Files")
def scan_ocr_files(raw_dir: str) -> List[str]:
    """Find all extracted text files recursively in the data directory."""
    logger.info(f"Scanning directory: {raw_dir} recursively...")
    pattern = os.path.join(raw_dir, "**", "*_extracted.txt")
    files = glob.glob(pattern, recursive=True)
    # Sort files by year extracted from filename/path
    files.sort()
    logger.info(f"Found {len(files)} extracted report text files.")
    for f in files:
        logger.info(f" - {f}")
    return files

@task(name="Ingest File")
def ingest_file(filepath: str, store_db_path: str, qdrant_collection: str) -> bool:
    """Parse, save, and sync a single file."""
    try:
        # Initialize parser, store, and qdrant sync
        parser = FinancialReportParser()
        db = DuckDBStore(store_db_path)
        qdrant = QdrantSync(qdrant_collection)
        
        # 1. Parse file and generate embeddings
        doc, chunks = parser.parse_file(filepath)
        
        # 2. Clear old data for this year in Qdrant (to prevent duplicate chunks on re-runs)
        qdrant.delete_by_year(doc.fiscal_year)
        
        # 3. Save to local DuckDB database
        logger.info(f"Saving document metadata and {len(chunks)} chunks to DuckDB...")
        db.add_document(doc)
        db.add_chunks(chunks)
        
        # 4. Sync vectors to Qdrant Cloud
        logger.info(f"Syncing {len(chunks)} chunks to Qdrant Cloud...")
        qdrant.upsert_chunks(chunks)
        
        db.close()
        logger.info(f"Successfully finished ingestion for {filepath}.")
        return True
    except Exception as e:
        logger.error(f"Failed to ingest file {filepath}: {str(e)}")
        return False

@flow(name="Financial Reports Ingestion Flow")
def ingest_financial_reports_flow(
    raw_dir: str = settings.RAW_OCR_DIR_ABS,
    store_db_path: str = settings.LOCAL_DB_PATH_ABS,
    qdrant_collection: str = settings.QDRANT_COLLECTION
):
    """Main Prefect flow to run the ingestion pipeline."""
    logger.info("Starting ingestion flow...")
    files = scan_ocr_files(raw_dir)
    
    success_count = 0
    for filepath in files:
        success = ingest_file(filepath, store_db_path, qdrant_collection)
        if success:
            success_count += 1
            
    logger.info(f"Ingestion flow finished. Successfully processed {success_count}/{len(files)} files.")
    return success_count

if __name__ == "__main__":
    ingest_financial_reports_flow()
