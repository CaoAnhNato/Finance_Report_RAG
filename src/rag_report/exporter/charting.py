import os
import json
import logging
import pandas as pd
import altair as alt

from src.rag_report.config import settings

logger = logging.getLogger(__name__)

class FinancialCharter:
    """Generates premium financial charts using Altair and exports them as Vega-Lite JSON configurations."""
    
    def __init__(self, data_path: str = None) -> None:
        self.data_path = data_path or os.path.join(settings.PROCESSED_DIR, "company_financials.json")
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Financials JSON not found at {self.data_path}")
            
    def load_data(self) -> pd.DataFrame:
        """Load financials JSON into a clean pandas DataFrame."""
        with open(self.data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        records = []
        for year, metrics in data.items():
            record = {"year": int(year)}
            for k, v in metrics.items():
                # Convert VND to Billion VND for better readability in charts
                record[k] = v / 1e9
            records.append(record)
            
        df = pd.DataFrame(records).sort_values("year")
        return df

    def generate_revenue_profit_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a dual-axis line-bar chart for Revenue and Profit After Tax."""
        base = alt.Chart(df).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False))
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Doanh thu thuần A32 lập kỷ lục mới năm 2025, LNST phục hồi sau cú sốc đại dịch",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        )
        
        # Bars for Revenue
        bar = base.mark_bar(
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4,
            color='#3B82F6', # Sleek blue
            size=30
        ).encode(
            y=alt.Y('doanh_thu:Q', title='Doanh thu thuần', axis=alt.Axis(titleColor='#3B82F6', gridColor='#374151'))
        )
        
        # Line for Net Profit
        line = base.mark_line(
            color='#10B981', # Emerald green
            strokeWidth=3,
            point=alt.OverlayMarkDef(color='#10B981', size=60, filled=True)
        ).encode(
            y=alt.Y('lnst:Q', title='Lợi nhuận sau thuế (LNST)', axis=alt.Axis(titleColor='#10B981', grid=False))
        )
        
        # Combine
        chart = alt.layer(bar, line).resolve_scale(
            y='independent'
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        
        return chart

    def generate_asset_structure_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a stacked bar chart for Asset Structure (Current vs Non-current)."""
        df_melted = df.melt(
            id_vars=['year'],
            value_vars=['ts_ngan_han', 'ts_dai_han'],
            var_name='asset_type',
            value_name='value'
        )
        
        type_mapping = {
            'ts_ngan_han': 'Tài sản ngắn hạn',
            'ts_dai_han': 'Tài sản dài hạn'
        }
        df_melted['asset_type'] = df_melted['asset_type'].map(type_mapping)
        
        chart = alt.Chart(df_melted).mark_bar(
            size=30,
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            y=alt.Y('value:Q', title='Giá trị (Tỷ VND)', axis=alt.Axis(gridColor='#374151')),
            color=alt.Color(
                'asset_type:N',
                title='Cấu trúc Tài sản',
                scale=alt.Scale(
                    domain=['Tài sản ngắn hạn', 'Tài sản dài hạn'],
                    range=['#3B82F6', '#8B5CF6'] # Blue vs Purple
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Tài sản ngắn hạn luôn chiếm tỷ trọng chủ đạo trên 74% trong cơ cấu tài sản",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        
        return chart

    def generate_working_capital_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a line chart for Working Capital (Inventory & Receivables trend)."""
        df_melted = df.melt(
            id_vars=['year'],
            value_vars=['hang_ton_kho', 'phai_thu_ngan_han'],
            var_name='item_type',
            value_name='value'
        )
        type_mapping = {
            'hang_ton_kho': 'Hàng tồn kho',
            'phai_thu_ngan_han': 'Phải thu ngắn hạn'
        }
        df_melted['item_type'] = df_melted['item_type'].map(type_mapping)
        
        chart = alt.Chart(df_melted).mark_line(
            strokeWidth=3,
            point=alt.OverlayMarkDef(size=50, filled=True)
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            y=alt.Y('value:Q', title='Giá trị (Tỷ VND)', axis=alt.Axis(gridColor='#374151')),
            color=alt.Color(
                'item_type:N',
                title='Danh mục',
                scale=alt.Scale(
                    domain=['Hàng tồn kho', 'Phải thu ngắn hạn'],
                    range=['#F59E0B', '#3B82F6'] # Amber vs Blue
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Tồn kho đạt đỉnh năm 2021 rồi giảm dần, phải thu ngắn hạn tăng mạnh năm 2025",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        return chart

    def generate_capital_structure_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a stacked bar chart for Capital Structure (Liabilities vs Equity)."""
        df_melted = df.melt(
            id_vars=['year'],
            value_vars=['no_phai_tra', 'vốn_csh'],
            var_name='capital_type',
            value_name='value'
        )
        
        type_mapping = {
            'no_phai_tra': 'Nợ phải trả',
            'vốn_csh': 'Vốn chủ sở hữu'
        }
        df_melted['capital_type'] = df_melted['capital_type'].map(type_mapping)
        
        chart = alt.Chart(df_melted).mark_bar(
            size=30,
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            y=alt.Y('value:Q', title='Giá trị (Tỷ VND)', axis=alt.Axis(gridColor='#374151')),
            color=alt.Color(
                'capital_type:N',
                title='Cấu trúc Nguồn vốn',
                scale=alt.Scale(
                    domain=['Nợ phải trả', 'Vốn chủ sở hữu'],
                    range=['#EF4444', '#10B981'] # Red vs Emerald Green
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Nợ phải trả cao hơn vốn chủ sở hữu nhưng chủ yếu là nợ ngắn hạn vận hành",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        
        return chart

    def generate_liquidity_ratios_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a line chart for Liquidity Ratios (Current and Quick ratios) with reference line y=1.0."""
        df_calc = df.copy()
        df_calc['current_ratio'] = df_calc.apply(
            lambda r: r['ts_ngan_han'] / r['no_ngan_han'] if r['no_ngan_han'] > 0 else 0, axis=1
        )
        df_calc['quick_ratio'] = df_calc.apply(
            lambda r: (r['ts_ngan_han'] - r['hang_ton_kho']) / r['no_ngan_han'] if r['no_ngan_han'] > 0 else 0, axis=1
        )
        
        df_ratios = df_calc.melt(
            id_vars=['year'],
            value_vars=['current_ratio', 'quick_ratio'],
            var_name='ratio_type',
            value_name='ratio_val'
        )
        ratio_mapping = {
            'current_ratio': 'Thanh toán hiện thời',
            'quick_ratio': 'Thanh toán nhanh'
        }
        df_ratios['ratio_type'] = df_ratios['ratio_type'].map(ratio_mapping)
        
        lines = alt.Chart(df_ratios).mark_line(
            strokeWidth=3,
            point=alt.OverlayMarkDef(size=50, filled=True)
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            y=alt.Y('ratio_val:Q', title='Hệ số thanh toán (Lần)', axis=alt.Axis(gridColor='#374151')),
            color=alt.Color(
                'ratio_type:N',
                title='Chỉ số thanh khoản',
                scale=alt.Scale(
                    domain=['Thanh toán hiện thời', 'Thanh toán nhanh'],
                    range=['#10B981', '#EF4444'] # Green vs Red
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        )
        
        rule = alt.Chart(pd.DataFrame({'y': [1.0]})).mark_rule(
            color='#EF4444',
            strokeDash=[4, 4],
            strokeWidth=1.5
        ).encode(
            y='y:Q'
        )
        
        chart = alt.layer(lines, rule).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Thanh toán hiện thời vững chắc trên 1.0, thanh toán nhanh chịu áp lực dưới 1.0",
                subtitle="Đơn vị tính: Lần (Đường đứt nét màu đỏ biểu diễn ngưỡng an toàn 1.0)",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        
        return chart

    def generate_cash_flow_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a grouped bar chart for Cash Flows (CFO, CFI, CFF)."""
        df_melted = df.melt(
            id_vars=['year'],
            value_vars=['cfo', 'cfi', 'cff'],
            var_name='flow_type',
            value_name='value'
        )
        type_mapping = {
            'cfo': 'CFO (Kinh doanh)',
            'cfi': 'CFI (Đầu tư)',
            'cff': 'CFF (Tài chính)'
        }
        df_melted['flow_type'] = df_melted['flow_type'].map(type_mapping)
        
        chart = alt.Chart(df_melted).mark_bar(
            cornerRadiusTopLeft=2,
            cornerRadiusTopRight=2
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            xOffset='flow_type:N',
            y=alt.Y('value:Q', title='Giá trị (Tỷ VND)', axis=alt.Axis(gridColor='#374151')),
            color=alt.Color(
                'flow_type:N',
                title='Loại dòng tiền',
                scale=alt.Scale(
                    domain=['CFO (Kinh doanh)', 'CFI (Đầu tư)', 'CFF (Tài chính)'],
                    range=['#10B981', '#3B82F6', '#EF4444']
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Dòng tiền kinh doanh duy trì thặng dư dương lớn, dòng tiền tài chính âm do chi trả cổ tức",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        return chart

    def generate_net_margin_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a line chart for Net Profit Margin."""
        df_calc = df.copy()
        df_calc['net_margin'] = df_calc.apply(
            lambda r: (r['lnst'] / r['doanh_thu']) * 100 if r['doanh_thu'] > 0 else 0, axis=1
        )
        
        chart = alt.Chart(df_calc).mark_line(
            color='#10B981',
            strokeWidth=3,
            point=alt.OverlayMarkDef(color='#10B981', size=50, filled=True)
        ).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False)),
            y=alt.Y('net_margin:Q', title='Biên lợi nhuận ròng (%)', axis=alt.Axis(gridColor='#374151'))
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Biên lợi nhuận ròng phục hồi năm 2025 sau giai đoạn sụt giảm hiệu quả chi phí",
                subtitle="Đơn vị tính: %",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=14,
                fontWeight='bold',
                anchor='start',
                limit=500
            )
        ).configure(
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).configure_axis(
            labelColor='#9CA3AF',
            titleColor='#9CA3AF',
            tickColor='#374151',
            domainColor='#374151'
        )
        return chart

    def export_charts_json(self, output_dir: str) -> dict:
        """Export all charts to Vega-Lite JSON files, handling missing fields gracefully."""
        os.makedirs(output_dir, exist_ok=True)
        df = self.load_data()
        
        generators = {
            "revenue_profit": self.generate_revenue_profit_chart,
            "asset_structure": self.generate_asset_structure_chart,
            "working_capital": self.generate_working_capital_chart,
            "capital_structure": self.generate_capital_structure_chart,
            "liquidity_ratios": self.generate_liquidity_ratios_chart,
            "cash_flow": self.generate_cash_flow_chart,
            "net_margin": self.generate_net_margin_chart
        }
        
        paths = {}
        for key, generator in generators.items():
            path = os.path.join(output_dir, f"{key}.json")
            paths[key] = path
            try:
                chart = generator(df)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(chart.to_json())
            except Exception as e:
                logger.warning(f"Error generating chart '{key}': {e}. Exporting empty configuration.")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("{}")
                    
        logger.info(f"Exported interactive chart JSON specs to {output_dir}")
        return paths

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    charter = FinancialCharter()
    charter.export_charts_json("data/processed/charts")
