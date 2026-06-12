"""
Runner để sinh báo cáo A32_Financial_Report_v2.html (RAG mode, không fallback).
Đây là phiên bản v2 - lưu song song với v1 để so sánh.
"""
import os
import sys
import json
import logging
import time
from pathlib import Path

# Configure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add root folder to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.rag_report.config import settings
from src.rag_report.query.graph import FinancialRAGGraph
from src.rag_report.exporter.charting import FinancialCharter
from src.rag_report.exporter.exporter import HTMLExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---- Section queries (identical to main flow) ----
QUERIES = {
    "executive_summary": (
        "Viết phần “Tổng quan phân tích” cho báo cáo tài chính của A32. Nội dung cần: "
        "- Nêu nhận định tổng quan về doanh thu, lợi nhuận, dòng tiền, khoản phải thu và thanh khoản trong giai đoạn 2017–2025. "
        "- Không mở đầu bằng việc nói “ngữ cảnh được cung cấp chưa đủ”. "
        "- Nếu dữ liệu thiếu, đưa vào một đoạn/box “Phạm vi và lưu ý dữ liệu” ở cuối phần tổng quan. "
        "- Cấu trúc bắt buộc: "
        "  ### Nhận định tổng quan "
        "  ### Các điểm chính "
        "  ### Phạm vi và lưu ý dữ liệu "
        "- Không dùng heading “Insight chính” hoặc “Bằng chứng số liệu”."
    ),
    "business_performance": (
        "Phân tích kết quả kinh doanh của A32 giai đoạn 2017–2025, tập trung vào doanh thu thuần và lợi nhuận sau thuế. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Các biến động đáng chú ý "
        "  ### Bảng số liệu tóm tắt "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Kết thúc section bằng ý: lợi nhuận cần được đối chiếu với dòng tiền từ hoạt động kinh doanh để đánh giá chất lượng lợi nhuận."
    ),
    "assets_structure": (
        "Phân tích cơ cấu tài sản của A32 giai đoạn 2017–2025. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Cơ sở số liệu "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Tập trung trả lời: tài sản tập trung ở đâu, tỷ trọng tài sản ngắn hạn/dài hạn ra sao, tài sản ngắn hạn có liên quan thế nào đến vốn lưu động và thanh khoản."
    ),
    "working_capital": (
        "Phân tích vốn lưu động của A32 giai đoạn 2017–2025, tập trung vào hàng tồn kho và khoản phải thu. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Diễn biến hàng tồn kho và khoản phải thu "
        "  ### Bảng số liệu tóm tắt "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Dùng thuật ngữ “vốn lưu động bị ứ đọng”, “doanh thu chưa chuyển hóa thành tiền thu về”, “áp lực thu hồi công nợ tăng”. "
        "Không dùng “tiền bị kẹt”, “vốn bị giam”, “bị chiếm dụng vốn” trong câu chính."
    ),
    "capital_structure": (
        "Phân tích nguồn vốn và nợ phải trả của A32 giai đoạn 2017–2025. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Cơ cấu nợ phải trả và vốn chủ sở hữu "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Không kết luận nợ là xấu tuyệt đối. Phân biệt áp lực nợ ngắn hạn, nợ hoạt động và nợ tài chính nếu dữ liệu cho phép."
    ),
    "liquidity_ratios": (
        "Phân tích thanh khoản của A32 giai đoạn 2017–2025. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Bảng hệ số thanh khoản "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Giải thích hệ số thanh toán hiện thời, hệ số thanh toán nhanh, đệm thanh khoản nếu các thuật ngữ này xuất hiện. "
        "Không dùng “doanh nghiệp có đủ tiền xoay xở không”. "
        "Dùng “khả năng đáp ứng nghĩa vụ ngắn hạn”, “đệm thanh khoản”, “áp lực thanh khoản”."
    ),
    "cash_flow": (
        "Phân tích dòng tiền của A32 giai đoạn 2017–2025, tập trung vào CFO, CFI, CFF và mối quan hệ giữa lợi nhuận kế toán và dòng tiền từ hoạt động kinh doanh. "
        "Cấu trúc bắt buộc: "
        "  ### Nhận định chính "
        "  ### Cơ cấu dòng tiền "
        "  ### Đối chiếu lợi nhuận và CFO "
        "  ### Diễn giải tài chính "
        "  ### Nội dung cần theo dõi "
        "Dùng nhất quán “dòng tiền từ hoạt động kinh doanh” hoặc “CFO”. "
        "Không dùng “dòng tiền thật”, “tiền thật”."
    ),
    "conclusions": (
        "Viết phần “Nhận định tổng hợp về sức khỏe tài chính” của A32, kết hợp phân tích biên lợi nhuận ròng nếu có dữ liệu. "
        "Cấu trúc bắt buộc: "
        "  ### Điểm tích cực "
        "  ### Điểm cần theo dõi "
        "  ### Kết luận cân bằng "
        "Không dùng “Khuyến nghị đầu tư” nếu không có cơ sở phân tích đầu tư rõ ràng. "
        "Không dùng “doanh nghiệp khỏe”. "
        "Kết luận phải cân bằng: A32 có tín hiệu phục hồi về kết quả kinh doanh nhưng chất lượng dòng tiền và thanh khoản cần được theo dõi."
    )
}

SECTION_TITLES = {
    "executive_summary": "Tổng quan phân tích",
    "business_performance": "Kết quả kinh doanh",
    "assets_structure": "Cơ cấu tài sản",
    "working_capital": "Vốn lưu động",
    "capital_structure": "Nguồn vốn và nợ phải trả",
    "liquidity_ratios": "Thanh khoản",
    "cash_flow": "Dòng tiền",
    "conclusions": "Nhận định tổng hợp về sức khỏe tài chính"
}

BANNED_REPORT_PHRASES = [
    "Insight chính",
    "Bằng chứng số liệu",
    "Các mốc bất thường",
    "Bằng chứng số liệu ngắn gọn",
    "Diễn giải ý nghĩa tài chính",
    "Diễn giải sau biểu đồ",
    "A32 RAG Platform",
    "RAG Financial",
    "GPT-5.5",
    "DeepSeek",
    "FPT BGE",
    "vNext",
    "v2",
    "tiền thật",
    "doanh nghiệp khỏe",
    "tiền bị kẹt",
    "vốn bị giam"
]

ERROR_TOKENS = ["Đã xảy ra lỗi hệ thống", "lỗi hệ thống"]
MAX_RETRIES = 3
COOL_DOWN = 25  # seconds between sections
RETRY_COOL_DOWN = 30  # seconds before retry

OUTPUT_FILENAME = "A32_Financial_Report_v2.html"


def validate_section(key: str, answer: str) -> bool:
    """Kiểm tra output section có hợp lệ không."""
    if not answer or len(answer.strip()) < 100:
        logger.warning(f"[{key}] Answer too short or empty: '{answer[:80]}'")
        return False
    if any(tok in answer for tok in ERROR_TOKENS):
        logger.warning(f"[{key}] Error token found in answer")
        return False
    # Check for banned phrases
    for phrase in BANNED_REPORT_PHRASES:
        if phrase in answer:
            logger.warning(f"[{key}] Banned phrase detected in answer: '{phrase}'")
    # Must have at least some structure
    if "###" not in answer and len(answer) < 200:
        logger.warning(f"[{key}] Answer lacks structure (no ### headers) and is short")
        return False
    return True


def run_generate_v2():
    logger.info("=" * 60)
    logger.info(f"Bắt đầu sinh báo cáo v2: {OUTPUT_FILENAME}")
    logger.info(f"Model: {settings.REPORT_MODEL} | Rerank Top N: {settings.DEFAULT_RERANK_TOP_N}")
    logger.info("=" * 60)

    # Step 1: Generate charts
    logger.info("\n[STEP 1/3] Generating Altair charts...")
    charter = FinancialCharter()
    charts_dir = os.path.join(settings.PROCESSED_DIR, "charts")
    chart_paths = charter.export_charts_json(charts_dir)
    logger.info(f"  ✅ Charts generated: {list(chart_paths.keys())}")

    # Step 2: Query RAG for each section
    logger.info("\n[STEP 2/3] Querying RAG for all sections...")
    graph = FinancialRAGGraph()
    sections = {}

    query_keys = list(QUERIES.keys())
    for idx, key in enumerate(query_keys):
        query = QUERIES[key]
        title = SECTION_TITLES.get(key, key)
        logger.info(f"\n  [{idx+1}/{len(query_keys)}] Section: {title}")

        result = None
        answer = ""
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                logger.warning(f"  ⚠️ Retry {attempt}/{MAX_RETRIES} for '{key}' after {RETRY_COOL_DOWN}s cooldown...")
                time.sleep(RETRY_COOL_DOWN)
            result = graph.run(query)
            answer = result.get("answer", "")
            if validate_section(key, answer):
                logger.info(f"  ✅ OK - Length: {len(answer)} chars | First 100: {answer[:100].replace(chr(10), ' ')}")
                break
            else:
                logger.warning(f"  ❌ Attempt {attempt}: Invalid answer for '{key}'")

        # Use answer even if invalid (after max retries) to not block pipeline
        sections[key] = answer
        
        # Validate quality standard
        if not validate_section(key, answer):
            logger.error(f"  ⛔ Section '{key}' failed all {MAX_RETRIES} attempts. Using last answer (may be empty/error).")

        # Cool down between sections (not needed after last)
        if idx < len(query_keys) - 1:
            logger.info(f"  ⏳ Cooling down {COOL_DOWN}s before next section...")
            time.sleep(COOL_DOWN)

    # Normalize sections using report_text_editor
    logger.info("\n[STEP 2.5/3] Normalizing all generated sections...")
    from src.rag_report.exporter.report_text_editor import normalize_all_sections
    sections = normalize_all_sections(sections)

    # Step 3: Export to HTML
    logger.info(f"\n[STEP 3/3] Compiling HTML report as: {OUTPUT_FILENAME}")
    exporter = HTMLExporter()
    output_path = exporter.compile_report(sections, chart_paths, OUTPUT_FILENAME)

    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Report v2 generated successfully!")
    logger.info(f"   Output: {output_path}")
    logger.info(f"   Model used: {settings.REPORT_MODEL}")
    logger.info(f"   Rerank Top N: {settings.DEFAULT_RERANK_TOP_N}")

    # Validate output sections
    logger.info("\n=== Section quality check ===")
    all_ok = True
    for key in query_keys:
        ans = sections.get(key, "")
        ok = validate_section(key, ans)
        status = "✅" if ok else "❌"
        logger.info(f"  {status} {key}: {len(ans)} chars")
        if not ok:
            all_ok = False

    if all_ok:
        logger.info("\n✅ All sections passed quality check!")
    else:
        logger.warning("\n⚠️ Some sections may have quality issues - review the report carefully.")

    return output_path


if __name__ == "__main__":
    run_generate_v2()
