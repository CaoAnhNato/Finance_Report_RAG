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
        "Hãy viết tóm tắt điều hành (Executive Summary) cho báo cáo tài chính của Công ty Cổ phần 32 (A32), "
        "nêu rõ mục tiêu báo cáo, tổng quan doanh nghiệp, và các kết quả tài chính nổi bật trong giai đoạn 2017-2025. "
        "Cấu trúc gồm 1) Insight chính, 2) Bằng chứng số liệu."
    ),
    "business_performance": (
        "Phân tích kết quả kinh doanh A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về doanh thu và LNST; "
        "2) các mốc bất thường như 2020, 2021, 2025; "
        "3) bằng chứng số liệu ngắn gọn; "
        "4) diễn giải ý nghĩa tài chính; "
        "5) Diễn giải sau biểu đồ để chốt insight. "
        "Không bịa số liệu, chỉ dùng dữ liệu trong báo cáo."
    ),
    "assets_structure": (
        "Phân tích cơ cấu và biến động tài sản ngắn hạn và dài hạn của A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về tỷ trọng tài sản ngắn hạn/dài hạn; "
        "2) bằng chứng số liệu ngắn gọn; "
        "3) Diễn giải sau biểu đồ để chốt ý nghĩa cơ cấu tài sản. "
        "Không bịa số liệu."
    ),
    "working_capital": (
        "Phân tích hiệu quả quản lý vốn lưu động của A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về biến động hàng tồn kho và các khoản phải thu ngắn hạn; "
        "2) bằng chứng số liệu ngắn gọn (đặc biệt đỉnh tồn kho 2021 và phải thu tăng mạnh 2025); "
        "3) Diễn giải sau biểu đồ để chốt ý nghĩa quản trị vốn lưu động. "
        "Không bịa số liệu."
    ),
    "capital_structure": (
        "Phân tích cơ cấu nguồn vốn của A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về tỷ lệ nợ phải trả so với vốn chủ sở hữu và tính chất nợ vay không chịu lãi; "
        "2) bằng chứng số liệu ngắn gọn; "
        "3) Diễn giải sau biểu đồ để chốt ý nghĩa cơ cấu nguồn vốn. "
        "Không bịa số liệu."
    ),
    "liquidity_ratios": (
        "Phân tích các chỉ số thanh khoản của A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về hệ số thanh toán hiện thời (>1.0) và hệ số thanh toán nhanh (<1.0 do tồn kho); "
        "2) bằng chứng số liệu ngắn gọn; "
        "3) Diễn giải sau biểu đồ để chốt ý nghĩa thanh khoản. "
        "Không bịa số liệu."
    ),
    "cash_flow": (
        "Phân tích lưu chuyển tiền tệ (dòng tiền) của A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
        "1) Insight chính về thặng dư dòng tiền kinh doanh (CFO) dương và dòng tiền tài chính âm do trả cổ tức đều đặn; "
        "2) bằng chứng số liệu ngắn gọn; "
        "3) Diễn giải sau biểu đồ để chốt ý nghĩa dòng tiền. "
        "Không bịa số liệu."
    ),
    "conclusions": (
        "Hãy đưa ra kết luận tổng quan về sức khỏe tài chính của A32 và khuyến nghị đầu tư/quản trị, "
        "kèm theo phân tích biên lợi nhuận ròng (Net Margin) qua các năm: "
        "1) Insight chính về hiệu quả sinh lời và biên lợi nhuận; "
        "2) bằng chứng số liệu ngắn gọn; "
        "3) Diễn giải sau biểu đồ để chốt khuyến nghị."
    )
}

SECTION_TITLES = {
    "executive_summary": "Tóm tắt Điều hành",
    "business_performance": "Kết quả Hoạt động Kinh doanh",
    "assets_structure": "Cơ cấu và Biến động Tài sản",
    "working_capital": "Khả năng Quản lý Vốn lưu động",
    "capital_structure": "Cơ cấu Nguồn vốn",
    "liquidity_ratios": "Khả năng Thanh khoản",
    "cash_flow": "Dòng tiền tệ",
    "conclusions": "Kết luận & Khuyến nghị"
}

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
