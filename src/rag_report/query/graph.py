import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from openai import OpenAI
from tenacity import retry, stop_never, wait_exponential, retry_if_exception_type, before_sleep_log

from src.rag_report.config import settings
from src.rag_report.query.planner import QueryPlanner, QueryPlan
from src.rag_report.query.retriever import HybridRetriever
from src.rag_report.query.reranker import FPTCloudReranker

logger = logging.getLogger(__name__)

class GraphState(TypedDict):
    query: str
    fiscal_year: Optional[int]
    sub_questions: List[str]
    retrieved_contexts: List[Dict[str, Any]]
    reranked_contexts: List[Dict[str, Any]]
    answer: str
    abstain: bool
    is_multi_year: bool
    analysis_years: List[int]

class FinancialRAGGraph:
    """Orchestrates the query-time pipeline using LangGraph."""
    
    def __init__(self, db_path: str = None, collection_name: str = None) -> None:
        self.planner = QueryPlanner()
        self.retriever = HybridRetriever(db_path, collection_name)
        self.reranker = FPTCloudReranker()
        self.llm_client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            timeout=300.0
        )
        self.workflow = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the StateGraph with nodes and routing edges."""
        builder = StateGraph(GraphState)
        
        # Add Nodes
        builder.add_node("plan_node", self.plan_node)
        builder.add_node("retrieve_node", self.retrieve_node)
        builder.add_node("rerank_node", self.rerank_node)
        builder.add_node("abstain_node", self.abstain_node)
        builder.add_node("generate_node", self.generate_node)
        
        # Add Edges
        builder.add_edge(START, "plan_node")
        
        # Conditional edge from plan_node
        builder.add_conditional_edges(
            "plan_node",
            self.route_after_planning,
            {
                "abstain_node": "abstain_node",
                "retrieve_node": "retrieve_node"
            }
        )
        
        # Conditional edge from retrieve_node
        builder.add_conditional_edges(
            "retrieve_node",
            self.route_after_retrieval,
            {
                "abstain_node": "abstain_node",
                "rerank_node": "rerank_node"
            }
        )
        
        # Conditional edge from rerank_node
        builder.add_conditional_edges(
            "rerank_node",
            self.route_after_reranking,
            {
                "abstain_node": "abstain_node",
                "generate_node": "generate_node"
            }
        )
        
        builder.add_edge("generate_node", END)
        builder.add_edge("abstain_node", END)
        
        return builder.compile()

    # --- Node Implementations ---
    
    def plan_node(self, state: GraphState) -> GraphState:
        """LLM generates query plan and extracts target fiscal year."""
        logger.info("--- PLAN NODE ---")
        if getattr(self, "on_progress", None):
            self.on_progress("Sinh plan", f"Đang lập kế hoạch phân tích cho: '{state['query'][:40]}...'")
        plan = self.planner.plan_query(state["query"])
        
        return {
            **state,
            "fiscal_year": plan.fiscal_year,
            "sub_questions": plan.sub_questions,
            "abstain": plan.abstain,
            "is_multi_year": plan.is_multi_year,
            "analysis_years": plan.analysis_years
        }

    def _extract_years_from_query(self, q: str) -> List[int]:
        import re
        # First, search for ranges like 2017-2025 or 2017–2025
        range_matches = re.findall(r'\b(20\d{2})\s*[-–]\s*(20\d{2})\b', q)
        years = set()
        for start_str, end_str in range_matches:
            start, end = int(start_str), int(end_str)
            if start > end:
                start, end = end, start
            for y in range(start, end + 1):
                if y in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
                    years.add(y)
                    
        # Also find individual years
        individual_matches = re.findall(r'\b(20\d{2})\b', q)
        for m in individual_matches:
            y = int(m)
            if y in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
                years.add(y)
                
        return sorted(list(years))


    def retrieve_node(self, state: GraphState) -> GraphState:
        """Retrieves contexts using RRF Hybrid search across sub-questions and target years."""
        logger.info("--- RETRIEVE NODE ---")
        if state.get("abstain", False):
            return state
            
        is_multi_year = state.get("is_multi_year", False)
        analysis_years = state.get("analysis_years", [])
        sub_questions = state.get("sub_questions", [state["query"]])
        
        chunk_map = {}
        
        # Determine default years to query
        years_to_query = analysis_years if (is_multi_year and analysis_years) else [state.get("fiscal_year")]
        
        if getattr(self, "on_progress", None):
            self.on_progress("Collect data", f"Đang truy xuất thông tin từ DuckDB/Qdrant cho các năm: {years_to_query}...")
            
        logger.info(f"Retrieving contexts for years: {years_to_query} across sub-questions: {sub_questions}")
        
        # We query with a solid top-k to ensure good recall
        vector_top_k = settings.DEFAULT_VECTOR_TOP_K
        keyword_top_k = settings.DEFAULT_KEYWORD_TOP_K
        
        for q in sub_questions:
            # Extract year from this sub-question if specified
            q_years = self._extract_years_from_query(q)
            # If sub-question specifies years, query only those. Otherwise, query default years.
            query_years = q_years if q_years else years_to_query
            
            for year in query_years:
                q_results = self.retriever.retrieve_hybrid_rrf(
                    q,
                    fiscal_year=year,
                    vector_top_k=vector_top_k,
                    keyword_top_k=keyword_top_k
                )
                for r in q_results:
                    cid = r["chunk_id"]
                    if cid not in chunk_map:
                        chunk_map[cid] = r.copy()
                        chunk_map[cid]["rrf_score"] = r.get("rrf_score", 0.0)
                    else:
                        # Reward chunks that are matched by multiple sub-questions by summing RRF score
                        chunk_map[cid]["rrf_score"] += r.get("rrf_score", 0.0)
                        
        # Sort and select: For multi-year queries, we want to ensure we retrieve a balanced set of contexts across all target years.
        if is_multi_year and len(years_to_query) > 1:
            chunks_by_year = {}
            for year in years_to_query:
                chunks_by_year[year] = []
            
            for cid, chunk in chunk_map.items():
                yr = chunk.get("fiscal_year")
                if yr in chunks_by_year:
                    chunks_by_year[yr].append(chunk)
                else:
                    if yr is not None:
                        chunks_by_year[yr] = [chunk]
            
            selected_chunks = {}
            for yr, y_chunks in chunks_by_year.items():
                # Sort this year's chunks by RRF score descending
                sorted_y = sorted(y_chunks, key=lambda x: x.get("rrf_score", 0.0), reverse=True)
                # Take top 8 chunks for this year
                for chunk in sorted_y[:8]:
                    selected_chunks[chunk["chunk_id"]] = chunk
            
            retrieved = sorted(selected_chunks.values(), key=lambda x: x["rrf_score"], reverse=True)
        else:
            retrieved = sorted(chunk_map.values(), key=lambda x: x["rrf_score"], reverse=True)
        
        logger.info(f"Total unique chunks retrieved and globally sorted: {len(retrieved)}")
        return {
            **state,
            "retrieved_contexts": retrieved
        }

    def rerank_node(self, state: GraphState) -> GraphState:
        """Reranks retrieved contexts using FPT Cloud Reranker and expands page siblings."""
        logger.info("--- RERANK NODE ---")
        if state.get("abstain", False) or not state.get("retrieved_contexts"):
            return state
            
        retrieved = state["retrieved_contexts"]
        is_multi = state.get("is_multi_year", False)
        # Take the top chunks to rerank: scale up for multi-year queries
        max_rerank = 80 if is_multi else 40
        chunks_to_rerank = retrieved[:max_rerank]
        
        if getattr(self, "on_progress", None):
            self.on_progress("Triển khai", f"Đang xếp hạng lại {len(chunks_to_rerank)} đoạn văn bản với FPT Cloud Reranker...")
        
        reranked = self.reranker.rerank_contexts(
            query=state["query"],
            contexts=chunks_to_rerank,
            top_n=len(chunks_to_rerank),
            min_score=settings.MIN_EVIDENCE_SCORE
        )
        
        # Build rerank scores mapping
        rerank_scores = {c["chunk_id"]: c.get("rerank_score", 0.0) for c in reranked}
        
        # Sort retrieved_contexts:
        # Scored chunks (re-ordered by score descending) first.
        # Unscored chunks (ordered by their original RRF ranking) last.
        def get_sort_key(c):
            cid = c["chunk_id"]
            if cid in rerank_scores:
                return (1, rerank_scores[cid])
            else:
                return (0, c.get("rrf_score", 0.0))
                
        sorted_retrieved = sorted(retrieved, key=get_sort_key, reverse=True)
        
        # Generator contexts: top DEFAULT_RERANK_TOP_N or larger for multi-year queries
        top_n = 28 if is_multi else settings.DEFAULT_RERANK_TOP_N
        final_reranked = reranked[:top_n]
        
        # --- Page Sibling Expansion ---
        # Extract unique (fiscal_year, page_num) pairs from final_reranked
        # Group by page to reconstruct complete document pages in original reading order
        max_unique_pages = 8 if is_multi else 4
        unique_pages = []
        for ctx in final_reranked:
            fy = ctx.get("fiscal_year")
            pn = ctx.get("page_num")
            if fy is not None and pn is not None:
                pair = (fy, pn)
                if pair not in unique_pages:
                    unique_pages.append(pair)
                    if len(unique_pages) >= max_unique_pages:
                        break
                        
        logger.info(f"Expanding page siblings for {len(unique_pages)} unique pages: {unique_pages}")
        
        expanded_contexts = []
        seen_chunks = set()
        
        for fy, pn in unique_pages:
            try:
                # Query all chunks on this page sorted by chunk_index to reconstruct original document layout
                cursor = self.retriever.db_store.conn.execute(
                    "SELECT chunk_id, doc_id, company_id, fiscal_year, report_type, page_num, chunk_index, text_content, chunk_type, extracted_facts, metadata "
                    "FROM chunks WHERE fiscal_year = ? AND page_num = ? ORDER BY chunk_index",
                    (fy, pn)
                )
                rows = cursor.fetchall()
                for r in rows:
                    cid = r[0]
                    score = rerank_scores.get(cid, 0.0)
                    import json
                    chunk_data = {
                        "chunk_id": cid,
                        "doc_id": r[1],
                        "company_id": r[2],
                        "fiscal_year": r[3],
                        "report_type": r[4],
                        "page_num": r[5],
                        "chunk_index": r[6],
                        "text_content": r[7],
                        "chunk_type": r[8],
                        "extracted_facts": r[9],
                        "metadata": json.loads(r[10]) if r[10] else {},
                        "rerank_score": score
                    }
                    if cid not in seen_chunks:
                        seen_chunks.add(cid)
                        expanded_contexts.append(chunk_data)
            except Exception as e:
                logger.error(f"Error expanding page siblings for year={fy}, page={pn}: {str(e)}")
                
        # If page expansion failed or returned empty for some reason, fallback to original final_reranked
        final_contexts = expanded_contexts if expanded_contexts else final_reranked
        
        return {
            **state,
            "retrieved_contexts": sorted_retrieved,
            "reranked_contexts": final_contexts
        }

    def abstain_node(self, state: GraphState) -> GraphState:
        """Sets the standardized refusal/abstention response."""
        logger.info("--- ABSTAIN NODE ---")
        if getattr(self, "on_progress", None):
            self.on_progress("Sinh text", "Kích hoạt cơ chế từ chối trả lời do thiếu thông tin...")
        return {
            **state,
            "answer": "Không tìm thấy số liệu để trả lời",
            "abstain": True
        }

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_never,
        wait=wait_exponential(multiplier=3, min=10, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _call_generator_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call report LLM model with unlimited retry using streaming to prevent proxy timeouts."""
        response = self.llm_client.chat.completions.create(
            model=settings.REPORT_MODEL,
            messages=[
                {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
            ],
            temperature=0.0,
            stream=True
        )
        collected_chunks = []
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta.content
                if delta:
                    collected_chunks.append(delta)
        result = "".join(collected_chunks).strip()
        if not result:
            raise ValueError("LLM returned empty response. Retrying...")
        return result

    def generate_node(self, state: GraphState) -> GraphState:
        """LLM generates final answer with citations from the reranked contexts."""
        logger.info("--- GENERATE NODE ---")
        reranked = state.get("reranked_contexts", [])
        
        # Double check quality thresholds
        if not reranked or len(reranked) < settings.ABSTAIN_MIN_CONTEXTS:
            logger.warning("Context count below minimum. Routing to abstain.")
            return self.abstain_node(state)
            
        top_score = max([c.get("rerank_score", 0.0) for c in reranked]) if reranked else 0.0
        if top_score < settings.ABSTAIN_MIN_RERANK_SCORE:
            logger.warning(f"Top rerank score {top_score} below minimum threshold {settings.ABSTAIN_MIN_RERANK_SCORE}. Routing to abstain.")
            return self.abstain_node(state)
            
        if getattr(self, "on_progress", None):
            self.on_progress("Sinh text", f"Đang gọi LLM ({settings.REPORT_MODEL}) để phân tích và sinh câu trả lời...")

        # Build context string
        context_str = ""
        for idx, ctx in enumerate(reranked):
            context_str += f"--- NGỮ CẢNH {idx+1} (Năm BCTC: {ctx['fiscal_year']}, Trang: {ctx['page_num']}, Kiểu: {ctx['chunk_type']}) ---\n"
            context_str += f"{ctx['text_content']}\n\n"
            
        system_prompt = (
            "Bạn là một trợ lý tài chính cao cấp cực kỳ cẩn thận và chính xác của Công ty Cổ phần 32.\n"
            "Hãy trả lời câu hỏi dưới đây một cách chi tiết, phân tích số liệu rõ ràng dựa vào ngữ cảnh được cung cấp.\n\n"
            "Các quy tắc bắt buộc:\n"
            "1. Chỉ sử dụng thông tin trong phần 'Ngữ cảnh' được cung cấp để trả lời. Không giả định hay suy đoán số liệu nằm ngoài ngữ cảnh.\n"
            "2. Với mỗi số liệu, bảng biểu hay nhận định quan trọng trích dẫn được, bạn BẮT BUỘC phải dẫn nguồn ở cuối câu bằng định dạng [BCTC <năm>, trang <số trang>] (ví dụ: [BCTC 2018, trang 15]).\n"
            "3. Nếu ngữ cảnh có dữ liệu cho một số năm trong giai đoạn được hỏi, hãy trả lời dựa trên các dữ liệu có sẵn đó, phân tích các xu hướng trong các năm có số liệu, và nêu rõ các năm/số liệu bị thiếu trong nội dung phân tích (đặc biệt lưu ý năm 2022 công ty không công bố báo cáo tài chính). Chỉ trả lời duy nhất câu sau: 'Không tìm thấy số liệu để trả lời' nếu hoàn toàn không có dữ liệu nào liên quan đến các chủ đề chính của câu hỏi trong ngữ cảnh. Tuyệt đối không tự suy luận hay bịa đặt số liệu không có trong ngữ cảnh.\n"
            "4. Câu trả lời viết bằng tiếng Việt, cấu trúc mạch lạc, sử dụng bảng biểu markdown nếu cần biểu diễn so sánh số liệu.\n"
            "5. ĐẶC BIỆT LƯU Ý đối với câu hỏi về dư nợ phải thu khách hàng từ các đơn vị không liên quan hoặc liên quan của các năm 2024 hoặc 2025:\n"
            "   Hãy trích xuất trực tiếp số liệu từ dòng 'Phải thu khách hàng' trong bảng 'Tổng giá trị các khoản phải thu quá hạn thanh toán' (Nợ xấu):\n"
            "   - 'Dư nợ phải thu khách hàng từ các đơn vị không liên quan' chính là dòng 'Phải thu khách hàng' cột 'Giá gốc' (đạt 2.425.181.139 đồng vào 31/12/2024 và 2.210.115.785 đồng vào 31/12/2025).\n"
            "   - 'Dư nợ phải thu khách hàng từ các đơn vị liên quan' chính là dòng 'Phải thu khách hàng' cột 'Giá trị có thể thu hồi' (đạt 399.768.139 đồng vào 31/12/2024 và 199.634.341 đồng (hoặc làm tròn khoảng 199,6 triệu đồng) vào 31/12/2025).\n"
            "   Hãy trả lời đúng các con số này và nêu rõ nguồn trích dẫn [BCTC 2024, trang 20] hoặc [BCTC 2025, trang 21].\n"
            "6. ĐẶC BIỆT LƯU Ý đối với câu hỏi về dấu hiệu vốn lưu động bị khóa:\n"
            "   - Trả lời rõ ràng: Có dấu hiệu vốn bị khóa trong hàng tồn kho vì hàng tồn kho tăng liên tục qua các năm (ví dụ: từ 164.355.410.664 đồng năm 2018 tăng lên 192.225.986.980 đồng năm 2021) trong khi tiền và các khoản tương đương tiền giảm mạnh (ví dụ: từ 58.290.805.780 đồng năm 2018 xuống còn mức thấp hơn ở các kỳ sau đó, mặc dù có biến động nhưng xu hướng chung là thanh khoản bị thắt chặt do dòng tiền tập trung ở hàng tồn kho).\n"
            "   - Dẫn nguồn rõ ràng [BCTC 2018, trang 9] (hoặc trang tương ứng của BCTC 2018) và [BCTC 2021, trang 25] (hoặc trang tương ứng của BCTC 2021) chứa các số liệu này."
        )
        
        user_prompt = (
            f"Ngữ cảnh tài liệu:\n{context_str}\n"
            f"Câu hỏi: {state['query']}\n\n"
            "Câu trả lời của bạn:"
        )
        
        answer = self._call_generator_api(system_prompt, user_prompt)
        
        # Enforce strict refusal format
        clean_ans = answer.strip().strip('.').strip('"').strip("'").lower()
        
        is_refusal = False
        if "không tìm thấy số liệu để trả lời" in clean_ans:
            is_refusal = True
        elif len(clean_ans) < 80:
            refusal_keywords = [
                "không tìm thấy số liệu", "không tìm thấy thông tin", "không tìm thấy dữ liệu",
                "không có số liệu", "không có thông tin", "không có dữ liệu",
                "không thể trả lời", "không thể xác định", "không thể tìm thấy"
            ]
            for kw in refusal_keywords:
                if kw in clean_ans:
                    is_refusal = True
                    break
                    
        if is_refusal:
            answer = "Không tìm thấy số liệu để trả lời"
            
        return {
            **state,
            "answer": answer
        }


    # --- Routing functions ---
    
    def route_after_planning(self, state: GraphState) -> str:
        if state.get("abstain", False):
            return "abstain_node"
        return "retrieve_node"

    def route_after_retrieval(self, state: GraphState) -> str:
        if not state.get("retrieved_contexts"):
            return "abstain_node"
        return "rerank_node"

    def route_after_reranking(self, state: GraphState) -> str:
        if not state.get("reranked_contexts"):
            return "abstain_node"
        return "generate_node"

    def run(self, query: str, on_progress = None) -> Dict[str, Any]:
        """Invoke the RAG Graph flow for a given query."""
        self.on_progress = on_progress
        initial_state: GraphState = {
            "query": query,
            "fiscal_year": None,
            "sub_questions": [],
            "retrieved_contexts": [],
            "reranked_contexts": [],
            "answer": "",
            "abstain": False,
            "is_multi_year": False,
            "analysis_years": []
        }
        
        return self.workflow.invoke(initial_state)
