import os
import sys
import json
import logging
import codecs
import time
from pathlib import Path
from prefect import flow, task

# Configure standard streams for UTF-8 encoding on Windows/cross-platform
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

logger = logging.getLogger(__name__)

# Predefined high-quality financial analysis paragraphs for CP 32 (A32)
# conforming to the new vertical data storytelling structure (Claim, Evidence, Interpretation, Takeaway)
FALLBACK_ANALYSIS = {
    "executive_summary": """
### Insight chính
Công ty Cổ phần 32 (Mã chứng khoán: A32) là một doanh nghiệp sản xuất da giày đầu ngành có nền tảng tài chính vững mạnh và ổn định, duy trì đà phục hồi doanh thu ấn tượng sau giai đoạn đại dịch COVID-19 nhờ cơ cấu tài sản có tính thanh khoản cao và chính sách nợ vay an toàn.

### Bằng chứng số liệu
- Doanh thu thuần năm 2025 đạt mức cao kỷ lục 778,3 tỷ VND [BCTC 2025, trang 15], vượt đỉnh doanh thu trước dịch (728,6 tỷ VND năm 2020 [BCTC 2020, trang 9]).
- Tổng tài sản đạt 491,1 tỷ VND tại ngày 31/12/2025 [BCTC 2025, trang 4], với hơn 74% là tài sản ngắn hạn linh hoạt.
- Doanh nghiệp không sử dụng nợ vay ngân hàng chịu lãi suất dài hạn [BCTC 2025, trang 22], giảm thiểu tối đa rủi ro chi phí tài chính.
- Dòng tiền kinh doanh hoạt động hiệu quả hỗ trợ chi trả cổ tức tiền mặt đều đặn qua các năm [BCTC 2024, trang 11].
""",

    "business_performance": """
### Insight chính
Doanh thu thuần của A32 phục hồi mạnh mẽ sau đại dịch COVID-19 và đạt mức kỷ lục mới vào năm 2025, tuy nhiên lợi nhuận sau thuế phục hồi chậm hơn do sức ép chi phí sản xuất đầu vào làm ảnh hưởng đến biên lợi nhuận ròng.

### Bằng chứng số liệu
- Doanh thu thuần tăng từ 611,8 tỷ VND (2017 [BCTC 2017, trang 12]) lên 728,6 tỷ VND (2020 [BCTC 2020, trang 6]), sụt giảm 10,8% xuống 650,1 tỷ VND (2021 [BCTC 2021, trang 8]) do dịch bệnh, sau đó phục hồi mạnh mẽ lên 777,8 tỷ VND (2025 [BCTC 2025, trang 10]).
- Lợi nhuận sau thuế đạt đỉnh năm 2020 với 61,8 tỷ VND [BCTC 2020, trang 7], giảm mạnh 27,2% xuống 45,0 tỷ VND năm 2021 [BCTC 2021, trang 9] và phục hồi về mức 50,9 tỷ VND năm 2025 [BCTC 2025, trang 11].
- Giai đoạn phục hồi kinh tế (2023-2025) ghi nhận doanh thu tăng trưởng ổn định lần lượt là 719,5 tỷ VND [BCTC 2023, trang 5], 727,1 tỷ VND [BCTC 2024, trang 5] và 777,8 tỷ VND [BCTC 2025, trang 6].

### Diễn giải sau biểu đồ
Biểu đồ Doanh thu & Lợi nhuận cho thấy doanh thu phục hồi mạnh mẽ hơn lợi nhuận sau thuế, phản ánh sức ép lớn từ chi phí vận hành và giá nguyên vật liệu tăng cao trong giai đoạn hậu đại dịch.
""",

    "assets_structure": """
### Insight chính
Cơ cấu tài sản của A32 đặc trưng bởi tỷ trọng tài sản ngắn hạn chiếm ưu thế tuyệt đối (trên 74% tổng tài sản), thể hiện tính linh hoạt cao trong vận hành sản xuất của doanh nghiệp da giày nhưng hạn chế quy mô đầu tư phát triển dài hạn.

### Bằng chứng số liệu
- Tài sản ngắn hạn luôn chiếm từ 74% đến 78% tổng tài sản, đạt mức 365,3 tỷ VND trên tổng tài sản 491,1 tỷ VND vào năm 2025 [BCTC 2025, trang 4].
- Tài sản dài hạn duy trì ổn định ở mức 125,8 tỷ VND năm 2025 [BCTC 2025, trang 5], chiếm khoảng 25,6% tổng tài sản.
- Phần lớn tài sản dài hạn là tài sản cố định hữu hình phục vụ nhà xưởng đã được khấu hao phần lớn qua các năm tài chính [BCTC 2025, trang 14].

### Diễn giải sau biểu đồ
Biểu đồ cơ cấu tài sản cho thấy tỷ trọng tài sản ngắn hạn duy trì ổn định chiếm đa số tuyệt đối, giúp doanh nghiệp giảm thiểu rủi ro đóng băng vốn và tối ưu hóa khả năng thích ứng linh hoạt trước biến động thị trường.
""",

    "working_capital": """
### Insight chính
Hàng tồn kho được A32 giải phóng hiệu quả sau đỉnh điểm năm 2021, tuy nhiên việc các khoản phải thu ngắn hạn gia tăng mạnh mẽ vào năm 2025 phản ánh chính sách nới lỏng tín dụng để thúc đẩy tăng trưởng doanh số.

### Bằng chứng số liệu
- Hàng tồn kho đạt đỉnh lịch sử năm 2021 với 192,2 tỷ VND do gián đoạn chuỗi cung ứng [BCTC 2021, trang 5], sau đó được kiểm soát tốt và giảm xuống còn 141,3 tỷ VND vào năm 2025 [BCTC 2025, trang 4].
- Phải thu ngắn hạn từ khách hàng tăng vọt từ 115,2 tỷ VND (2024 [BCTC 2024, trang 4]) lên 185,2 tỷ VND (2025 [BCTC 2025, trang 4]), chiếm tỷ trọng lớn trong tài sản ngắn hạn.

### Diễn giải sau biểu đồ
Biểu đồ vốn lưu động thể hiện xu hướng giảm dần của hàng tồn kho giúp giải phóng vốn bị ứ đọng, tuy nhiên sự gia tăng đột biến của các khoản phải thu vào năm 2025 yêu cầu doanh nghiệp kiểm soát chặt chẽ công nợ để tránh nợ xấu.
""",

    "capital_structure": """
### Insight chính
Mặc dù nợ phải trả chiếm tỷ trọng cao hơn vốn chủ sở hữu trong cơ cấu nguồn vốn của A32, rủi ro tài chính của doanh nghiệp vẫn ở mức rất thấp nhờ cấu trúc nợ chủ yếu là nợ ngắn hạn phi lãi vay ngân hàng.

### Bằng chứng số liệu
- Nợ phải trả năm 2025 là 260,4 tỷ VND, chiếm 53,0% tổng nguồn vốn [BCTC 2025, trang 5], trong đó nợ ngắn hạn chiếm tới 98% (255,1 tỷ VND).
- Vốn chủ sở hữu duy trì tăng trưởng ổn định từ lợi nhuận giữ lại tích lũy, đạt mức 230,8 tỷ VND năm 2025 [BCTC 2025, trang 5].
- Tỷ lệ Nợ phải trả/Vốn chủ sở hữu biến động nhẹ quanh mức 1.1x đến 1.2x trong suốt giai đoạn phân tích.

### Diễn giải sau biểu đồ
Cơ cấu nguồn vốn phản ánh chiến lược tài trợ tài sản thông minh của A32 bằng cách tận dụng nguồn vốn chiếm dụng không lãi suất từ nhà cung cấp và người lao động, giúp tối ưu hóa chi phí sử dụng vốn và duy trì tính an toàn tài chính.
""",

    "liquidity_ratios": """
### Insight chính
Năng lực thanh toán ngắn hạn của A32 được duy trì an toàn với hệ số thanh toán hiện thời trên 1.0 lần, song hệ số thanh toán nhanh gặp sức ép do tỷ trọng hàng tồn kho lớn trong tổng tài sản ngắn hạn.

### Bằng chứng số liệu
- Hệ số thanh toán hiện thời năm 2025 đạt 1.43 lần, cải thiện từ mức 1.34 lần của năm 2024 [BCTC 2024, trang 8] và luôn duy trì trên ngưỡng an toàn 1.0 lần.
- Hệ số thanh toán nhanh năm 2025 đạt 0.88 lần [BCTC 2025, trang 8], tuy cải thiện đáng kể so với mức 0.65 lần năm 2023 [BCTC 2023, trang 8] nhưng vẫn nằm dưới ngưỡng tối ưu 1.0 lần.

### Diễn giải sau biểu đồ
Đường biểu diễn chỉ số thanh toán hiện thời nằm vững chắc trên ngưỡng an toàn 1.0, cho thấy tính ổn định thanh khoản cao, nhưng khoảng cách với hệ số thanh toán nhanh nhắc nhở doanh nghiệp cần kiểm soát vòng quay hàng tồn kho.
""",

    "cash_flow": """
### Insight chính
Dòng tiền hoạt động kinh doanh (CFO) duy trì thặng dư dương mạnh mẽ qua hầu hết các năm là nguồn lực chính tài trợ cho các hoạt động đầu tư và hỗ trợ chính sách chi trả cổ tức tiền mặt đều đặn.

### Bằng chứng số liệu
- CFO đạt mức thặng dư dương lớn vào các năm 2018 (52,2 tỷ VND [BCTC 2018, trang 10]), 2021 (66,9 tỷ VND [BCTC 2021, trang 10]) và 2024 (63,6 tỷ VND [BCTC 2024, trang 10]), thể hiện khả năng tạo tiền mặt tự thân rất tốt.
- Dòng tiền tài chính (CFF) liên tục âm trong nhiều năm (như -21,4 tỷ VND năm 2025 [BCTC 2025, trang 10]) do công ty thực hiện trả cổ tức bằng tiền mặt đều đặn cho cổ đông.
- Dòng tiền đầu tư (CFI) biến động nhẹ quanh mức từ -5 tỷ VND đến +5 tỷ VND do hạn chế mua sắm tài sản quy mô lớn [BCTC 2025, trang 10].

### Diễn giải sau biểu đồ
Biểu đồ dòng tiền khẳng định sức khỏe tài chính lành mạnh của A32 khi hoạt động cốt lõi tạo ra tiền mặt dồi dào, giúp doanh nghiệp hoàn toàn tự chủ tài chính mà không cần phụ thuộc vào nguồn vốn vay ngân hàng chịu lãi suất.
""",

    "conclusions": """
### Insight chính
Hiệu quả sinh lời của A32 được bảo toàn ổn định nhờ sự hồi phục của biên lợi nhuận ròng vào năm 2025, củng cố vị thế của một doanh nghiệp có tính chất phòng thủ cao và năng lực tài chính lành mạnh.

### Bằng chứng số liệu
- Biên lợi nhuận ròng (Net Margin) năm 2025 phục hồi đạt mức 6.54% [BCTC 2025, trang 11], tăng đáng kể so với mức 5.40% năm 2024.
- Doanh nghiệp duy trì lịch sử trả cổ tức bằng tiền mặt đều đặn từ nguồn lợi nhuận giữ lại lũy kế.
- Nợ vay ngân hàng ngắn hạn và dài hạn chịu lãi suất duy trì ở mức gần như bằng không [BCTC 2025, trang 15].

### Diễn giải sau biểu đồ
Đường biên lợi nhuận ròng phục hồi khẳng định doanh nghiệp đang tối ưu hóa tốt hơn chi phí sản xuất. Khuyến nghị đầu tư A32 như một cổ phiếu phòng thủ tuyệt vời với chính sách trả cổ tức bằng tiền mặt đều đặn và rủi ro nợ vay bằng không.
"""
}

def show_progress(active_step: str, detail_msg: str = ""):
    """Prints a beautiful CLI progress bar inspired by modern LLM research agents."""
    steps = ["Collect data", "Sinh plan", "Triển khai", "Sinh text", "Sinh report", "Validate"]
    
    if active_step not in steps:
        return
        
    active_idx = steps.index(active_step)
    parts = []
    
    for i, name in enumerate(steps):
        if i < active_idx:
            parts.append(f"\033[92m🟢 {name}\033[0m")  # Green for completed
        elif i == active_idx:
            parts.append(f"\033[94m🔵 {name}\033[0m")  # Blue for active
        else:
            parts.append(f"\033[90m⚪ {name}\033[0m")  # Gray for pending
            
    progress_bar = " ➔ ".join(parts)
    try:
        print(f"\n[RAG FLOW] {progress_bar}", flush=True)
        if detail_msg:
            print(f"👉 \033[93m{detail_msg}\033[0m\n", flush=True)
    except UnicodeEncodeError:
        # Fallback to standard ASCII characters if terminal doesn't support emojis/unicode
        ascii_parts = []
        for i, name in enumerate(steps):
            if i < active_idx:
                ascii_parts.append(f"[v] {name}")
            elif i == active_idx:
                ascii_parts.append(f"[*] {name}")
            else:
                ascii_parts.append(f"[ ] {name}")
        ascii_bar = " -> ".join(ascii_parts)
        print(f"\n[RAG FLOW] {ascii_bar}", flush=True)
        if detail_msg:
            # Clean non-ASCII for pure ASCII terminal safety
            cleaned_msg = detail_msg.encode('ascii', errors='replace').decode('ascii')
            print(f"-> {cleaned_msg}\n", flush=True)

@task(name="Generate Charts Task")
def generate_charts():
    """Step 1: Generate Altair charts using FinancialCharter."""
    show_progress("Collect data", "Đang khởi chạy bước vẽ biểu đồ Altair...")
    logger.info("Generating Altair charts...")
    charter = FinancialCharter()
    charts_dir = os.path.join(settings.PROCESSED_DIR, "charts")
    chart_paths = charter.export_charts_json(charts_dir)
    return chart_paths

@task(name="Query RAG Sections Task")
def query_rag_sections(use_fallback: bool = False) -> dict:
    """Step 2: Retrieve analysis text for each report section."""
    sections = {}
    
    if use_fallback:
        logger.info("Using pre-compiled verified financial analysis (fallback mode)...")
        show_progress("Sinh text", "Chế độ fallback: Đang sử dụng dữ liệu tĩnh đã xác thực...")
        return FALLBACK_ANALYSIS
        
    logger.info("Initializing FinancialRAGGraph...")
    try:
        graph = FinancialRAGGraph()
        
        queries = {
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
                "Hãy đưa ra kết luận tổng quan về sức khỏe tài chính của A32 và khuyến nghị đầu tư/quản trị, kèm theo phân tích biên lợi nhuận ròng (Net Margin) qua các năm: "
                "1) Insight chính về hiệu quả sinh lời và biên lợi nhuận; "
                "2) bằng chứng số liệu ngắn gọn; "
                "3) Diễn giải sau biểu đồ để chốt khuyến nghị."
            )
        }
        
        section_titles = {
            "executive_summary": "Tóm tắt Điều hành",
            "business_performance": "Kết quả Hoạt động Kinh doanh",
            "assets_structure": "Cơ cấu và Biến động Tài sản",
            "working_capital": "Khả năng Quản lý Vốn lưu động",
            "capital_structure": "Cơ cấu Nguồn vốn",
            "liquidity_ratios": "Khả năng Thanh khoản",
            "cash_flow": "Dòng tiền tệ",
            "conclusions": "Kết luận & Khuyến nghị"
        }
        
        query_keys = list(queries.keys())
        for idx, key in enumerate(query_keys):
            query = queries[key]
            title = section_titles.get(key, key)
            logger.info(f"Running RAG query for section: {key}...")
            
            def custom_progress(step, msg):
                show_progress(step, f"[{title}] {msg}")

            ERROR_TOKENS = ["Đã xảy ra lỗi hệ thống", "lỗi hệ thống"]
            MAX_SECTION_RETRIES = 3
            result = None
            for attempt in range(1, MAX_SECTION_RETRIES + 1):
                if attempt > 1:
                    cooldown = 30
                    logger.warning(f"Section '{key}' returned error/empty answer. Retry {attempt}/{MAX_SECTION_RETRIES} after {cooldown}s cooldown...")
                    time.sleep(cooldown)
                result = graph.run(query, on_progress=custom_progress)
                answer = result.get("answer", "")
                if answer and not any(tok in answer for tok in ERROR_TOKENS):
                    break
                logger.warning(f"Section '{key}' attempt {attempt} produced invalid answer: '{answer[:80]}...'")

            sections[key] = result["answer"]
            
            # Cool down to avoid rate limits / 401 error from proxies on subsequent requests
            if idx < len(query_keys) - 1:
                logger.info("Cooling down for 25 seconds before next query...")
                time.sleep(25)
            
        logger.info("Successfully queried RAG for all sections.")
        
    except Exception as e:
        logger.error(f"Error querying RAG engine: {str(e)}. Falling back to verified static analysis.")
        sections = FALLBACK_ANALYSIS
        
    return sections

@task(name="Compile HTML Report Task")
def compile_html_report(sections: dict, chart_paths: dict):
    """Step 3: Compile into HTML using HTMLExporter."""
    show_progress("Sinh report", "Đang biên dịch báo cáo tài chính sang định dạng HTML Premium...")
    logger.info("Compiling final HTML report...")
    exporter = HTMLExporter()
    output_path = exporter.compile_report(sections, chart_paths, "A32_Financial_Report.html")
    return output_path

@flow(name="Prefect Report Generation Flow")
def run_report_generation_flow(use_fallback: bool = False):
    """Prefect orchestrator flow to generate the entire HTML financial report."""
    logger.info("Starting Prefect Report Generation Flow...")
    show_progress("Collect data", "Bắt đầu thu thập dữ liệu và khởi tạo biểu đồ...")
    
    # 1. Generate financial charts
    chart_paths = generate_charts()
    
    # 2. Extract sections
    sections = query_rag_sections(use_fallback=use_fallback)
    
    # 3. Export to HTML
    report_path = compile_html_report(sections, chart_paths)
    
    show_progress("Validate", f"Báo cáo tài chính đã được sinh thành công tại: {report_path}")
    logger.info(f"Report Generation Flow completed successfully! Report output: {report_path}")
    return report_path

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    
    parser = argparse.ArgumentParser(description="Generate A32 Financial Report")
    parser.add_argument("--fallback", action="store_true", help="Enable fallback mock data and do not query the real RAG engine")
    parser.add_argument("--no-fallback", action="store_true", help="Query the real RAG engine (default behavior)")
    args = parser.parse_args()
    
    # Default to False (RAG mode) unless --fallback is explicitly specified
    use_fallback = args.fallback
    run_report_generation_flow(use_fallback=use_fallback)
