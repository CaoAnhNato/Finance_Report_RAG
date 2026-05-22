# Prompt cho AI Coding Agent: Cải thiện bố cục và nội dung báo cáo tài chính

Bạn là AI Coding Agent làm việc trên repository:

`CaoAnhNato/Finance_Report_RAG`

Mục tiêu: chỉnh sửa logic sinh báo cáo tài chính HTML để cải thiện cả **bố cục trình bày** và **nội dung data storytelling** theo bản review “Phân tích bố cục và nội dung báo cáo hiện tại”.

## 1. Bối cảnh hiện tại

Hệ thống hiện sinh báo cáo tài chính A32 giai đoạn 2017–2025 từ pipeline RAG + charting + HTML exporter.

Các file trọng tâm cần kiểm tra và chỉnh sửa:

- `flows/generate_report_flow.py`
- `src/rag_report/exporter/exporter.py`
- `src/rag_report/exporter/charting.py`
- Các file cấu hình hoặc data liên quan nếu cần, đặc biệt dữ liệu tài chính đã xử lý như `company_financials.json`.

Hiện tại báo cáo có các vấn đề chính:

1. Layout mỗi section đang dùng dạng 2 cột:
   - Text ở bên trái.
   - Biểu đồ ở bên phải.
   - Điều này không phù hợp với format báo cáo chuẩn và làm giảm khả năng đọc theo luồng phân tích.

2. Cần đổi sang cấu trúc dọc:
   - Text phân tích trước.
   - Biểu đồ / bảng minh họa ngay bên dưới.
   - Sau biểu đồ cần có đoạn diễn giải / takeaway ngắn để chốt insight.

3. Một số nội dung đã có insight nhưng chưa được biểu đồ hóa đầy đủ:
   - Dòng tiền chưa có biểu đồ.
   - Hàng tồn kho và khoản phải thu đang được phân tích bằng text nhưng biểu đồ tài sản hiện tại chỉ thể hiện tài sản ngắn hạn / dài hạn.
   - Khả năng thanh toán hiện thời và thanh toán nhanh có số liệu phân tích nhưng chưa có biểu đồ riêng.
   - Các biểu đồ hiện tại chủ yếu mô tả số liệu, chưa đủ “data storytelling”: thiếu tiêu đề dạng insight, thiếu annotation, thiếu highlight các mốc quan trọng.

4. Cần áp dụng nguyên tắc:
   - One Chart – One Message.
   - Chart title nên là claim/insight, không chỉ là nhãn mô tả.
   - Text và chart phải hỗ trợ lẫn nhau.
   - Không nhồi quá nhiều series vào một biểu đồ.
   - Dùng annotation/highlight cho các năm quan trọng như 2021 và 2025.
   - Không bịa số liệu. Mọi số liệu phải lấy từ dữ liệu đã xử lý hoặc kết quả RAG có căn cứ.

## 2. Yêu cầu chỉnh sửa layout HTML

Trong `src/rag_report/exporter/exporter.py`, chỉnh lại template HTML/CSS.

### 2.1. Loại bỏ layout 2 cột

Hiện tại `.section-grid` đang dùng `display: grid` và `grid-template-columns: 1.2fr 1fr`.

Hãy thay bằng layout một cột theo thứ tự:

```html
<section class="report-section">
  <span class="section-tag">...</span>
  <h2>...</h2>

  <div class="section-text">
    ... nội dung phân tích ...
  </div>

  <div class="chart-container">
    ... chart ...
  </div>

  <div class="chart-takeaway">
    ... diễn giải ngắn sau chart ...
  </div>
</section>
```

Không để text và chart nằm ngang cạnh nhau ở desktop. Mobile và desktop đều dùng một luồng đọc dọc.

### 2.2. Thêm style cho data storytelling

Bổ sung các class CSS:

- `.section-text`
- `.chart-container`
- `.chart-takeaway`
- `.insight-card`
- `.metric-highlight`
- `.section-lead`
- `.evidence-list`

Yêu cầu style:

- Giữ dark premium theme hiện tại.
- Chart container chiếm full width trong section.
- Biểu đồ có margin-top và margin-bottom hợp lý.
- `.chart-takeaway` là một khung ngắn bên dưới biểu đồ, dùng để kết luận insight chính.
- Không làm báo cáo quá rối mắt.
- Bảo đảm readability tốt trên màn hình rộng.

## 3. Yêu cầu chỉnh sửa cấu trúc báo cáo

Mỗi phần báo cáo nên có format thống nhất:

```markdown
### Insight chính
Một đoạn ngắn 2–4 câu nêu claim chính.

### Bằng chứng số liệu
- Bullet 1: số liệu chính.
- Bullet 2: xu hướng chính.
- Bullet 3: rủi ro hoặc điểm tích cực.

[Biểu đồ minh họa]

### Diễn giải sau biểu đồ
Một đoạn ngắn chốt lại biểu đồ cho thấy điều gì.
```

Không chỉ liệt kê số liệu. Nội dung phải trả lời được:

- Xu hướng là gì?
- Mốc bất thường nằm ở đâu?
- Nguyên nhân hoặc diễn giải tài chính hợp lý là gì?
- Tác động đến doanh nghiệp là gì?
- Rủi ro / cơ hội cần chú ý là gì?

## 4. Yêu cầu cải thiện charting

Trong `src/rag_report/exporter/charting.py`, mở rộng `FinancialCharter` để sinh thêm các biểu đồ cần thiết.

Hiện tại đang có:

- `revenue_profit`
- `asset_structure`
- `capital_structure`

Cần bổ sung tối thiểu các chart sau:

### 4.1. Cash flow chart

Tên key đề xuất:

```python
"cash_flow"
```

Biểu đồ nên thể hiện:

- CFO: dòng tiền từ hoạt động kinh doanh.
- CFI: dòng tiền từ hoạt động đầu tư.
- CFF: dòng tiền từ hoạt động tài chính.

Gợi ý chart:

- Grouped bar chart hoặc line chart.
- Trục x: năm.
- Trục y: tỷ VND.
- Màu khác nhau cho CFO, CFI, CFF.
- Có tooltip.
- Title dạng insight, ví dụ:
  “Dòng tiền kinh doanh duy trì dương, trong khi dòng tiền tài chính thường âm do chi trả cổ tức”.

Nếu data không có đủ CFO/CFI/CFF, không được bịa. Hãy xử lý gracefully:

- Không render chart nếu thiếu dữ liệu.
- Hiển thị thông báo trong HTML: “Không đủ dữ liệu để hiển thị biểu đồ dòng tiền.”

### 4.2. Inventory and receivables trend chart

Tên key đề xuất:

```python
"working_capital"
```

Biểu đồ thể hiện:

- Hàng tồn kho.
- Các khoản phải thu ngắn hạn / phải thu khách hàng nếu có.

Mục tiêu insight:

- Tồn kho tăng mạnh giai đoạn COVID, sau đó giảm dần.
- Khoản phải thu duy trì cao, phản ánh áp lực vốn lưu động hoặc chính sách bán chịu.

Gợi ý chart:

- Line chart hai series.
- Highlight năm 2021.
- Title dạng insight:
  “Tồn kho đạt đỉnh năm 2021 rồi giảm dần, cho thấy quá trình giải phóng vốn lưu động”.

### 4.3. Liquidity ratio chart

Tên key đề xuất:

```python
"liquidity_ratios"
```

Biểu đồ thể hiện:

- Current ratio = tài sản ngắn hạn / nợ ngắn hạn.
- Quick ratio = (tài sản ngắn hạn - hàng tồn kho) / nợ ngắn hạn.

Nếu trong JSON chưa có ratio, hãy tính từ các field có sẵn.

Lưu ý:

- Không chia các ratio cho `1e9`.
- Chỉ chia tiền tệ cho `1e9`.
- Thêm đường tham chiếu y = 1.0 để đánh dấu ngưỡng an toàn thanh khoản.
- Title dạng insight:
  “Thanh toán hiện thời trên 1 lần, nhưng thanh toán nhanh vẫn chịu áp lực do tồn kho”.

### 4.4. Optional: margin chart

Nếu dữ liệu có đủ `doanh_thu` và `lnst`, thêm:

```python
"net_margin"
```

Net margin = LNST / doanh thu.

Mục tiêu:

- Cho thấy doanh thu tăng chưa chắc đi kèm hiệu quả lợi nhuận tương ứng.
- Làm rõ năm 2021 giảm hiệu quả do chi phí tăng.

## 5. Yêu cầu cải thiện biểu đồ hiện tại

### 5.1. Revenue & profit chart

Biểu đồ hiện tại có doanh thu dạng bar và LNST dạng line. Cần cải thiện:

- Title nên chuyển từ mô tả sang insight.
- Thêm tooltip cho năm, doanh thu, LNST.
- Highlight hoặc annotation:
  - 2020: LNST đạt đỉnh giai đoạn đầu.
  - 2021: doanh thu và lợi nhuận giảm do COVID.
  - 2025: doanh thu đạt mức cao mới.

Không nhất thiết annotation phải quá phức tạp, nhưng cần có ít nhất một cách nhấn mạnh mốc bất thường.

### 5.2. Asset structure chart

Giữ chart tài sản ngắn hạn / dài hạn nhưng không dùng nó để thay thế phân tích tồn kho.

- Title nên thể hiện insight:
  “Tài sản ngắn hạn luôn chiếm tỷ trọng chủ đạo trong cơ cấu tài sản A32”.
- Tooltip cần hiển thị giá trị tỷ VND.
- Nếu có thể, thêm tỷ trọng % trong tooltip.

### 5.3. Capital structure chart

Giữ chart nợ phải trả / vốn chủ sở hữu.

- Title nên thể hiện insight:
  “Nợ phải trả thường cao hơn vốn chủ sở hữu nhưng vẫn chủ yếu là nợ ngắn hạn vận hành”.
- Nếu có field nợ ngắn hạn, có thể bổ sung chart riêng hoặc tooltip bổ sung.
- Không gộp quá nhiều thông tin vào một chart nếu làm giảm readability.

## 6. Yêu cầu chỉnh `export_charts_json`

Trong `FinancialCharter.export_charts_json(...)`, cập nhật để export thêm các chart mới:

```python
paths = {
    "revenue_profit": "...",
    "asset_structure": "...",
    "working_capital": "...",
    "capital_structure": "...",
    "liquidity_ratios": "...",
    "cash_flow": "...",
    # optional
    "net_margin": "..."
}
```

Chỉ export chart nếu dữ liệu đủ field. Nếu thiếu field:

- Log warning.
- Không crash pipeline.
- Trả về chart spec rỗng hoặc bỏ key một cách có kiểm soát.
- HTML exporter phải xử lý được trường hợp thiếu chart.

## 7. Yêu cầu chỉnh `HTMLExporter.compile_report`

Trong `src/rag_report/exporter/exporter.py`, cần:

1. Đọc tất cả chart specs mới.
2. Embed chart theo đúng section.
3. Không hard-code chỉ 3 chart như hiện tại.
4. Tạo helper JavaScript để embed chart an toàn.

Ví dụ logic mong muốn:

```javascript
function safeEmbedChart(selector, spec, emptyMessage) {
  if (!spec || Object.keys(spec).length === 0) {
    const el = document.querySelector(selector);
    if (el) el.innerHTML = `<p class="empty-chart-message">${emptyMessage}</p>`;
    return;
  }
  vegaEmbed(selector, spec, embedOpts).catch(console.error);
}
```

Sau đó gọi:

```javascript
safeEmbedChart('#chart-rev-prof', revProfSpec, 'Không đủ dữ liệu để hiển thị biểu đồ doanh thu và lợi nhuận.');
safeEmbedChart('#chart-asset', assetSpec, 'Không đủ dữ liệu để hiển thị biểu đồ cơ cấu tài sản.');
safeEmbedChart('#chart-working-capital', workingCapitalSpec, 'Không đủ dữ liệu để hiển thị biểu đồ vốn lưu động.');
safeEmbedChart('#chart-capital', capitalSpec, 'Không đủ dữ liệu để hiển thị biểu đồ cơ cấu nguồn vốn.');
safeEmbedChart('#chart-liquidity', liquiditySpec, 'Không đủ dữ liệu để hiển thị biểu đồ thanh khoản.');
safeEmbedChart('#chart-cash-flow', cashFlowSpec, 'Không đủ dữ liệu để hiển thị biểu đồ dòng tiền.');
```

## 8. Yêu cầu chỉnh nội dung RAG query và fallback

Trong `flows/generate_report_flow.py`, cập nhật phần `FALLBACK_ANALYSIS` và `queries`.

### 8.1. Không viết nội dung theo kiểu liệt kê thuần túy

Mỗi section phải có narrative rõ:

- Claim chính.
- Evidence.
- Ý nghĩa tài chính.
- Rủi ro / khuyến nghị.

### 8.2. Query RAG nên ép mô hình trả lời theo cấu trúc data storytelling

Ví dụ với section doanh thu:

```python
"business_performance": (
    "Phân tích kết quả kinh doanh A32 giai đoạn 2017-2025 theo cấu trúc data storytelling: "
    "1) insight chính về doanh thu và LNST; "
    "2) các mốc bất thường như 2020, 2021, 2025; "
    "3) bằng chứng số liệu ngắn gọn; "
    "4) diễn giải ý nghĩa tài chính; "
    "5) kết luận ngắn để đặt ngay sau biểu đồ. "
    "Không bịa số liệu, chỉ dùng dữ liệu trong báo cáo."
)
```

Làm tương tự cho:

- `assets_structure`
- `capital_debts`
- `cash_flow`
- `abstention_2022`
- `conclusions`

### 8.3. Giữ abstention policy cho năm 2022

Không được suy diễn số liệu năm 2022. Nếu người dùng hoặc report cần nhắc đến năm 2022:

- Phải nói rõ dữ liệu BCTC kiểm toán năm 2022 không có trong hệ thống.
- Không interpolate.
- Không dùng web.
- Không tự tạo số liệu.

## 9. Cấu trúc HTML mong muốn sau chỉnh sửa

Báo cáo cuối nên có flow như sau:

### Header

- Tên công ty.
- Giai đoạn phân tích.
- Ghi chú dữ liệu: có dữ liệu 2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025; thiếu 2022.

### Executive Summary

Thêm section đầu báo cáo trước Phần I:

- 3–5 insight lớn nhất.
- Ví dụ:
  - Doanh thu phục hồi và đạt mức cao mới năm 2025.
  - LNST chịu cú sốc năm 2021 nhưng phục hồi về sau.
  - Tài sản ngắn hạn chiếm tỷ trọng lớn, tồn kho giảm dần sau giai đoạn COVID.
  - Nợ phải trả cao hơn vốn chủ sở hữu nhưng chủ yếu là nợ vận hành.
  - Thanh khoản nhanh cần theo dõi do phụ thuộc vào hàng tồn kho.

### Phần I – Kết quả kinh doanh

- Text insight.
- Chart doanh thu & LNST.
- Takeaway sau chart.

### Phần II – Tài sản và vốn lưu động

- Text insight về cơ cấu tài sản.
- Chart cơ cấu tài sản.
- Takeaway.
- Text insight về tồn kho và phải thu.
- Chart working capital.
- Takeaway.

### Phần III – Nguồn vốn và thanh khoản

- Text insight về nợ và vốn chủ sở hữu.
- Chart capital structure.
- Takeaway.
- Text insight về khả năng thanh toán.
- Chart liquidity ratios.
- Takeaway.

### Phần IV – Dòng tiền

- Text insight về CFO/CFI/CFF.
- Chart cash flow.
- Takeaway.

### Cảnh báo dữ liệu năm 2022

- Giữ box abstention.
- Nói rõ không có dữ liệu 2022.

### Kết luận & khuyến nghị

- Tổng hợp lại bức tranh tài chính.
- Nêu rõ:
  - Điểm mạnh.
  - Rủi ro.
  - Khuyến nghị quản trị.
  - Góc nhìn nhà đầu tư.

## 10. Yêu cầu về chất lượng code

- Không phá vỡ flow hiện tại.
- Không hard-code số liệu mới nếu có thể lấy từ `company_financials.json`.
- Không dùng số liệu từ internet.
- Không thêm dependency nặng nếu không cần.
- Nếu thêm helper function, đặt tên rõ ràng.
- Code cần dễ mở rộng khi sau này thêm công ty khác hoặc năm khác.
- Nên log warning khi thiếu field dữ liệu thay vì crash.
- Giữ khả năng chạy fallback mode.

## 11. Acceptance Criteria

Sau khi chỉnh xong, cần đảm bảo:

1. Chạy được:

```bash
python flows/generate_report_flow.py
```

hoặc lệnh tương đương đang dùng trong repo.

2. File HTML output vẫn được sinh ra thành công.

3. Trên desktop, không còn section nào dùng layout text bên trái và chart bên phải.

4. Mỗi chart nằm dưới đoạn text liên quan.

5. Có ít nhất các chart:
   - Revenue & Profit.
   - Asset Structure.
   - Working Capital / Inventory & Receivables.
   - Capital Structure.
   - Liquidity Ratios.
   - Cash Flow.

6. Nếu thiếu dữ liệu cho chart nào, HTML hiển thị thông báo thiếu dữ liệu thay vì lỗi JavaScript.

7. Tiêu đề chart được viết theo dạng insight, không chỉ là nhãn mô tả.

8. Có section Executive Summary.

9. Năm 2022 được xử lý bằng abstention, không có số liệu bịa.

10. Báo cáo cuối thể hiện được:
   - Bức tranh tài chính tổng quát.
   - Xu hướng nhiều năm.
   - Các vấn đề tồn đọng / rủi ro.
   - Kết luận và khuyến nghị.

## 12. Output mong muốn từ AI Coding Agent

Sau khi chỉnh sửa, hãy trả về:

1. Danh sách file đã thay đổi.
2. Tóm tắt thay đổi chính.
3. Cách chạy lại report.
4. Các chart mới đã thêm.
5. Các trường dữ liệu bắt buộc trong `company_financials.json`.
6. Ghi chú nếu field nào còn thiếu và cần bổ sung trong bước data extraction.

## Ghi chú triển khai

Với prompt này, nên chạy agent ở chế độ có quyền đọc toàn repo trước, sau đó để nó tự xác định field thật trong `company_financials.json`.

Điểm quan trọng nhất là không chỉ sửa CSS, mà phải sửa cả logic charting và cấu trúc section để báo cáo thật sự chuyển từ “dashboard mô tả” sang “financial data story”.
