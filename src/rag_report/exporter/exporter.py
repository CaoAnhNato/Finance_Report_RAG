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
        # We can construct the template inline or load it from a file
        self.output_dir = settings.REPORT_OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def _markdown_to_html(self, md_text: str) -> str:
        """Simple and clean markdown parsing to HTML to avoid heavy external dependencies."""
        # Convert headers
        html = md_text
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Convert bold/italic
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
        
        # Convert bullet lists
        # Group list items together and wrap in <ul>
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
            if p_stripped.startswith('<h') or p_stripped.startswith('<ul') or p_stripped.startswith('<li') or p_stripped.startswith('</ul'):
                p_html.append(p_stripped)
            else:
                p_html.append(f'<p>{p_stripped}</p>')
                
        return '\n'.join(p_html)

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

        # Convert markdown sections to HTML
        import re
        html_sections = {k: self._markdown_to_html(v) for k, v in sections.items()}
        
        # Complete Premium HTML Template with Glassmorphism and responsive design
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
            --accent-red: #ef4444;
            --accent-glow: rgba(59, 130, 246, 0.15);
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
            line-height: 1.6;
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
            border-right: 1px border-solid var(--border-color);
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
        
        .report-section ul {{
            margin-left: 1.5rem;
            margin-bottom: 1.5rem;
            color: var(--text-secondary);
        }}
        
        .report-section li {{
            margin-bottom: 0.5rem;
        }}
        
        /* Grid layout for text & charts */
        .section-grid {{
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 2.5rem;
            align-items: center;
        }}
        
        @media(max-width: 1024px) {{
            .section-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        /* Chart container */
        .chart-container {{
            background: rgba(10, 15, 26, 0.5);
            border-radius: 12px;
            border: 1px solid var(--border-color);
            padding: 1.5rem;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 350px;
        }}
        
        /* Tables in reports */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            font-size: 0.95rem;
        }}
        
        th {{
            background: rgba(59, 130, 246, 0.1);
            color: var(--text-primary);
            text-align: left;
            padding: 0.75rem 1rem;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color);
        }}
        
        td {{
            padding: 0.75rem 1rem;
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
                <div class="logo-badge">RAG</div>
                <div class="logo-title">A32 Report</div>
            </div>
            
            <nav>
                <ul class="nav-list">
                    <li class="nav-item"><a href="#kết-quả-kd">Doanh thu & Lợi nhuận</a></li>
                    <li class="nav-item"><a href="#cơ-cấu-ts">Cơ cấu Tài sản</a></li>
                    <li class="nav-item"><a href="#nguồn-vốn">Nguồn vốn & Nợ</a></li>
                    <li class="nav-item"><a href="#dòng-tiền">Dòng tiền tệ</a></li>
                    <li class="nav-item"><a href="#cơ-chế-từ-chối">Thông tin năm 2022</a></li>
                    <li class="nav-item"><a href="#kết-luận">Kết luận & Đánh giá</a></li>
                </ul>
            </nav>
        </div>
        
        <div class="sidebar-footer">
            <p>Hệ thống RAG Financial</p>
            <p>Version 1.0.0 (FPT Cloud)</p>
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
                <span class="meta-item">Nhà phát triển: <strong>RAG Analyzer System</strong></span>
            </div>
        </header>
        
        <!-- Section 1: Kết quả Kinh doanh -->
        <section id="kết-quả-kd" class="report-section">
            <span class="section-tag">Phần I</span>
            <h2>Kết quả Hoạt động Kinh doanh</h2>
            <div class="section-grid">
                <div class="section-text">
                    {html_sections.get("business_performance", "<p>Đang tải dữ liệu phân tích kết quả kinh doanh...</p>")}
                </div>
                <div class="chart-container" id="chart-rev-prof"></div>
            </div>
        </section>
        
        <!-- Section 2: Cơ cấu Tài sản -->
        <section id="cơ-cấu-ts" class="report-section">
            <span class="section-tag">Phần II</span>
            <h2>Cơ cấu và Biến động Tài sản</h2>
            <div class="section-grid">
                <div class="section-text">
                    {html_sections.get("assets_structure", "<p>Đang tải dữ liệu phân tích cơ cấu tài sản...</p>")}
                </div>
                <div class="chart-container" id="chart-asset"></div>
            </div>
        </section>
        
        <!-- Section 3: Nguồn vốn và Nợ -->
        <section id="nguồn-vốn" class="report-section">
            <span class="section-tag">Phần III</span>
            <h2>Cơ cấu Nguồn vốn & Khả năng Thanh toán</h2>
            <div class="section-grid">
                <div class="section-text">
                    {html_sections.get("capital_debts", "<p>Đang tải dữ liệu phân tích nguồn vốn...</p>")}
                </div>
                <div class="chart-container" id="chart-capital"></div>
            </div>
        </section>
        
        <!-- Section 4: Dòng tiền -->
        <section id="dòng-tiền" class="report-section">
            <span class="section-tag">Phần IV</span>
            <h2>Phân tích Lưu chuyển Tiền tệ (Dòng tiền)</h2>
            <div>
                {html_sections.get("cash_flow", "<p>Đang tải dữ liệu phân tích dòng tiền...</p>")}
            </div>
        </section>
        
        <!-- Section 5: Cơ chế từ chối -->
        <section id="cơ-chế-từ-chối" class="report-section">
            <span class="section-tag">Cảnh báo dữ liệu</span>
            <h2>Kiểm soát chất lượng & Dữ liệu năm 2022</h2>
            <div class="refusal-note">
                <h4>Cơ chế Từ chối Trả lời (Abstention Policy)</h4>
                {html_sections.get("abstention_2022", "<p>Chưa thiết lập cơ chế từ chối.</p>")}
            </div>
        </section>
        
        <!-- Section 6: Kết luận -->
        <section id="kết-luận" class="report-section">
            <span class="section-tag">Phần V</span>
            <h2>Kết luận chung & Khuyến nghị</h2>
            <div>
                {html_sections.get("conclusions", "<p>Đang tải kết luận phân tích...</p>")}
            </div>
        </section>
    </main>
</div>

<script>
    // Embed interactive Vega-Lite charts
    const revProfSpec = {json.dumps(chart_specs.get("revenue_profit", {}))};
    const assetSpec = {json.dumps(chart_specs.get("asset_structure", {}))};
    const capitalSpec = {json.dumps(chart_specs.get("capital_structure", {}))};
    
    // Embed configurations
    const embedOpts = {{actions: false, theme: 'dark', renderer: 'svg'}};
    
    vegaEmbed('#chart-rev-prof', revProfSpec, embedOpts).catch(console.error);
    vegaEmbed('#chart-asset', assetSpec, embedOpts).catch(console.error);
    vegaEmbed('#chart-capital', capitalSpec, embedOpts).catch(console.error);
    
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
