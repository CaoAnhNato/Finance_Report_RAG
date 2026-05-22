import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

from src.rag_report.config import settings

logger = logging.getLogger(__name__)

class QueryPlan(BaseModel):
    fiscal_year: Optional[int] = Field(None, description="Primary fiscal year mentioned in the query (e.g. 2018). None if multi-year or unspecified.")
    sub_questions: List[str] = Field(..., description="1 to 3 search sub-questions to retrieve data from vector and database stores.")
    abstain: bool = Field(..., description="True if query asks for data or analysis of the year 2022, as reports are missing.")
    is_multi_year: bool = Field(..., description="True if comparing or analyzing multiple years.")
    analysis_years: List[int] = Field(..., description="List of all fiscal years involved in the query.")

class QueryPlanner:
    """Uses LLM to analyze the user query and generate a structured search/execution plan."""
    
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        
    def plan_query(self, query: str) -> QueryPlan:
        """Generate a QueryPlan for the user query."""
        logger.info(f"Planning query: '{query}'")
        
        system_prompt = (
            "Bạn là một chuyên gia lập kế hoạch truy xuất cho hệ thống RAG phân tích tài chính.\n"
            "Hãy phân tích câu hỏi của người dùng và trả về một đối tượng JSON tuân thủ schema dưới đây:\n"
            "{\n"
            "  \"fiscal_year\": int hoặc null (năm tài chính chính đang được hỏi, ví dụ: 2018),\n"
            "  \"sub_questions\": [string] (1 đến 3 câu hỏi tìm kiếm ngắn, tập trung vào các số liệu cần tra cứu như tài sản, nợ, doanh thu),\n"
            "  \"abstain\": boolean (chỉ đặt thành true nếu câu hỏi yêu cầu dữ liệu hoặc phân tích trực tiếp về năm 2022. Chú ý: Năm 2022 công ty không công bố báo cáo tài chính),\n"
            "  \"is_multi_year\": boolean (true nếu so sánh, phân tích xu hướng giữa các năm tài chính),\n"
            "  \"analysis_years\": [int] (danh sách tất cả các năm tài chính xuất hiện hoặc cần thiết cho phân tích)\n"
            "}\n\n"
            "Quy tắc đặc biệt:\n"
            "1. Nếu câu hỏi đề cập đến năm 2022 hoặc giai đoạn chứa năm 2022 (ví dụ: 'từ 2020 đến 2023'), đặt abstain là true và đưa 2022 vào analysis_years.\n"
            "2. Trả về định dạng JSON thuần túy, không có thẻ markdown ```json."
        )
        
        try:
            response = self.client.chat.completions.create(
                model=settings.PLANNER_MODEL,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\nCâu hỏi: {query}"}
                ],
                max_tokens=250,
                temperature=0.0
            )
            
            # Support both direct string return and ChatCompletion
            if isinstance(response, str):
                json_str = response.strip()
            else:
                json_str = response.choices[0].message.content.strip()
                
            # Clean markdown code blocks if present
            clean_str = json_str
            if "```json" in clean_str:
                clean_str = clean_str.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_str:
                clean_str = clean_str.split("```")[1].split("```")[0].strip()
            clean_str = clean_str.strip()
            
            data = json.loads(clean_str)
            
            # Map keys to match QueryPlan if there are slight spelling mismatches
            plan = QueryPlan(
                fiscal_year=data.get("fiscal_year"),
                sub_questions=data.get("sub_questions", [query]),
                abstain=data.get("abstain", False),
                is_multi_year=data.get("is_multi_year", False),
                analysis_years=data.get("analysis_years", [])
            )
            
            # Extra safety check: if 2022 is in analysis_years, force abstain
            if 2022 in plan.analysis_years or "2022" in query:
                plan.abstain = True
                
            logger.info(f"Query plan generated: {plan.model_dump()}")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate query plan: {str(e)}")
            # Fallback plan
            return QueryPlan(
                fiscal_year=None,
                sub_questions=[query],
                abstain="2022" in query,
                is_multi_year=False,
                analysis_years=[]
            )
