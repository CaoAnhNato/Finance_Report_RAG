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
            base_url=settings.OPENAI_API_BASE,
            timeout=300.0
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
            "  \"abstain\": boolean (chỉ đặt thành true nếu câu hỏi yêu cầu dữ liệu hoặc phân tích trực tiếp và duy nhất về năm 2022. Chú ý: Năm 2022 công ty không công bố báo cáo tài chính),\n"
            "  \"is_multi_year\": boolean (true nếu so sánh, phân tích xu hướng giữa các năm tài chính),\n"
            "  \"analysis_years\": [int] (danh sách tất cả các năm tài chính xuất hiện hoặc cần thiết cho phân tích)\n"
            "}\n\n"
            "Quy tắc đặc biệt:\n"
            "1. Chỉ đặt abstain là true nếu câu hỏi hỏi trực tiếp và duy nhất về năm 2022 (ví dụ: 'Hàng tồn kho năm 2022 là bao nhiêu?'). KHÔNG đặt abstain là true đối với các câu hỏi phân tích xu hướng hoặc so sánh qua nhiều năm có chứa năm 2022 (ví dụ: 'giai đoạn 2021-2025').\n"
            "2. Trả về định dạng JSON thuần túy, không có thẻ markdown ```json.\n"
            "3. Đối với các câu hỏi không nêu rõ năm cụ thể nhưng có tính chất phân tích tổng thể hoặc trích xuất dấu hiệu/vấn đề xuyên suốt báo cáo (ví dụ: 'dấu hiệu vốn lưu động bị khóa', 'tình hình công nợ'), hãy đặt `is_multi_year` là true và `analysis_years` gồm tất cả các năm có dữ liệu báo cáo: [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]."
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
            
            # Extra safety check: only force abstain if 2022 is mentioned and there are no other years.
            # If there are other years, it is a multi-year query and we should not abstain.
            if "2022" in query or 2022 in plan.analysis_years:
                has_other_years = any(str(y) in query for y in [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]) or len([y for y in plan.analysis_years if y != 2022]) > 0
                if not has_other_years:
                    plan.abstain = True
                else:
                    plan.abstain = False
                    
            # Programmatic fallback: if no fiscal year is mentioned in the query and none was detected,
            # default to querying all years to guarantee we don't miss context for general questions (like working capital lock).
            import re
            matches = re.findall(r'\b(20\d{2})\b', query)
            query_years = [int(m) for m in matches if int(m) in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]]
            if not query_years and not plan.fiscal_year and not plan.analysis_years and not plan.abstain:
                plan.is_multi_year = True
                plan.analysis_years = [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]
                logger.info("Programmatic fallback triggered: query is year-agnostic, defaulting to all available years.")
                
            logger.info(f"Query plan generated: {plan.model_dump()}")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate query plan: {str(e)}")
            # Fallback plan
            import re
            matches = re.findall(r'\b(20\d{2})\b', query)
            query_years = [int(m) for m in matches if int(m) in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]]
            abstain = "2022" in query and not any(str(y) in query for y in [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025])
            
            is_multi = False
            analysis_y = []
            if not query_years and not abstain:
                is_multi = True
                analysis_y = [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]
                
            return QueryPlan(
                fiscal_year=None,
                sub_questions=[query],
                abstain=abstain,
                is_multi_year=is_multi,
                analysis_years=analysis_y
            )
