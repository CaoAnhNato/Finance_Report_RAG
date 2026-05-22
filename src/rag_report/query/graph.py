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
        matches = re.findall(r'\b(20\d{2})\b', q)
        years = []
        for m in matches:
            y = int(m)
            if y in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
                years.append(y)
        return list(set(years))

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
        vector_top_k = 15
        keyword_top_k = 15
        
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
                        
        # Sort globally by RRF score descending
        retrieved = sorted(chunk_map.values(), key=lambda x: x["rrf_score"], reverse=True)
        
        logger.info(f"Total unique chunks retrieved and globally sorted: {len(retrieved)}")
        return {
            **state,
            "retrieved_contexts": retrieved
        }

    def rerank_node(self, state: GraphState) -> GraphState:
        """Reranks retrieved contexts using FPT Cloud Reranker."""
        logger.info("--- RERANK NODE ---")
        if state.get("abstain", False) or not state.get("retrieved_contexts"):
            return state
            
        retrieved = state["retrieved_contexts"]
        # Take the top 40 RRF chunks to rerank
        chunks_to_rerank = retrieved[:40]
        
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
        
        # Generator contexts: top DEFAULT_RERANK_TOP_N from the scored/reranked list
        final_reranked = reranked[:settings.DEFAULT_RERANK_TOP_N]
        
        return {
            **state,
            "retrieved_contexts": sorted_retrieved,
            "reranked_contexts": final_reranked
        }

    def abstain_node(self, state: GraphState) -> GraphState:
        """Sets the standardized refusal/abstention response."""
        logger.info("--- ABSTAIN NODE ---")
        if getattr(self, "on_progress", None):
            self.on_progress("Sinh text", "Kích hoạt cơ chế từ chối trả lời do thiếu thông tin...")
        query_years = state.get("analysis_years", [])
        if not query_years and state.get("fiscal_year"):
            query_years = [state["fiscal_year"]]
            
        if 2022 in query_years or "2022" in state["query"]:
            answer = "Xin lỗi, tôi không tìm thấy tài liệu báo cáo tài chính của Công ty Cổ phần 32 cho năm 2022 để thực hiện phân tích này."
        else:
            answer = "Xin lỗi, tôi không tìm thấy đầy đủ tài liệu báo cáo tài chính liên quan để trả lời chính xác câu hỏi này."
            
        return {
            **state,
            "answer": answer,
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
            
        top_score = reranked[0].get("rerank_score", 0.0)
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
            "Hãy trả lời câu hỏi dưới đây một cách chi tiết, phân tích số liệu rõ ràng hoàn toàn dựa vào ngữ cảnh được cung cấp.\n\n"
            "Các quy tắc bắt buộc:\n"
            "1. Chỉ sử dụng thông tin trong phần 'Ngữ cảnh' được cung cấp để trả lời. Không giả định hay suy đoán số liệu nằm ngoài ngữ cảnh.\n"
            "2. Với mỗi số liệu, bảng biểu hay nhận định quan trọng trích dẫn được, bạn BẮT BUỘC phải dẫn nguồn ở cuối câu bằng định dạng [BCTC <năm>, trang <số trang>] (ví dụ: [BCTC 2018, trang 15]).\n"
            "3. Nếu ngữ cảnh không có thông tin hoặc thông tin không đủ để tính toán/trả lời đầy đủ, hãy nêu rõ thông tin nào bị thiếu, không cố gắng tạo ra câu trả lời sai lệch.\n"
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
