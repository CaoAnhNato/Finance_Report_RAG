import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from openai import OpenAI

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
            base_url=settings.OPENAI_API_BASE
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
        plan = self.planner.plan_query(state["query"])
        
        return {
            **state,
            "fiscal_year": plan.fiscal_year,
            "sub_questions": plan.sub_questions,
            "abstain": plan.abstain,
            "is_multi_year": plan.is_multi_year,
            "analysis_years": plan.analysis_years
        }

    def retrieve_node(self, state: GraphState) -> GraphState:
        """Retrieves contexts using RRF Hybrid search across sub-questions and target years."""
        logger.info("--- RETRIEVE NODE ---")
        if state.get("abstain", False):
            return state
            
        is_multi_year = state.get("is_multi_year", False)
        analysis_years = state.get("analysis_years", [])
        sub_questions = state.get("sub_questions", [state["query"]])
        
        retrieved = []
        seen_chunk_ids = set()
        
        # Multi-year query: query each year separately and merge results
        if is_multi_year and analysis_years:
            logger.info(f"Retrieving contexts for multi-year analysis: {analysis_years}")
            for year in analysis_years:
                year_results = self.retriever.retrieve_for_questions(
                    sub_questions,
                    fiscal_year=year,
                    vector_top_k=20,
                    keyword_top_k=20
                )
                for r in year_results:
                    if r["chunk_id"] not in seen_chunk_ids:
                        seen_chunk_ids.add(r["chunk_id"])
                        retrieved.append(r)
        else:
            # Single year or unspecified query
            fiscal_year = state.get("fiscal_year")
            logger.info(f"Retrieving contexts for year: {fiscal_year}")
            retrieved = self.retriever.retrieve_for_questions(
                sub_questions,
                fiscal_year=fiscal_year
            )
            
        logger.info(f"Total chunks retrieved: {len(retrieved)}")
        return {
            **state,
            "retrieved_contexts": retrieved
        }

    def rerank_node(self, state: GraphState) -> GraphState:
        """Reranks retrieved contexts using FPT Cloud Reranker."""
        logger.info("--- RERANK NODE ---")
        if state.get("abstain", False) or not state.get("retrieved_contexts"):
            return state
            
        reranked = self.reranker.rerank_contexts(
            query=state["query"],
            contexts=state["retrieved_contexts"],
            top_n=settings.DEFAULT_RERANK_TOP_N,
            min_score=settings.MIN_EVIDENCE_SCORE
        )
        
        return {
            **state,
            "reranked_contexts": reranked
        }

    def abstain_node(self, state: GraphState) -> GraphState:
        """Sets the standardized refusal/abstention response."""
        logger.info("--- ABSTAIN NODE ---")
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
            "4. Câu trả lời viết bằng tiếng Việt, cấu trúc mạch lạc, sử dụng bảng biểu markdown nếu cần biểu diễn so sánh số liệu."
        )
        
        user_prompt = (
            f"Ngữ cảnh tài liệu:\n{context_str}\n"
            f"Câu hỏi: {state['query']}\n\n"
            "Câu trả lời của bạn:"
        )
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.REPORT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0
            )
            
            if isinstance(response, str):
                answer = response.strip()
            else:
                answer = response.choices[0].message.content.strip()
                
            return {
                **state,
                "answer": answer
            }
        except Exception as e:
            logger.error(f"Failed to generate answer: {str(e)}")
            return {
                **state,
                "answer": "Đã xảy ra lỗi hệ thống khi sinh câu trả lời."
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

    def run(self, query: str) -> Dict[str, Any]:
        """Invoke the RAG Graph flow for a given query."""
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
