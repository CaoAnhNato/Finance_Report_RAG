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
        # Enable dark/premium theme styling
        base = alt.Chart(df).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False))
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Diễn biến Doanh thu & Lợi nhuận sau thuế",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=16,
                fontWeight='bold',
                anchor='start'
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
        # Melt dataframe for stacked representation
        df_melted = df.melt(
            id_vars=['year'],
            value_vars=['ts_ngan_han', 'ts_dai_han'],
            var_name='asset_type',
            value_name='value'
        )
        
        # Map labels
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
                text="Cơ cấu Tài sản qua các năm",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=16,
                fontWeight='bold',
                anchor='start'
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
                text="Cơ cấu Nguồn vốn qua các năm",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=16,
                fontWeight='bold',
                anchor='start'
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
                text="Diễn biến Dòng tiền (CFO, CFI, CFF)",
                subtitle="Đơn vị tính: Tỷ VND",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=16,
                fontWeight='bold',
                anchor='start'
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

    def generate_liquidity_working_capital_chart(self, df: pd.DataFrame) -> alt.Chart:
        """Create a dual-axis chart for Working Capital (bars) and Liquidity Ratios (lines)."""
        df_calc = df.copy()
        df_calc['working_capital'] = df_calc['ts_ngan_han'] - df_calc['no_ngan_han']
        # Avoid division by zero
        df_calc['current_ratio'] = df_calc.apply(
            lambda r: r['ts_ngan_han'] / r['no_ngan_han'] if r['no_ngan_han'] > 0 else 0, axis=1
        )
        df_calc['quick_ratio'] = df_calc.apply(
            lambda r: (r['ts_ngan_han'] - r['hang_ton_kho']) / r['no_ngan_han'] if r['no_ngan_han'] > 0 else 0, axis=1
        )
        
        base = alt.Chart(df_calc).encode(
            x=alt.X('year:O', title='Năm tài chính', axis=alt.Axis(labelAngle=0, grid=False))
        ).properties(
            width=550,
            height=320,
            title=alt.TitleParams(
                text="Khả năng thanh khoản & Vốn lưu động",
                subtitle="Vốn lưu động (Tỷ VND, Cột) vs Hệ số thanh toán (Đường)",
                color='#F3F4F6',
                subtitleColor='#9CA3AF',
                fontSize=16,
                fontWeight='bold',
                anchor='start'
            )
        )
        
        bar = base.mark_bar(
            color='#3B82F6',
            opacity=0.6,
            size=25,
            cornerRadiusTopLeft=3,
            cornerRadiusTopRight=3
        ).encode(
            y=alt.Y('working_capital:Q', title='Vốn lưu động ròng (Tỷ VND)', axis=alt.Axis(titleColor='#3B82F6', gridColor='#374151'))
        )
        
        df_ratios = df_calc.melt(
            id_vars=['year'],
            value_vars=['current_ratio', 'quick_ratio'],
            var_name='ratio_type',
            value_name='ratio_val'
        )
        ratio_mapping = {
            'current_ratio': 'Thanh toán hiện hành (Lần)',
            'quick_ratio': 'Thanh toán nhanh (Lần)'
        }
        df_ratios['ratio_type'] = df_ratios['ratio_type'].map(ratio_mapping)
        
        line = alt.Chart(df_ratios).mark_line(
            strokeWidth=3,
            point=alt.OverlayMarkDef(size=50, filled=True)
        ).encode(
            x=alt.X('year:O', title='Năm tài chính'),
            y=alt.Y('ratio_val:Q', title='Hệ số thanh toán (Lần)', axis=alt.Axis(titleColor='#10B981', grid=False)),
            color=alt.Color(
                'ratio_type:N',
                title='Chỉ số thanh khoản',
                scale=alt.Scale(
                    domain=['Thanh toán hiện hành (Lần)', 'Thanh toán nhanh (Lần)'],
                    range=['#10B981', '#F59E0B'] # Green vs Yellow/Amber
                ),
                legend=alt.Legend(orient='bottom', labelColor='#9CA3AF', titleColor='#9CA3AF')
            )
        )
        
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

    def export_charts_json(self, output_dir: str) -> dict:
        """Export all charts to Vega-Lite JSON files."""
        os.makedirs(output_dir, exist_ok=True)
        df = self.load_data()
        
        c1 = self.generate_revenue_profit_chart(df)
        c2 = self.generate_asset_structure_chart(df)
        c3 = self.generate_capital_structure_chart(df)
        c4 = self.generate_cash_flow_chart(df)
        c5 = self.generate_liquidity_working_capital_chart(df)
        
        paths = {
            "revenue_profit": os.path.join(output_dir, "revenue_profit.json"),
            "asset_structure": os.path.join(output_dir, "asset_structure.json"),
            "capital_structure": os.path.join(output_dir, "capital_structure.json"),
            "cash_flow": os.path.join(output_dir, "cash_flow.json"),
            "liquidity_working_capital": os.path.join(output_dir, "liquidity_working_capital.json")
        }
        
        with open(paths["revenue_profit"], "w", encoding="utf-8") as f:
            f.write(c1.to_json())
        with open(paths["asset_structure"], "w", encoding="utf-8") as f:
            f.write(c2.to_json())
        with open(paths["capital_structure"], "w", encoding="utf-8") as f:
            f.write(c3.to_json())
        with open(paths["cash_flow"], "w", encoding="utf-8") as f:
            f.write(c4.to_json())
        with open(paths["liquidity_working_capital"], "w", encoding="utf-8") as f:
            f.write(c5.to_json())
            
        logger.info(f"Exported interactive chart JSON specs to {output_dir}")
        return paths

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    charter = FinancialCharter()
    charter.export_charts_json("data/processed/charts")
