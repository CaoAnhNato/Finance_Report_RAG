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

    def _markdown_to_html(self, md_text: str) -> str:
        """Simple and clean markdown parsing to HTML with support for markdown tables."""
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
                
        return '\n'.join(p_html)

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
        sec_exec_summary = render_story_section("tổng-quan", "Tổng quan", "Tóm tắt Điều hành", "executive_summary")
        sec_business_performance = render_story_section("kết-quả-kd", "Phần I", "Kết quả Hoạt động Kinh doanh", "business_performance", "chart-rev-prof")
        sec_assets_structure = render_story_section("cơ-cấu-ts", "Phần II - A", "Cơ cấu và Biến động Tài sản", "assets_structure", "chart-asset")
        sec_working_capital = render_story_section("vốn-lưu-động", "Phần II - B", "Khả năng Quản lý Vốn lưu động", "working_capital", "chart-working-capital")
        sec_capital_structure = render_story_section("nguồn-vốn", "Phần III - A", "Cơ cấu Nguồn vốn & Nợ phải trả", "capital_structure", "chart-capital")
        sec_liquidity_ratios = render_story_section("thanh-khoản", "Phần III - B", "Khả năng Thanh khoản & Hệ số Thanh toán", "liquidity_ratios", "chart-liquidity")
        sec_cash_flow = render_story_section("dòng-tiền", "Phần IV", "Phân tích Lưu chuyển Tiền tệ (Dòng tiền)", "cash_flow", "chart-cash-flow")
        
        # Abstention section
        abstention_content = sections.get("abstention_2022", "<p>Chưa thiết lập cơ chế từ chối.</p>")
        abstention_html = self._markdown_to_html(abstention_content)
        sec_abstention = f"""
        <section id="cơ-chế-từ-chối" class="report-section">
            <span class="section-tag">Kiểm soát chất lượng</span>
            <h2>Cơ chế Từ chối Trả lời & Dữ liệu năm 2022</h2>
            <div class="refusal-note">
                <h4>Chính sách từ chối (Abstention Policy)</h4>
                {abstention_html}
            </div>
        </section>
        """
        
        # Conclusions with Net Margin chart
        sec_conclusions = render_story_section("kết-luận", "Phần V", "Kết luận chung & Khuyến nghị", "conclusions", "chart-net-margin")

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
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-purple: #8b5cf6;
            --accent-orange: #f59e0b;
            --accent-red: #ef4444;
            --accent-glow: rgba(59, 130, 246, 0.12);
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
            line-height: 1.65;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
            background-attachment: fixed;
        }}
        
        /* Layout wrapper */
        .app-container {{
            display: flex;
            min-height: 100vh;
        }}
        
        /* Sidebar Navigation */
        .sidebar {{
            width: 280px;
            background: rgba(10, 15, 26, 0.85);
            backdrop-filter: blur(20px);
            border-right: 1px solid var(--border-color);
            position: fixed;
            height: 100vh;
            padding: 2.5rem 1.5rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            z-index: 100;
        }}
        
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 2.5rem;
        }}
        
        .logo-badge {{
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            font-weight: 800;
            font-size: 1.1rem;
            letter-spacing: 1px;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }}
        
        .logo-title {{
            font-weight: 700;
            font-size: 1.25rem;
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
        }}
        
        .nav-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .nav-item a {{
            display: flex;
            align-items: center;
            padding: 0.75rem 1rem;
            color: var(--text-secondary);
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
            border: 1px solid transparent;
        }}
        
        .nav-item a:hover, .nav-item.active a {{
            color: var(--text-primary);
            background: rgba(59, 130, 246, 0.08);
            border-color: rgba(59, 130, 246, 0.2);
            padding-left: 1.25rem;
        }}
        
        .sidebar-footer {{
            color: #6b7280;
            font-size: 0.8rem;
            border-top: 1px solid var(--border-color);
            padding-top: 1.5rem;
        }}
        
        /* Main Content */
        .main-content {{
            margin-left: 280px;
            flex: 1;
            padding: 3rem 4rem;
            max-width: 1200px;
        }}
        
        /* Header Hero */
        .report-header {{
            margin-bottom: 3.5rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .company-tag {{
            display: inline-block;
            background: rgba(59, 130, 246, 0.1);
            color: var(--accent-blue);
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1rem;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }}
        
        .report-title {{
            font-size: 2.5rem;
            font-weight: 800;
            font-family: 'Outfit', sans-serif;
            background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1rem;
            line-height: 1.2;
        }}
        
        .report-meta {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            display: flex;
            gap: 2rem;
        }}
        
        .meta-item strong {{
            color: var(--text-primary);
        }}
        
        /* Section Cards */
        .report-section {{
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2.5rem;
            margin-bottom: 3rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .report-section:hover {{
            transform: translateY(-4px);
            box-shadow: 0 15px 35px var(--accent-glow);
            border-color: rgba(59, 130, 246, 0.15);
        }}
        
        .section-tag {{
            color: var(--accent-blue);
            font-weight: 700;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.75rem;
            display: block;
        }}
        
        .report-section h2 {{
            font-size: 1.75rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            margin-bottom: 1.5rem;
            color: var(--text-primary);
        }}
        
        .report-section p {{
            color: var(--text-secondary);
            margin-bottom: 1.25rem;
            font-size: 1.05rem;
        }}
        
        .report-section strong {{
            color: var(--accent-blue);
        }}
        
        /* Vertical block layout */
        .section-block {{
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }}
        
        .section-text {{
            width: 100%;
        }}
        
        .section-text h3 {{
            font-size: 1.25rem;
            color: var(--text-primary);
            font-weight: 600;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
            font-family: 'Outfit', sans-serif;
            border-bottom: 1px solid var(--border-color);
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
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }}
        
        .section-text li {{
            position: relative;
            padding-left: 1.5rem;
            color: var(--text-secondary);
            font-size: 1.025rem;
        }}
        
        .section-text li::before {{
            content: "→";
            color: var(--accent-blue);
            font-weight: bold;
            position: absolute;
            left: 0;
            font-size: 1.1rem;
        }}
        
        /* Chart container */
        .chart-wrapper {{
            width: 100%;
            margin-top: 1.5rem;
            display: flex;
            justify-content: center;
        }}
        
        .chart-container {{
            width: 100%;
            max-width: 750px;
            background: rgba(10, 15, 26, 0.4);
            border-radius: 12px;
            border: 1px solid var(--border-color);
            padding: 1.5rem;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 380px;
        }}
        
        /* Takeaway styling */
        .chart-takeaway {{
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.06), rgba(139, 92, 246, 0.03));
            border-left: 4px solid var(--accent-blue);
            padding: 1.5rem;
            border-radius: 4px 12px 12px 4px;
            margin-top: 1.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.03);
            border-right: 1px solid rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }}
        
        .chart-takeaway h3 {{
            font-size: 1.1rem;
            color: var(--accent-blue);
            margin-bottom: 0.5rem;
            font-family: 'Outfit', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .chart-takeaway p {{
            font-size: 1rem !important;
            color: var(--text-primary) !important;
            margin-bottom: 0 !important;
            line-height: 1.6;
        }}
        
        /* Tables in reports */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            font-size: 0.95rem;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }}
        
        th {{
            background: rgba(59, 130, 246, 0.1);
            color: var(--text-primary);
            text-align: left;
            padding: 0.85rem 1.2rem;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color);
        }}
        
        td {{
            padding: 0.85rem 1.2rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
        }}
        
        tr:hover td {{
            background: rgba(255, 255, 255, 0.02);
            color: var(--text-primary);
        }}
        
        /* Refusal Note */
        .refusal-note {{
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.08), transparent);
            border-left: 4px solid var(--accent-red);
            padding: 1.5rem;
            border-radius: 0 12px 12px 0;
            margin: 1.5rem 0;
        }}
        
        .refusal-note h4 {{
            color: var(--accent-red);
            margin-bottom: 0.5rem;
            font-weight: 700;
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: var(--bg-color);
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: #27272a;
            border-radius: 4px;
        }}
        
        ::-webkit-scrollbar-thumb:hover {{
            background: #3f3f46;
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
                <div class="logo-title">RAG Platform</div>
            </div>
            
            <nav>
                <ul class="nav-list">
                    <li class="nav-item"><a href="#tổng-quan">Tóm tắt Điều hành</a></li>
                    <li class="nav-item"><a href="#kết-quả-kd">Doanh thu & LNST</a></li>
                    <li class="nav-item"><a href="#cơ-cấu-ts">Cơ cấu Tài sản</a></li>
                    <li class="nav-item"><a href="#vốn-lưu-động">Quản lý Vốn lưu động</a></li>
                    <li class="nav-item"><a href="#nguồn-vốn">Cơ cấu Nguồn vốn</a></li>
                    <li class="nav-item"><a href="#thanh-khoản">Khả năng Thanh khoản</a></li>
                    <li class="nav-item"><a href="#dòng-tiền">Dòng tiền tệ</a></li>
                    <li class="nav-item"><a href="#cơ-chế-từ-chối">Thông tin năm 2022</a></li>
                    <li class="nav-item"><a href="#kết-luận">Kết luận & Khuyến nghị</a></li>
                </ul>
            </nav>
        </div>
        
        <div class="sidebar-footer">
            <p>Hệ thống RAG Financial</p>
            <p>Version 1.2.0 (DeepSeek + FPT)</p>
        </div>
    </aside>
    
    <!-- Main Content Area -->
    <main class="main-content">
        <!-- Header -->
        <header class="report-header">
            <span class="company-tag">Công ty Cổ phần 32 - Mã chứng khoán: A32</span>
            <h1 class="report-title">Báo cáo Phân tích Tài chính Tổng hợp<br>Giai đoạn 2017 - 2025</h1>
            
            <div class="report-meta">
                <span class="meta-item">Đối tượng phân tích: <strong>Báo cáo tài chính kiểm toán 8 năm</strong></span>
                <span class="meta-item">Mô hình phân tích: <strong>DeepSeek v4 Pro + FPT Reranker</strong></span>
            </div>
        </header>

        {sec_exec_summary}
        {sec_business_performance}
        {sec_assets_structure}
        {sec_working_capital}
        {sec_capital_structure}
        {sec_liquidity_ratios}
        {sec_cash_flow}
        {sec_abstention}
        {sec_conclusions}
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
    const embedOpts = {{actions: false, theme: 'dark', renderer: 'svg'}};
    
    // Defensive chart rendering wrapper
    function safeEmbedChart(containerId, spec, opts) {{
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!spec || Object.keys(spec).length === 0) {{
            container.innerHTML = `<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Không có dữ liệu biểu đồ</div>`;
            return;
        }}
        vegaEmbed('#' + containerId, spec, opts).catch(err => {{
            console.error("Lỗi vẽ biểu đồ " + containerId + ":", err);
            container.innerHTML = `<div style="color: var(--accent-red); text-align: center; padding: 2rem; font-size: 0.9rem;">Không thể hiển thị biểu đồ: ${{err.message}}</div>`;
        }});
    }}

    // Render all charts defensively
    safeEmbedChart('chart-rev-prof', revProfSpec, embedOpts);
    safeEmbedChart('chart-asset', assetSpec, embedOpts);
    safeEmbedChart('chart-working-capital', workingCapitalSpec, embedOpts);
    safeEmbedChart('chart-capital', capitalSpec, embedOpts);
    safeEmbedChart('chart-liquidity', liquiditySpec, embedOpts);
    safeEmbedChart('chart-cash-flow', cashFlowSpec, embedOpts);
    safeEmbedChart('chart-net-margin', netMarginSpec, embedOpts);
    
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
