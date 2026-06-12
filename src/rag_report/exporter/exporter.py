import os
import json
import logging
import re
from typing import Dict, Any

from src.rag_report.config import settings

logger = logging.getLogger(__name__)

class HTMLExporter:
    """Compiles markdown analysis and interactive Vega-Lite charts into a premium HTML report."""
    
    def __init__(self, template_path: str = None) -> None:
        self.output_dir = settings.REPORT_OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)
        self.citations_map = {}

    def _convert_table(self, table_lines) -> str:
        if len(table_lines) < 2:
            return "\n".join(table_lines)
        
        header_raw = table_lines[0]
        sep_raw = table_lines[1]
        
        cleaned_sep = sep_raw.replace('|', '').replace('-', '').replace(':', '').replace(' ', '')
        is_sep = (len(cleaned_sep) == 0)
        
        rows_start = 2 if is_sep else 1
        
        headers = [col.strip() for col in header_raw.split('|')[1:-1]]
        header_html = "<thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead>"
        
        body_html = "<tbody>"
        for r in table_lines[rows_start:]:
            cols = [col.strip() for col in r.split('|')[1:-1]]
            body_html += "<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>"
        body_html += "</tbody>"
        
        return f"<table>{header_html}{body_html}</table>"

    def _parse_markdown_tables(self, text: str) -> str:
        lines = text.split('\n')
        new_lines = []
        in_table = False
        table_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                if not in_table:
                    in_table = True
                table_lines.append(stripped)
            else:
                if in_table:
                    new_lines.append(self._convert_table(table_lines))
                    table_lines = []
                    in_table = False
                new_lines.append(line)
                
        if in_table:
            new_lines.append(self._convert_table(table_lines))
            
        return '\n'.join(new_lines)

    def _sanitize_noise(self, text: str) -> str:
        if not text:
            return ""
        # Remove LLM internal thought prompt residues / planning residues
        # e.g., "Need calculate ratios."
        text = re.sub(r'(?i)need\s+calculate\s+ratios\.?', '', text)
        # Clean up double dots
        text = text.replace("..", ".")
        return text.strip()

    def _convert_citations(self, html: str) -> str:
        pattern = r'\[(BCTC\s*[^\]]+)\]'
        
        def repl(match):
            cite_text = match.group(1).strip()
            if cite_text not in self.citations_map:
                self.citations_map[cite_text] = len(self.citations_map) + 1
            num = self.citations_map[cite_text]
            
            # Hoverable tooltip
            return (
                f'<span class="cite-ref">{num}'
                f'<span class="cite-tooltip">'
                f'<span class="cite-tooltip-header">'
                f'<span class="cite-tooltip-nav">&larr; &rarr;</span>'
                f'<span class="cite-tooltip-title">'
                f'<span class="cite-tooltip-icon">📄</span>BCTC A32</span>'
                f'</span>'
                f'<span class="cite-tooltip-body"><strong>Nguồn:</strong> {cite_text}</span>'
                f'</span>'
                f'</span>'
            )
            
        return re.sub(pattern, repl, html)

    def _highlight_keywords(self, html: str) -> str:
        # Split by html tags to avoid highlighting text inside attribute values/tags
        parts = re.split(r'(<[^>]+>)', html)
        for i in range(len(parts)):
            if i % 2 == 0:
                text = parts[i]
                # Highlighting percentages (e.g. 53.0% or 53%)
                text = re.sub(r'\b(\d+(?:[.,]\d+)?\s*%)', r'<span class="kw-pct">\1</span>', text)
                # Highlighting money values (e.g. 778,3 tỷ VND or 61,8 tỷ or 260.4 tỷ VND)
                text = re.sub(r'\b(\d+(?:[.,]\d+)?\s*(?:tỷ|triệu|nghìn|đồng|VND)\b)', r'<span class="kw-money">\1</span>', text)
                # Highlighting ratios (e.g. 1.43 lần or 1.1x)
                text = re.sub(r'\b(\d+(?:[.,]\d+)?\s*(?:lần|x)\b)', r'<span class="kw-ratio">\1</span>', text)
                parts[i] = text
        return "".join(parts)

    def _markdown_to_html(self, md_text: str) -> str:
        """Simple and clean markdown parsing to HTML with support for markdown tables."""
        md_text = self._sanitize_noise(md_text)
        
        # Clean tables first
        html = self._parse_markdown_tables(md_text)
        
        # Convert headers
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Convert bold/italic
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
        
        # Convert bullet lists
        lines = html.split('\n')
        in_list = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('- ') or line.strip().startswith('* '):
                if not in_list:
                    new_lines.append('<ul>')
                    in_list = True
                item = line.strip()[2:]
                new_lines.append(f'<li>{item}</li>')
            else:
                if in_list:
                    new_lines.append('</ul>')
                    in_list = False
                new_lines.append(line)
        if in_list:
            new_lines.append('</ul>')
        html = '\n'.join(new_lines)
        
        # Convert paragraphs
        paragraphs = html.split('\n\n')
        p_html = []
        for p in paragraphs:
            p_stripped = p.strip()
            if not p_stripped:
                continue
            if p_stripped.startswith('<h') or p_stripped.startswith('<ul') or p_stripped.startswith('<li') or p_stripped.startswith('</ul') or p_stripped.startswith('<table'):
                p_html.append(p_stripped)
            else:
                p_html.append(f'<p>{p_stripped}</p>')
                
        html_out = '\n'.join(p_html)
        html_out = self._convert_citations(html_out)
        html_out = self._highlight_keywords(html_out)
        return html_out

    def _split_text_and_takeaway(self, md_text: str) -> tuple[str, str]:
        """Split markdown into main body and chart takeaway based on headers."""
        md_text = md_text.strip()
        
        # Search for explicit takeaway keywords
        match = re.search(r"^###\s*(?:diễn giải|takeaway|ý nghĩa|kết luận ngắn).*$", md_text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            split_idx = match.start()
            main_body = md_text[:split_idx].strip()
            takeaway = md_text[split_idx:].strip()
            return main_body, takeaway
            
        # Fallback to splitting at the last header if multiple exist
        headers = list(re.finditer(r'^###\s+.*$', md_text, flags=re.MULTILINE))
        if len(headers) >= 2:
            split_idx = headers[-1].start()
            main_body = md_text[:split_idx].strip()
            takeaway = md_text[split_idx:].strip()
            return main_body, takeaway
            
        return md_text, ""

    def compile_report(
        self,
        sections: Dict[str, str],
        chart_paths: Dict[str, str],
        output_filename: str = "A32_Financial_Report.html"
    ) -> str:
        """Compile analysis and charts into the final premium HTML file."""
        self.citations_map = {}
        
        # Read Vega-lite chart specifications
        chart_specs = {}
        for name, path in chart_paths.items():
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    chart_specs[name] = json.load(f)
            else:
                chart_specs[name] = {}

        # Render sections using vertical story template helper
        def render_story_section(section_id, tag, title, key, chart_id=None):
            content = sections.get(key, "")
            main_body_md, takeaway_md = self._split_text_and_takeaway(content)
            
            main_body_html = self._markdown_to_html(main_body_md)
            takeaway_html = self._markdown_to_html(takeaway_md)
            
            chart_html = ""
            if chart_id:
                chart_html = f"""
                <div class="chart-wrapper">
                    <div class="chart-container" id="{chart_id}"></div>
                </div>
                """
            
            takeaway_block = ""
            if takeaway_html:
                takeaway_block = f"""
                <div class="chart-takeaway">
                    {takeaway_html}
                </div>
                """
                
            return f"""
            <section id="{section_id}" class="report-section">
                <span class="section-tag">{tag}</span>
                <h2>{title}</h2>
                <div class="section-block">
                    <div class="section-text">
                        {main_body_html}
                    </div>
                    {chart_html}
                    {takeaway_block}
                </div>
            </section>
            """

        # Section HTML compilation
        sec_guide = """
        <section id="huong-dan-doc" class="report-section">
            <span class="section-tag">Hướng dẫn</span>
            <h2>Cách đọc báo cáo này</h2>
            <div class="section-block" style="padding: 1.5rem 2rem;">
                <p>Báo cáo phân tích tài chính này được thiết kế theo mạch logic tuần tự từ kết quả kinh doanh đến cơ cấu vốn và khả năng thanh khoản, nhằm cung cấp bức tranh toàn cảnh về hoạt động của doanh nghiệp:</p>
                <ul style="list-style: none; margin: 0; padding: 0;">
                    <li style="margin-bottom: 8px; position: relative; padding-left: 1.4rem; color: var(--text-secondary); font-size: 0.97rem;">
                        <span style="position: absolute; left: 0; color: var(--accent-blue); font-weight: bold;">▸</span>
                        <strong>Tổng quan phân tích:</strong> Nhận định cốt lõi và các điểm lưu ý về phạm vi dữ liệu tài chính đầu vào.
                    </li>
                    <li style="margin-bottom: 8px; position: relative; padding-left: 1.4rem; color: var(--text-secondary); font-size: 0.97rem;">
                        <span style="position: absolute; left: 0; color: var(--accent-blue); font-weight: bold;">▸</span>
                        <strong>Kết quả kinh doanh:</strong> Phân tích xu hướng doanh thu thuần và lợi nhuận sau thuế, đánh giá chất lượng tăng trưởng.
                    </li>
                    <li style="margin-bottom: 8px; position: relative; padding-left: 1.4rem; color: var(--text-secondary); font-size: 0.97rem;">
                        <span style="position: absolute; left: 0; color: var(--accent-blue); font-weight: bold;">▸</span>
                        <strong>Cơ cấu tài sản & Vốn lưu động:</strong> Đánh giá tính cân đối trong phân bổ tài sản ngắn/dài hạn và hiệu quả quản lý hàng tồn kho, công nợ.
                    </li>
                    <li style="margin-bottom: 8px; position: relative; padding-left: 1.4rem; color: var(--text-secondary); font-size: 0.97rem;">
                        <span style="position: absolute; left: 0; color: var(--accent-blue); font-weight: bold;">▸</span>
                        <strong>Nguồn vốn & Thanh khoản:</strong> Phân tích đòn bẩy tài chính, áp lực trả nợ ngắn hạn và đệm an toàn thanh khoản.
                    </li>
                    <li style="margin-bottom: 8px; position: relative; padding-left: 1.4rem; color: var(--text-secondary); font-size: 0.97rem;">
                        <span style="position: absolute; left: 0; color: var(--accent-blue); font-weight: bold;">▸</span>
                        <strong>Dòng tiền & Nhận định tổng hợp:</strong> Đánh giá mức độ đóng góp của dòng tiền kinh doanh (CFO) vào hoạt động của doanh nghiệp và đưa ra kết luận tổng hợp.
                    </li>
                </ul>
            </div>
        </section>
        """

        sec_exec_summary = render_story_section("tổng-quan", "Tổng quan", "Tổng quan phân tích", "executive_summary")
        sec_business_performance = render_story_section("kết-quả-kd", "Phần I", "Kết quả kinh doanh", "business_performance", "chart-rev-prof")
        sec_assets_structure = render_story_section("cơ-cấu-ts", "Phần II - A", "Cơ cấu tài sản", "assets_structure", "chart-asset")
        sec_working_capital = render_story_section("vốn-lưu-động", "Phần II - B", "Vốn lưu động", "working_capital", "chart-working-capital")
        sec_capital_structure = render_story_section("nguồn-vốn", "Phần III - A", "Nguồn vốn và nợ phải trả", "capital_structure", "chart-capital")
        sec_liquidity_ratios = render_story_section("thanh-khoản", "Phần III - B", "Thanh khoản", "liquidity_ratios", "chart-liquidity")
        sec_cash_flow = render_story_section("dòng-tiền", "Phần IV", "Dòng tiền", "cash_flow", "chart-cash-flow")
        sec_conclusions = render_story_section("kết-luận", "Phần V", "Nhận định tổng hợp về sức khỏe tài chính", "conclusions", "chart-net-margin")

        sec_glossary = """
        <section id="thuat-ngu-viet-tat" class="report-section">
            <span class="section-tag">Thuật ngữ</span>
            <h2>Danh mục chữ viết tắt và thuật ngữ tài chính</h2>
            <div class="section-block" style="padding: 1.5rem 2rem;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem;">
                    <div>
                        <h3 style="margin-top: 0; font-size: 1.1rem; color: var(--text-primary); font-weight: 700; margin-bottom: 0.6rem; font-family: 'Outfit', sans-serif; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.25rem;">Các chữ viết tắt</h3>
                        <table style="margin: 0.5rem 0;">
                            <thead>
                                <tr>
                                    <th>Viết tắt</th>
                                    <th>Thuật ngữ tiếng Việt</th>
                                    <th>Thuật ngữ tiếng Anh</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td><strong>LNST</strong></td><td>Lợi nhuận sau thuế</td><td>Net Income</td></tr>
                                <tr><td><strong>BCTC</strong></td><td>Báo cáo tài chính</td><td>Financial Statements</td></tr>
                                <tr><td><strong>CFO</strong></td><td>Dòng tiền từ HĐKD</td><td>Cash Flow from Operations</td></tr>
                                <tr><td><strong>CFI</strong></td><td>Dòng tiền từ HĐĐT</td><td>Cash Flow from Investing</td></tr>
                                <tr><td><strong>CFF</strong></td><td>Dòng tiền từ HĐTC</td><td>Cash Flow from Financing</td></tr>
                                <tr><td><strong>VCSH</strong></td><td>Vốn chủ sở hữu</td><td>Owner's Equity</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <div>
                        <h3 style="margin-top: 0; font-size: 1.1rem; color: var(--text-primary); font-weight: 700; margin-bottom: 0.6rem; font-family: 'Outfit', sans-serif; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.25rem;">Thuật ngữ chính</h3>
                        <table style="margin: 0.5rem 0;">
                            <thead>
                                <tr>
                                    <th>Thuật ngữ</th>
                                    <th>Định nghĩa / Diễn giải</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td><strong>Vốn lưu động ròng</strong></td><td>Chênh lệch giữa tài sản ngắn hạn và nợ ngắn hạn, thể hiện đệm an toàn tài chính.</td></tr>
                                <tr><td><strong>Hệ số thanh toán hiện thời</strong></td><td>Tài sản ngắn hạn chia cho nợ ngắn hạn, đo lường khả năng thanh toán nợ ngắn hạn.</td></tr>
                                <tr><td><strong>Hệ số thanh toán nhanh</strong></td><td>(Tài sản ngắn hạn - Hàng tồn kho) chia cho nợ ngắn hạn, đo lường thanh khoản tức thời.</td></tr>
                                <tr><td><strong>Biên lợi nhuận ròng</strong></td><td>Lợi nhuận sau thuế chia cho doanh thu thuần, đo lường hiệu suất sinh lời trên mỗi đồng doanh thu.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </section>
        """

        # Citations section
        if self.citations_map:
            citations_li = "".join(f'<li style="margin-bottom: 8px; font-size: 0.9rem; color: var(--text-secondary);"><strong>[{num}]</strong> {cite}</li>' for cite, num in sorted(self.citations_map.items(), key=lambda x: x[1]))
        else:
            citations_li = '<li style="margin-bottom: 8px; font-size: 0.9rem; color: var(--text-secondary); font-style: italic;">Không có nguồn trích dẫn trực tiếp nào được sử dụng trong phiên bản tóm tắt này.</li>'
            
        sec_citations = f"""
        <section id="danh-muc-trich-dan" class="report-section">
            <span class="section-tag">Nguồn dữ liệu</span>
            <h2>Danh mục Trích dẫn</h2>
            <div class="section-block" style="padding: 1.5rem 2rem;">
                <ul style="list-style: none; margin: 0; padding: 0;">
                    {citations_li}
                </ul>
            </div>
        </section>
        """

        # Complete Premium HTML Template
        template = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo cáo Phân tích Tài chính A32 - Công ty CP 32</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
    
    <!-- Vega-Lite dependency -->
    <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
    <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
    <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
    
    <style>
        :root {{
            --bg-color: #f0f4f8;
            --card-bg: #ffffff;
            --border-color: #dde3ec;
            --text-primary: #1e293b;
            --text-secondary: #4b5a6e;
            --accent-blue: #1d4ed8;
            --accent-green: #16a34a;
            --accent-purple: #7c3aed;
            --accent-orange: #d97706;
            --accent-red: #dc2626;
            --accent-glow: rgba(29, 78, 216, 0.08);
            --sidebar-bg: #ffffff;
            --header-gradient-start: #1e3a5f;
            --header-gradient-end: #2563eb;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Plus Jakarta Sans', 'Outfit', sans-serif;
            line-height: 1.7;
        }}
        
        /* Layout wrapper */
        .app-container {{
            display: flex;
            min-height: 100vh;
        }}
        
        /* Sidebar Navigation */
        .sidebar {{
            width: 270px;
            background: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            position: fixed;
            height: 100vh;
            padding: 2rem 1.25rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            z-index: 100;
            box-shadow: 2px 0 8px rgba(0,0,0,0.06);
            overflow-y: auto;
        }}
        
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .logo-badge {{
            background: linear-gradient(135deg, #1d4ed8, #2563eb);
            color: white;
            padding: 0.45rem 0.75rem;
            border-radius: 6px;
            font-weight: 800;
            font-size: 1rem;
            letter-spacing: 1px;
        }}
        
        .logo-title {{
            font-weight: 700;
            font-size: 1.1rem;
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
        }}
        
        .nav-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }}
        
        .nav-item a {{
            display: flex;
            align-items: center;
            padding: 0.6rem 0.9rem;
            color: var(--text-secondary);
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            font-size: 0.9rem;
            transition: all 0.2s ease;
            border: 1px solid transparent;
        }}
        
        .nav-item a:hover, .nav-item.active a {{
            color: var(--accent-blue);
            background: rgba(29, 78, 216, 0.07);
            border-color: rgba(29, 78, 216, 0.15);
        }}
        
        .sidebar-footer {{
            color: #94a3b8;
            font-size: 0.78rem;
            border-top: 1px solid var(--border-color);
            padding-top: 1rem;
        }}
        
        /* Main Content */
        .main-content {{
            margin-left: 270px;
            flex: 1;
            padding: 2.5rem 3.5rem;
            max-width: 1200px;
        }}
        
        /* Header Hero */
        .report-header {{
            background: linear-gradient(135deg, var(--header-gradient-start), var(--header-gradient-end));
            color: white;
            border-radius: 16px;
            padding: 2.5rem 3rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 4px 24px rgba(29,78,216,0.18);
        }}
        
        .company-tag {{
            display: inline-block;
            background: rgba(255,255,255,0.18);
            color: #e0e7ff;
            padding: 0.2rem 0.75rem;
            border-radius: 20px;
            font-size: 0.82rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            border: 1px solid rgba(255,255,255,0.25);
        }}
        
        .report-title {{
            font-size: 2.2rem;
            font-weight: 800;
            font-family: 'Outfit', sans-serif;
            color: #ffffff;
            margin-bottom: 0.75rem;
            line-height: 1.25;
        }}
        
        .report-meta {{
            color: rgba(255,255,255,0.75);
            font-size: 0.9rem;
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
        }}
        
        .meta-item strong {{
            color: #ffffff;
        }}
        
        /* Section Cards */
        .report-section {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2.25rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            transition: box-shadow 0.2s ease;
        }}
        
        .report-section:hover {{
            box-shadow: 0 6px 20px rgba(29,78,216,0.1);
        }}
        
        .section-tag {{
            color: var(--accent-blue);
            font-weight: 700;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.5rem;
            display: block;
        }}
        
        .report-section h2 {{
            font-size: 1.5rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            margin-bottom: 1.25rem;
            color: var(--text-primary);
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.75rem;
        }}
        
        .report-section p {{
            color: var(--text-secondary);
            margin-bottom: 1rem;
            font-size: 1rem;
        }}
        
        .report-section strong {{
            color: var(--accent-blue);
        }}
        
        /* Vertical block layout */
        .section-block {{
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }}
        
        .section-text {{
            width: 100%;
        }}
        
        .section-text h3 {{
            font-size: 1.1rem;
            color: var(--text-primary);
            font-weight: 700;
            margin-top: 1.25rem;
            margin-bottom: 0.6rem;
            font-family: 'Outfit', sans-serif;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0.25rem;
        }}
        
        .section-text h3:first-child {{
            margin-top: 0;
        }}

        .section-text ul {{
            list-style: none;
            margin-left: 0;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin-bottom: 1.25rem;
        }}
        
        .section-text li {{
            position: relative;
            padding-left: 1.4rem;
            color: var(--text-secondary);
            font-size: 0.97rem;
        }}
        
        .section-text li::before {{
            content: "▸";
            color: var(--accent-blue);
            font-weight: bold;
            position: absolute;
            left: 0;
        }}
        
        /* Chart container */
        .chart-wrapper {{
            width: 100%;
            margin-top: 1.25rem;
            display: flex;
            justify-content: center;
        }}
        
        .chart-container {{
            width: 100%;
            max-width: 780px;
            background: #f8fafc;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            padding: 1.25rem;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 380px;
        }}
        
        /* Takeaway styling */
        .chart-takeaway {{
            background: linear-gradient(135deg, #eff6ff, #f5f3ff);
            border-left: 4px solid var(--accent-blue);
            padding: 1.25rem 1.5rem;
            border-radius: 4px 10px 10px 4px;
            margin-top: 1.25rem;
            border-top: 1px solid #dbeafe;
            border-right: 1px solid #dbeafe;
            border-bottom: 1px solid #dbeafe;
        }}
        
        .chart-takeaway h3 {{
            font-size: 1rem;
            color: var(--accent-blue);
            margin-bottom: 0.4rem;
            font-family: 'Outfit', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 700;
        }}
        
        .chart-takeaway p {{
            font-size: 0.97rem !important;
            color: #1e3a5f !important;
            margin-bottom: 0 !important;
            line-height: 1.65;
        }}
        
        /* Tables in reports */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.25rem 0;
            font-size: 0.93rem;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }}
        
        th {{
            background: #eff6ff;
            color: #1e3a5f;
            text-align: left;
            padding: 0.75rem 1rem;
            font-weight: 700;
            border-bottom: 2px solid #dbeafe;
        }}
        
        td {{
            padding: 0.7rem 1rem;
            border-bottom: 1px solid #f1f5f9;
            color: var(--text-secondary);
        }}
        
        tr:nth-child(even) td {{
            background: #f8fafc;
        }}
        
        tr:hover td {{
            background: #eff6ff;
            color: var(--text-primary);
        }}
        
        /* Citation references */
        .cite-ref {{
            position: relative;
            cursor: pointer;
            background: #eff6ff;
            color: #1d4ed8;
            border-radius: 50%;
            width: 16px;
            height: 16px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 700;
            margin: 0 3px;
            border: 1px solid #dbeafe;
            vertical-align: super;
        }}
        
        .cite-ref:hover {{
            background: #1d4ed8;
            color: white;
            border-color: #1d4ed8;
        }}
        
        /* Tooltip style resembling a browser link preview card */
        .cite-tooltip {{
            visibility: hidden;
            opacity: 0;
            position: absolute;
            bottom: 140%;
            left: 50%;
            transform: translateX(-50%) translateY(5px);
            background: #ffffff;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
            border-radius: 10px;
            padding: 10px 14px;
            width: 250px;
            z-index: 1000;
            transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
            font-family: 'Plus Jakarta Sans', sans-serif;
            text-align: left;
            pointer-events: none;
            color: var(--text-primary);
            line-height: 1.4;
        }}
        
        .cite-ref:hover .cite-tooltip {{
            visibility: visible;
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }}
        
        .cite-tooltip-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 6px;
            margin-bottom: 6px;
        }}
        
        .cite-tooltip-nav {{
            font-family: monospace;
            color: #94a3b8;
            font-size: 0.75rem;
            letter-spacing: 2px;
        }}
        
        .cite-tooltip-title {{
            font-size: 0.8rem;
            font-weight: 700;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        
        .cite-tooltip-icon {{
            font-size: 0.8rem;
        }}
        
        .cite-tooltip-body {{
            font-size: 0.78rem;
            color: var(--text-secondary);
        }}
        
        .cite-tooltip-body strong {{
            color: #1e293b;
        }}
        
        /* Highlight words styling */
        .kw-pct {{
            color: var(--accent-purple);
            background-color: rgba(124, 58, 237, 0.07);
            padding: 1px 4px;
            border-radius: 4px;
            font-weight: 600;
        }}
        
        .kw-money {{
            color: #15803d;
            background-color: rgba(22, 163, 74, 0.07);
            padding: 1px 4px;
            border-radius: 4px;
            font-weight: 600;
        }}
        
        .kw-ratio {{
            color: #b45309;
            background-color: rgba(217, 119, 6, 0.07);
            padding: 1px 4px;
            border-radius: 4px;
            font-weight: 600;
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: #f1f5f9;
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 4px;
        }}
        
        ::-webkit-scrollbar-thumb:hover {{
            background: #94a3b8;
        }}
    </style>
</head>
<body>

<div class="app-container">
    <!-- Sidebar -->
    <aside class="sidebar">
        <div>
            <div class="logo-section">
                <div class="logo-badge">A32</div>
                <div class="logo-title">Phân tích Tài chính</div>
            </div>
            
            <nav>
                <ul class="nav-list">
                    <li class="nav-item"><a href="#huong-dan-doc">Hướng dẫn đọc</a></li>
                    <li class="nav-item"><a href="#tổng-quan">Tổng quan phân tích</a></li>
                    <li class="nav-item"><a href="#kết-quả-kd">Kết quả kinh doanh</a></li>
                    <li class="nav-item"><a href="#cơ-cấu-ts">Cơ cấu tài sản</a></li>
                    <li class="nav-item"><a href="#vốn-lưu-động">Vốn lưu động</a></li>
                    <li class="nav-item"><a href="#nguồn-vốn">Nguồn vốn và nợ phải trả</a></li>
                    <li class="nav-item"><a href="#thanh-khoản">Thanh khoản</a></li>
                    <li class="nav-item"><a href="#dòng-tiền">Dòng tiền</a></li>
                    <li class="nav-item"><a href="#kết-luận">Nhận định tổng hợp</a></li>
                    <li class="nav-item"><a href="#thuat-ngu-viet-tat">Thuật ngữ & Viết tắt</a></li>
                    <li class="nav-item"><a href="#danh-muc-trich-dan">Danh mục Trích dẫn</a></li>
                </ul>
            </nav>
        </div>
        
        <div class="sidebar-footer">
            <p>© 2026 Bộ phận Phân tích và Nghiên cứu</p>
        </div>
    </aside>
    
    <!-- Main Content Area -->
    <main class="main-content">
        <!-- Header -->
        <header class="report-header">
            <span class="company-tag">Công ty Cổ phần 32 - Mã chứng khoán: A32</span>
            <h1 class="report-title">Báo cáo Phân tích Tài chính Tổng hợp<br>Giai đoạn 2017 - 2025</h1>
            
            <div class="report-meta">
                <span class="meta-item">Đối tượng phân tích: <strong>Báo cáo tài chính kiểm toán giai đoạn 2017–2025</strong></span>
            </div>
        </header>

        {sec_guide}
        {sec_exec_summary}
        {sec_business_performance}
        {sec_assets_structure}
        {sec_working_capital}
        {sec_capital_structure}
        {sec_liquidity_ratios}
        {sec_cash_flow}
        {sec_conclusions}
        {sec_glossary}
        {sec_citations}
    </main>
</div>

<script>
    // Vega-Lite chart specifications passed from Python
    const revProfSpec = {json.dumps(chart_specs.get("revenue_profit", {}))};
    const assetSpec = {json.dumps(chart_specs.get("asset_structure", {}))};
    const workingCapitalSpec = {json.dumps(chart_specs.get("working_capital", {}))};
    const capitalSpec = {json.dumps(chart_specs.get("capital_structure", {}))};
    const liquiditySpec = {json.dumps(chart_specs.get("liquidity_ratios", {}))};
    const cashFlowSpec = {json.dumps(chart_specs.get("cash_flow", {}))};
    const netMarginSpec = {json.dumps(chart_specs.get("net_margin", {}))};
    
    // Embed configurations
    const embedOpts = {{actions: false, theme: 'default', renderer: 'svg'}};
    
    // Defensive chart rendering wrapper
    function safeEmbedChart(containerId, spec, opts) {{
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!spec || Object.keys(spec).length === 0) {{
            container.innerHTML = `<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Không có dữ liệu biểu đồ</div>`;
            return;
        }}
        try {{
            vegaEmbed('#' + containerId, spec, opts).catch(err => {{
                console.error("Lỗi vẽ biểu đồ " + containerId + ":", err);
                container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem; font-size: 0.9rem;">Không thể hiển thị biểu đồ: ${{err.message}}</div>`;
            }});
        }} catch (err) {{
            console.error("Lỗi vẽ biểu đồ đồng bộ " + containerId + ":", err);
            container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem; font-size: 0.9rem;">Lỗi vẽ biểu đồ: ${{err.message}}</div>`;
        }}
    }}

    // Render all charts defensively when vegaEmbed is ready
    function initCharts(attempts = 0) {{
        if (typeof vegaEmbed === 'undefined') {{
            if (attempts < 50) {{
                setTimeout(() => initCharts(attempts + 1), 100);
            }} else {{
                console.error("VegaEmbed library failed to load after 5s.");
                document.querySelectorAll('.chart-container').forEach(c => {{
                    c.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem; font-size: 0.9rem;">Lỗi: Thư viện biểu đồ (vegaEmbed) chưa được tải. Vui lòng tải lại trang.</div>`;
                }});
            }}
            return;
        }}
        
        safeEmbedChart('chart-rev-prof', revProfSpec, embedOpts);
        safeEmbedChart('chart-asset', assetSpec, embedOpts);
        safeEmbedChart('chart-working-capital', workingCapitalSpec, embedOpts);
        safeEmbedChart('chart-capital', capitalSpec, embedOpts);
        safeEmbedChart('chart-liquidity', liquiditySpec, embedOpts);
        safeEmbedChart('chart-cash-flow', cashFlowSpec, embedOpts);
        safeEmbedChart('chart-net-margin', netMarginSpec, embedOpts);
    }}
    
    // Start chart initialization on window load
    window.addEventListener('load', () => initCharts());
    
    // Scroll active link styling
    window.addEventListener('scroll', () => {{
        let current = "";
        const sections = document.querySelectorAll("section");
        const navItems = document.querySelectorAll(".nav-item");
        
        sections.forEach(section => {{
            const sectionTop = section.offsetTop;
            if (pageYOffset >= sectionTop - 120) {{
                current = section.getAttribute("id");
            }}
        }});
        
        navItems.forEach(item => {{
            item.classList.remove("active");
            if (item.querySelector("a").getAttribute("href") === `#${{current}}`) {{
                item.classList.add("active");
            }}
        }});
    }});
</script>
</body>
</html>
"""
        
        output_path = os.path.join(self.output_dir, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(template)
            
        logger.info(f"Report compiled successfully: {output_path}")
        return output_path
