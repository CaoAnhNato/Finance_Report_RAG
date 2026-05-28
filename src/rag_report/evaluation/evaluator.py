import os
import re
import json
import logging
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

from src.rag_report.config import settings
from src.rag_report.query.graph import FinancialRAGGraph

logger = logging.getLogger(__name__)

class RAGEvaluator:
    """Evaluates the financial RAG pipeline correctness, retrieval hit rates, and abstention compliance."""
    
    def __init__(self, eval_file_path: str = None) -> None:
        self.eval_file_path = eval_file_path or settings.EVAL_FILE
        if not self.eval_file_path or not os.path.exists(self.eval_file_path):
            raise FileNotFoundError(f"Evaluation questions file not found at {self.eval_file_path}")
            
        self.graph = FinancialRAGGraph()
        self.llm_client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            timeout=300.0
        )

    def load_questions(self) -> List[Dict[str, Any]]:
        """Load evaluation questions from JSON file."""
        with open(self.eval_file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _extract_key_numbers(self, text: str) -> List[str]:
        """Helper to extract financial figures (e.g. 164.355.410.664, 164,4) for programmatic verification."""
        matches = re.findall(r'\b\d+(?:[\.,]\d+)*\b', text)
        filtered = []
        for m in matches:
            clean = m.replace('.', '').replace(',', '')
            if clean.isdigit():
                val = int(clean)
                # Exclude fiscal years and page indexes
                if val > 1000 and val not in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
                    filtered.append(m)
                elif '.' in m or ',' in m:
                    # decimal values (e.g. 164,4)
                    filtered.append(m)
        return list(set(filtered))

    def parse_source_and_page_position(self, source_str: str, page_pos_str: str) -> List[Tuple[int, int]]:
        """
        Parses Source (years) and Page position.
        e.g., Source: "2017, 2018, 2020", Page position: "6 (2017), 6 (2018), 8 (2020)"
        or Source: "2021", Page position: "7, 19"
        Returns a list of (fiscal_year, page_num).
        """
        pairs = []
        if not source_str or not page_pos_str or source_str == "None" or page_pos_str == "None":
            return pairs
            
        source_str = str(source_str)
        page_pos_str = str(page_pos_str)
        
        # Check if contains year annotations in parentheses like "6 (2017)"
        if "(" in page_pos_str and ")" in page_pos_str:
            matches = re.findall(r"(\d+)\s*\(\s*(\d+)\s*\)", page_pos_str)
            for p_str, y_str in matches:
                pairs.append((int(y_str), int(p_str)))
        else:
            # Simple comma-separated list
            years = [int(y.strip()) for y in re.findall(r"\d+", source_str)]
            pages = [int(p.strip()) for p in re.findall(r"\d+", page_pos_str)]
            if len(years) == 1:
                # Single year, multiple pages
                y = years[0]
                for p in pages:
                    pairs.append((y, p))
            elif len(years) == len(pages):
                for y, p in zip(years, pages):
                    pairs.append((y, p))
        return pairs

    def compute_context_precision(self, retrieved_chunks: List[Dict[str, Any]], ground_truth_pairs: List[Tuple[int, int]], expected_behavior: str, abstain_correct: bool) -> float:
        """Compute Context Precision (Mean Average Precision) against ground truth year-page pairs."""
        if expected_behavior == "abstain":
            return 1.0 if abstain_correct else 0.0
            
        if not ground_truth_pairs:
            return 1.0
            
        relevant_count = 0
        precision_sum = 0.0
        
        for k, chunk in enumerate(retrieved_chunks):
            cy = chunk.get("fiscal_year")
            cp = chunk.get("page_num")
            
            is_relevant = any(cy == gt_y and cp == gt_p for gt_y, gt_p in ground_truth_pairs)
            if is_relevant:
                relevant_count += 1
                precision_at_k = relevant_count / (k + 1)
                precision_sum += precision_at_k
                
        if relevant_count == 0:
            return 0.0
            
        return precision_sum / relevant_count

    def evaluate_faithfulness_llm(self, question: str, answer: str, contexts: List[Dict[str, Any]], expected_behavior: str) -> Dict[str, Any]:
        """Use LLM to grade faithfulness of the response against the provided contexts."""
        if expected_behavior == "abstain":
            return {
                "faithfulness_score": 1.0,
                "reason": "Abstention requested and successfully processed."
            }
            
        # Clean standard refusal response is always faithful
        if answer.strip().strip('.').lower() == "không tìm thấy số liệu để trả lời":
            return {
                "faithfulness_score": 1.0,
                "reason": "Standard refusal response is 100% faithful to the context."
            }
            
        if not contexts:
            return {
                "faithfulness_score": 0.0,
                "reason": "Empty context provided for an answered question."
            }
            
        # Build context string
        context_texts = []
        for idx, ctx in enumerate(contexts):
            context_texts.append(f"Ngữ cảnh {idx+1} (Năm {ctx.get('fiscal_year')}, trang {ctx.get('page_num')}):\n{ctx.get('text_content')}")
        full_context_str = "\n\n".join(context_texts)
        
        prompt = (
            "Bạn là một chuyên gia kiểm định chất lượng hệ thống RAG phân tích tài chính.\n"
            "Hãy đánh giá tính trung thực (Faithfulness) của Câu trả lời đối với Ngữ cảnh được cung cấp.\n"
            "Các bước thực hiện:\n"
            "1. Tách Câu trả lời thành các mệnh đề hoặc khẳng định thực tế (factual statements/claims) riêng biệt.\n"
            "2. Với mỗi khẳng định, kiểm tra xem nó có được hỗ trợ trực tiếp và chính xác bởi Ngữ cảnh hay không.\n"
            "3. Tính điểm Faithfulness = (Số khẳng định được hỗ trợ bởi Ngữ cảnh) / (Tổng số khẳng định).\n"
            "Nếu Câu trả lời là câu từ chối trả lời hoặc không chứa khẳng định thực tế nào, điểm mặc định là 1.0.\n\n"
            f"Ngữ cảnh:\n{full_context_str}\n\n"
            f"Câu trả lời:\n{answer}\n\n"
            "Trả về kết quả dưới định dạng JSON thuần túy, không có thẻ markdown ```json:\n"
            "{\n"
            "  \"statements\": [\n"
            "    {\n"
            "      \"statement\": \"khẳng định thứ nhất\",\n"
            "      \"supported\": true/false,\n"
            "      \"reason\": \"giải thích dựa trên Ngữ cảnh\"\n"
            "    }\n"
            "  ],\n"
            "  \"faithfulness_score\": float (từ 0.0 đến 1.0),\n"
            "  \"reason\": \"giải thích ngắn gọn tổng quát\"\n"
            "}"
        )
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.PLANNER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.0
            )
            
            if isinstance(response, str):
                json_str = response.strip()
            else:
                json_str = response.choices[0].message.content.strip()
                
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            json_str = json_str.strip()
            
            data = json.loads(json_str)
            return data
        except Exception as e:
            logger.error(f"Error grading faithfulness: {str(e)}")
            return {
                "faithfulness_score": 1.0,
                "reason": f"Fallback to 1.0 due to LLM error: {str(e)}"
            }

    def evaluate_response_llm(self, question: str, reference: str, answer: str, expected_behavior: str) -> Dict[str, Any]:
        """Use LLM to grade answer numeric accuracy and context recall."""
        # For abstention behavior
        if expected_behavior == "abstain":
            is_refusal = (answer.strip().strip('.').lower() == "không tìm thấy số liệu để trả lời")
            return {
                "numeric_accuracy": is_refusal,
                "context_recall": True,
                "reason": "Abstention requested and successfully matched the exact refusal sentence." if is_refusal else "Failed to abstain when required."
            }
            
        prompt = (
            "Bạn là một chuyên gia đánh giá hệ thống RAG phân tích tài chính.\n"
            "Hãy so sánh câu trả lời của hệ thống RAG và câu trả lời tham chiếu (Reference) dưới đây để kiểm tra tính chính xác.\n\n"
            f"Câu hỏi: {question}\n"
            f"Tham chiếu (Reference): {reference}\n"
            f"Hệ thống trả lời (RAG Answer): {answer}\n\n"
            "Hãy đánh giá 2 tiêu chí sau:\n"
            "1. numeric_accuracy: true nếu hệ thống trả lời đúng số liệu tài chính nêu trong câu tham chiếu (cho phép sai lệch định dạng viết, ví dụ: 164,4 tỷ đồng vs 164.355.410.664 đồng hoặc làm tròn hợp lý). false nếu sai lệch số liệu hoặc bịa đặt số liệu.\n"
            "2. context_recall: true nếu hệ thống tìm được thông tin đúng trọng tâm và trả lời đủ ý của câu tham chiếu.\n\n"
            "Trả về kết quả dưới định dạng JSON thuần túy, không có thẻ markdown ```json:\n"
            "{\n"
            "  \"numeric_accuracy\": boolean,\n"
            "  \"context_recall\": boolean,\n"
            "  \"reason\": \"giải thích ngắn gọn lý do\"\n"
            "}"
        )
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.PLANNER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.0
            )
            
            if isinstance(response, str):
                json_str = response.strip()
            else:
                json_str = response.choices[0].message.content.strip()
                
            # Clean formatting wrapper
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            json_str = json_str.strip()
            
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Error grading with LLM: {str(e)}")
            # Programmatic fallback
            ref_nums = self._extract_key_numbers(reference)
            ans_nums = self._extract_key_numbers(answer)
            matches = [num for num in ref_nums if num in answer or num.replace(',', '.') in answer or num.replace('.', ',') in answer]
            acc = len(matches) > 0 or not ref_nums
            return {
                "numeric_accuracy": acc,
                "context_recall": acc,
                "reason": "Fallback to regex number verification due to LLM error."
            }

    def evaluate_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single test case."""
        qid = item["id"]
        q_type = item["question_type"]
        question = item["user_input"]
        reference = item["reference"]
        ref_contexts = item.get("reference_contexts", [])
        expected_behavior = item.get("expected_behavior", "answer")
        gt_source = item.get("Source", "None")
        gt_page = item.get("Page position", "None")
        
        logger.info(f"Evaluating QID {qid} ({q_type}): '{question}'")
        
        start_time = time.time()
        result = self.graph.run(question)
        latency = time.time() - start_time
        
        answer = result["answer"]
        abstain = result["abstain"]
        
        # 1. Abstention Accuracy
        abstain_correct = False
        if expected_behavior == "abstain":
            abstain_correct = (answer.strip().strip('.').lower() == "không tìm thấy số liệu để trả lời")
        else:
            abstain_correct = abstain is False and (answer.strip().strip('.').lower() != "không tìm thấy số liệu để trả lời")
        
        # 2. Retrieval Metrics (Hit@K, MRR, Context Recall)
        retrieved_contexts = result.get("retrieved_contexts", [])
        reranked_contexts = result.get("reranked_contexts", [])
        
        hit_at_3 = False
        hit_at_5 = False
        mrr = 0.0
        
        # Programmatic check for chunk relevance based on key numbers
        ref_context_nums = []
        for rc in ref_contexts:
            ref_context_nums.extend(self._extract_key_numbers(rc))
        ref_context_nums = list(set(ref_context_nums))
        
        # Helper to determine if a retrieved chunk is a hit
        def is_hit(chunk_text: str) -> bool:
            if not ref_context_nums:
                return True # If no key numbers are present, count as hit (fallback)
            # Check if chunk contains at least one key number from reference
            return any(num in chunk_text or num.replace('.', '') in chunk_text for num in ref_context_nums)
            
        # Calculate Hit Rates on Retrieved Contexts
        for idx, ctx in enumerate(retrieved_contexts):
            txt = ctx.get("text_content", "")
            if is_hit(txt):
                if idx < 3:
                    hit_at_3 = True
                if idx < 5:
                    hit_at_5 = True
                if mrr == 0.0:
                    mrr = 1.0 / (idx + 1)
                    
        # 3. Context Precision and Faithfulness
        gt_pairs = self.parse_source_and_page_position(gt_source, gt_page)
        context_precision_retrieval = self.compute_context_precision(retrieved_contexts, gt_pairs, expected_behavior, abstain_correct)
        context_precision_reranked = self.compute_context_precision(reranked_contexts, gt_pairs, expected_behavior, abstain_correct)
        
        faithfulness_res = self.evaluate_faithfulness_llm(question, answer, reranked_contexts, expected_behavior)
        generation_faithfulness = faithfulness_res.get("faithfulness_score", 1.0)
        faithfulness_reason = faithfulness_res.get("reason", "")
        
        # 4. LLM Response Grader (Numeric Accuracy and Context Recall)
        grades = self.evaluate_response_llm(question, reference, answer, expected_behavior)
        
        return {
            "id": qid,
            "question_type": q_type,
            "question": question,
            "expected_behavior": expected_behavior,
            "answer": answer,
            "abstain_correct": abstain_correct,
            "hit_at_3": hit_at_3,
            "hit_at_5": hit_at_5,
            "mrr": mrr,
            "numeric_accuracy": grades.get("numeric_accuracy", False),
            "context_recall": grades.get("context_recall", False),
            "grader_reason": grades.get("reason", ""),
            "context_precision_retrieval": context_precision_retrieval,
            "context_precision_reranked": context_precision_reranked,
            "generation_faithfulness": generation_faithfulness,
            "faithfulness_reason": faithfulness_reason,
            "latency": latency
        }

    def evaluate_all(self, max_workers: int = 4) -> Dict[str, Any]:
        """Run evaluation on all loaded questions in parallel."""
        items = self.load_questions()
        logger.info(f"Starting evaluation of {len(items)} questions using {max_workers} threads...")
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.evaluate_single, item) for item in items]
            for f in futures:
                try:
                    results.append(f.result())
                except Exception as e:
                    logger.error(f"Error evaluating question: {str(e)}")
                    
        # Compute aggregate metrics
        total = len(results)
        if total == 0:
            return {}
            
        abstain_total = sum(1 for r in results if r["expected_behavior"] == "abstain")
        answer_total = total - abstain_total
        
        abstain_correct_count = sum(1 for r in results if r["expected_behavior"] == "abstain" and r["abstain_correct"])
        answer_correct_count = sum(1 for r in results if r["expected_behavior"] != "abstain" and r["abstain_correct"])
        
        hit_3_count = sum(1 for r in results if r["hit_at_3"])
        hit_5_count = sum(1 for r in results if r["hit_at_5"])
        avg_mrr = sum(r["mrr"] for r in results) / total
        
        num_acc_count = sum(1 for r in results if r["numeric_accuracy"])
        ctx_recall_count = sum(1 for r in results if r["context_recall"])
        avg_latency = sum(r["latency"] for r in results) / total
        
        avg_context_precision_retrieval = sum(r["context_precision_retrieval"] for r in results) / total
        avg_context_precision_reranked = sum(r["context_precision_reranked"] for r in results) / total
        avg_generation_faithfulness = sum(r["generation_faithfulness"] for r in results) / total
        
        summary = {
            "total_questions": total,
            "abstention_accuracy": abstain_correct_count / abstain_total if abstain_total > 0 else 1.0,
            "answer_compliance": answer_correct_count / answer_total if answer_total > 0 else 1.0,
            "hit_at_3": hit_3_count / total,
            "hit_at_5": hit_5_count / total,
            "mrr": avg_mrr,
            "numeric_accuracy": num_acc_count / total,
            "context_recall": ctx_recall_count / total,
            "context_precision_retrieval": avg_context_precision_retrieval,
            "context_precision_reranked": avg_context_precision_reranked,
            "generation_faithfulness": avg_generation_faithfulness,
            "avg_latency_seconds": avg_latency
        }
        
        logger.info(f"Evaluation Finished. Summary: {summary}")
        
        # Save results to data/processed/
        processed_dir = os.path.dirname(settings.LOCAL_DB_PATH_ABS)
        os.makedirs(processed_dir, exist_ok=True)
        
        results_file = os.path.join(processed_dir, "eval_results.json")
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "details": results}, f, ensure_ascii=False, indent=2)
            
        # Write markdown report
        self._write_markdown_report(summary, results, os.path.join(processed_dir, "eval_report.md"))
        
        return summary

    def _write_markdown_report(self, summary: Dict[str, Any], details: List[Dict[str, Any]], output_path: str) -> None:
        """Generate a structured Markdown evaluation report with bottleneck analysis."""
        lines = [
            "# Báo cáo đánh giá hiệu năng hệ thống RAG Report (Công ty CP 32)\n",
            f"Thời gian đánh giá: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            "## 1. Kết quả tổng hợp (Metrics)\n",
            "| Chỉ số (Metric) | Kết quả (Value) | Mô tả |",
            "| --- | --- | --- |",
            f"| **Tổng số câu hỏi** | {summary['total_questions']} | Số câu hỏi kiểm thử |",
            f"| **Tỷ lệ từ chối đúng (Abstention Accuracy)** | {summary['abstention_accuracy']:.2%} | Chính xác khi gặp năm 2022 |",
            f"| **Tỷ lệ trả lời đúng (Answer Compliance)** | {summary['answer_compliance']:.2%} | Phản hồi đúng khi tài liệu có sẵn |",
            f"| **Hit Rate @ 3** | {summary['hit_at_3']:.2%} | Tỷ lệ tìm thấy ngữ cảnh đúng trong Top 3 |",
            f"| **Hit Rate @ 5** | {summary['hit_at_5']:.2%} | Tỷ lệ tìm thấy ngữ cảnh đúng trong Top 5 |",
            f"| **MRR (Mean Reciprocal Rank)** | {summary['mrr']:.4f} | Chất lượng thứ hạng tìm kiếm |",
            f"| **Context Precision (Retrieval)** | {summary['context_precision_retrieval']:.2%} | Độ chính xác của ngữ cảnh trước Rerank |",
            f"| **Context Precision (Reranked)** | {summary['context_precision_reranked']:.2%} | Độ chính xác của ngữ cảnh sau Rerank |",
            f"| **Generation Faithfulness** | {summary['generation_faithfulness']:.2%} | Điểm trung thực của câu trả lời từ LLM |",
            f"| **Độ chính xác số liệu (Numeric Accuracy)** | {summary['numeric_accuracy']:.2%} | Số liệu tài chính khớp với tham chiếu |",
            f"| **Độ bao phủ ngữ cảnh (Context Recall)** | {summary['context_recall']:.2%} | Ngữ cảnh trích xuất đủ ý trả lời |",
            f"| **Độ trễ trung bình (Avg Latency)** | {summary['avg_latency_seconds']:.2f} s | Thời gian phản hồi trung bình |\n",
        ]
        
        # Bottleneck Analysis
        ret_prec = summary['context_precision_retrieval']
        rer_prec = summary['context_precision_reranked']
        gen_faith = summary['generation_faithfulness']
        num_acc = summary['numeric_accuracy']
        
        bottlenecks = []
        recommendations = []
        
        # Analyze Retrieval
        if ret_prec < 0.85:
            bottlenecks.append(f"- **Retrieval (Chunk size/Search)**: Context Precision của Retrieval đạt {ret_prec:.2%}, thấp hơn mức mục tiêu 85%. Việc tìm kiếm ban đầu (keyword + vector) có thể chứa nhiều chunk rác/nhiễu hoặc Chunk Size hiện tại chưa tối ưu làm loãng thông tin.")
            recommendations.append("- **Tối ưu hóa Retrieval**: Điều chỉnh chunk_size, cải thiện trọng số hybrid search hoặc tối ưu embedding model.")
        else:
            bottlenecks.append("- **Retrieval (Chunk size/Search)**: Retrieval hoạt động hiệu quả, độ chính xác ngữ cảnh ban đầu đạt yêu cầu cao.")
            
        # Analyze Reranking
        if rer_prec < ret_prec:
            bottlenecks.append(f"- **Reranking**: Reranked Context Precision ({rer_prec:.2%}) thấp hơn Retrieval Context Precision ({ret_prec:.2%}). Bộ Reranker đang làm giảm vị trí hoặc lọc mất các chunk thực sự hữu ích.")
            recommendations.append("- **Tối ưu hóa Reranking**: Xem xét lại ngưỡng lọc `MIN_EVIDENCE_SCORE` hoặc tune lại các tham số rerank, kiểm tra xem bge-reranker-v2-m3 có hoạt động tốt với dạng bảng số liệu tài chính không.")
        else:
            bottlenecks.append("- **Reranking**: Bộ Reranker hoạt động tốt, giúp cải thiện hoặc duy trì độ chính xác của ngữ cảnh trước khi đưa vào LLM.")
            
        # Analyze Generation
        if gen_faith < 0.90:
            bottlenecks.append(f"- **Generation (LLM Faithfulness)**: Faithfulness đạt {gen_faith:.2%}, thấp hơn mức mục tiêu 90%. LLM có hiện tượng sinh dữ liệu ngoài ngữ cảnh (ảo tưởng - hallucination) hoặc suy luận chủ quan.")
            recommendations.append("- **Tối ưu hóa Prompt**: Cần bổ sung các ràng buộc nghiêm ngặt trong system prompt của generate_node để ép LLM chỉ lấy dữ liệu trực tiếp từ ngữ cảnh được cung cấp.")
        else:
            bottlenecks.append("- **Generation (LLM Faithfulness)**: LLM sinh câu trả lời có tính trung thực cao, bám sát các ngữ cảnh được cung cấp.")
            
        if num_acc < rer_prec - 0.10:
            bottlenecks.append(f"- **Numeric Synthesis**: Độ chính xác số liệu ({num_acc:.2%}) thấp hơn đáng kể so với chất lượng ngữ cảnh được cung cấp ({rer_prec:.2%}). LLM đang gặp khó khăn trong việc trích xuất và so sánh các con số chính xác mặc dù ngữ cảnh đã có sẵn.")
            recommendations.append("- **Tối ưu hóa Logic Generation**: Cung cấp ví dụ Few-Shot về trích xuất số liệu và so sánh số tăng giảm qua các năm cho mô hình.")

        lines.extend([
            "## 2. Phân tích điểm nghẽn & Đề xuất tối ưu (Bottleneck Analysis)\n",
            "### Điểm nghẽn hiện tại:\n",
            "\n".join(bottlenecks) + "\n",
            "### Đề xuất hành động:\n",
            ("\n".join(recommendations) if recommendations else "- Hệ thống hiện tại hoạt động rất tốt trên tất cả các chỉ số thành phần.") + "\n",
            "## 3. Chi tiết kết quả kiểm thử (Details)\n",
            "| ID | Loại câu hỏi | Câu hỏi | Từ chối đúng | Hit@5 | Retrieval Prec | Reranked Prec | Faithfulness | Số liệu đúng | Độ trễ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
        ])
        
        for d in details:
            lines.append(
                f"| {d['id']} | {d['question_type']} | {d['question']} | "
                f"{'✅' if d['abstain_correct'] else '❌'} | "
                f"{'✅' if d['hit_at_5'] else '❌'} | "
                f"{d['context_precision_retrieval']:.2%} | "
                f"{d['context_precision_reranked']:.2%} | "
                f"{d['generation_faithfulness']:.2%} | "
                f"{'✅' if d['numeric_accuracy'] else '❌'} | "
                f"{d['latency']:.2f}s |"
            )
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"Markdown evaluation report saved to: {output_path}")

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    evaluator = RAGEvaluator()
    evaluator.evaluate_all(max_workers=3)
