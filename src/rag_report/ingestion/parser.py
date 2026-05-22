import os
import re
import uuid
import logging
from typing import List, Dict, Any, Tuple
from openai import OpenAI

from src.rag_report.config import settings
from src.rag_report.schemas.models import DocumentSchema, ChunkSchema
from src.rag_report.ingestion.embedding import FPTCloudEmbedding

logger = logging.getLogger(__name__)

class FinancialReportParser:
    """Parser to split raw OCR text reports into pages, tables, and text chunks with fact extraction."""
    
    def __init__(self, embed_model: FPTCloudEmbedding = None) -> None:
        self.embed_model = embed_model or FPTCloudEmbedding()
        self.llm_client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )

    def extract_year_from_path(self, filepath: str) -> int:
        """Extract fiscal year from directory path (e.g. data/A32/2017/ -> 2017)."""
        match = re.search(r"\b(20\d{2})\b", filepath)
        if match:
            return int(match.group(1))
        # Default fallback
        raise ValueError(f"Could not extract fiscal year from path: {filepath}")

    def split_into_pages(self, content: str) -> List[Tuple[int, str]]:
        """Split content by page boundaries and return list of (page_num, page_text)."""
        # Split by ===== PAGE \d+ =====
        pattern = r"=====\s*PAGE\s+(\d+)\s*====="
        parts = re.split(pattern, content)
        
        # Parts will be [pre_text, '1', page1_text, '2', page2_text, ...]
        if len(parts) < 3:
            # If no markers, treat entire doc as page 1
            return [(1, content.strip())]
            
        pages = []
        for i in range(1, len(parts), 2):
            page_num = int(parts[i])
            page_text = parts[i+1].strip()
            if page_text:
                pages.append((page_num, page_text))
        return pages

    def extract_facts_using_llm(self, chunk_text: str) -> str:
        """Call gpt-5.4-mini to extract key financial numbers and metrics from text chunk."""
        # Only call LLM if there are digits in the text to optimize costs
        if not any(char.isdigit() for char in chunk_text):
            return ""
            
        prompt = (
            "Bạn là một trợ lý phân tích tài chính chuyên nghiệp.\n"
            "Hãy trích xuất tất cả các chỉ số tài chính, số liệu số học kèm theo đơn vị đo lường (VND, %, người...) "
            "từ đoạn văn bản dưới đây. Hãy liệt kê chúng dưới dạng ngắn gọn, phân tách bởi dấu chấm phẩy.\n"
            "Nếu không có số liệu nào quan trọng, trả về chuỗi rỗng.\n\n"
            f"Văn bản:\n\"\"\"\n{chunk_text}\n\"\"\"\n\n"
            "Chỉ số trích xuất:"
        )
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.PLANNER_MODEL,
                messages=[
                    {"role": "system", "content": "Bạn chỉ trả về các chỉ số tài chính được trích xuất ngắn gọn, không giải thích dài dòng."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.0
            )
            if isinstance(response, str):
                return response.strip()
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Fact extraction failed for chunk: {str(e)}")
            return ""

    def parse_file(self, filepath: str) -> Tuple[DocumentSchema, List[ChunkSchema]]:
        """Parse raw report file into a DocumentSchema and a list of ChunkSchemas with embeddings."""
        logger.info(f"Parsing file: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        file_basename = os.path.basename(filepath)
        fiscal_year = self.extract_year_from_path(filepath)
        doc_id = str(uuid.uuid4())
        
        pages = self.split_into_pages(content)
        total_pages = len(pages)
        
        all_chunks: List[ChunkSchema] = []
        chunk_idx = 0
        
        # Standard chunk parameters
        text_chunk_size = 800
        text_chunk_overlap = 150
        
        for page_num, page_text in pages:
            # 1. Extract HTML tables
            tables = re.findall(r"(<table>.*?</table>)", page_text, re.DOTALL)
            
            # Clean page text by removing tables to process text separately
            clean_page_text = re.sub(r"<table>.*?</table>", "\n[TABLE_PLACEHOLDER]\n", page_text, flags=re.DOTALL)
            
            # Process tables
            for t_idx, table_html in enumerate(tables):
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_page_{page_num}_table_{t_idx}"))
                
                table_chunk = ChunkSchema(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    company_id="A32",
                    fiscal_year=fiscal_year,
                    report_type="Kiemtoan",
                    page_num=page_num,
                    chunk_index=chunk_idx,
                    text_content=table_html,
                    chunk_type="table",
                    extracted_facts=None,
                    metadata={"table_index": t_idx}
                )
                all_chunks.append(table_chunk)
                chunk_idx += 1
                
            # 2. Process text content
            # Split clean page text into overlapping windows
            words = clean_page_text.split()
            # If empty text, skip
            if not words:
                continue
                
            text_str = " ".join(words)
            
            # Simple character sliding window chunking
            start = 0
            while start < len(text_str):
                end = start + text_chunk_size
                # Adjust end to fall on space if possible
                if end < len(text_str):
                    next_space = text_str.find(" ", end, end + 30)
                    if next_space != -1:
                        end = next_space
                
                chunk_text = text_str[start:end].strip()
                if chunk_text and chunk_text != "[TABLE_PLACEHOLDER]":
                    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_page_{page_num}_text_{start}"))
                    
                    text_chunk = ChunkSchema(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        company_id="A32",
                        fiscal_year=fiscal_year,
                        report_type="Kiemtoan",
                        page_num=page_num,
                        chunk_index=chunk_idx,
                        text_content=chunk_text,
                        chunk_type="text",
                        extracted_facts=None,
                        metadata={}
                    )
                    all_chunks.append(text_chunk)
                    chunk_idx += 1
                    
                start += (text_chunk_size - text_chunk_overlap)
                
        # 3. Create Document Schema
        doc_schema = DocumentSchema(
            doc_id=doc_id,
            file_name=file_basename,
            company_id="A32",
            fiscal_year=fiscal_year,
            report_type="Kiemtoan",
            raw_file_path=os.path.abspath(filepath),
            total_pages=total_pages,
            total_chunks=len(all_chunks)
        )
        
        # 4. Extract facts in parallel
        from concurrent.futures import ThreadPoolExecutor
        logger.info(f"Extracting key financial facts using LLM for {len(all_chunks)} chunks in parallel...")
        
        def extract_fact(c: ChunkSchema):
            if c.chunk_type == "table":
                if len(c.text_content) < 2000:
                    c.extracted_facts = self.extract_facts_using_llm(c.text_content)
            else:
                c.extracted_facts = self.extract_facts_using_llm(c.text_content)
                
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(extract_fact, all_chunks)
            
        # 5. Generate Embeddings for all chunks
        logger.info(f"Generating FPT Vietnamese Embeddings for {len(all_chunks)} chunks...")
        texts_to_embed = [
            f"Báo cáo tài chính năm {c.fiscal_year} trang {c.page_num}: {c.text_content}"
            for c in all_chunks
        ]
        
        # Batch get embeddings
        embeddings = self.embed_model.get_text_embedding_batch(texts_to_embed)
        
        for c, emb in zip(all_chunks, embeddings):
            c.embedding = emb
            
        logger.info(f"File parsing, fact extraction and embedding completed for {file_basename}.")
        return doc_schema, all_chunks
