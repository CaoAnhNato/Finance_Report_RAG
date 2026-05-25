# Hệ Thống RAG Phân Tích Báo Cáo Tài Chính Tự Động (A32 RAG Report System)

## 📌 Tổng Quan Dự Án
Hệ thống **RAG Report** là giải pháp phân tích báo cáo tài chính tích hợp (Retrieval-Augmented Generation) được thiết kế riêng cho **Công ty Cổ phần 32 (Mã CK: A32)**. Hệ thống tự động thu thập, trích xuất dữ liệu tài chính từ các tài liệu quét OCR (giai đoạn từ 2017 đến 2025, trừ năm 2022 không có báo cáo), lưu trữ đồng bộ vào cơ sở dữ liệu quan hệ địa phương (DuckDB) và cơ sở dữ liệu vector (Qdrant Cloud), sau đó tiến hành truy vấn thông minh thông qua quy trình LangGraph agentic. Kết quả được tổng hợp thành một báo cáo phân tích tài chính tương tác chuẩn Premium dưới dạng file HTML, tích hợp biểu đồ động Altair và hệ thống trích dẫn (citation) chính xác đến từng trang báo cáo gốc.

---

## 🛠️ Kiến Trúc Hệ Thống

Dưới đây là sơ đồ luồng hoạt động tổng thể của hệ thống từ Ingestion đến Generation:

```mermaid
graph TD
    subgraph Ingestion Pipeline (Prefect Flow)
        A[Báo cáo tài chính OCR .txt] --> B[FinancialReportParser]
        B --> C[Phân tích bảng & Trích xuất Fact bằng LLM]
        C --> D[Tính Embeddings - FPT Cloud API]
        D --> E[(DuckDB - Lưu trữ Chunk & Metadata)]
        D --> F[(Qdrant Cloud - Vector Database)]
    end

    subgraph Query & Generation Pipeline (LangGraph Workflow)
        G[User Query / Section Plan] --> H[Query Planner Node]
        H --> I{Xác định Năm & Hợp lệ?}
        I -- 2022 hoặc Không hợp lệ --> J[Abstention Node - Từ chối trả lời]
        I -- Hợp lệ --> K[Hybrid Retriever Node - DuckDB + Qdrant]
        K --> L[Reciprocal Rank Fusion - RRF]
        L --> M[FPT Cloud Reranker Node]
        M --> N[Generate Node - Trích dẫn chính xác trang]
        N --> O[HTML Exporter - Kết hợp biểu đồ Altair]
        O --> P[Báo cáo HTML Premium có Tooltip Trích Dẫn]
    end
```

---

## ✨ Tính Năng Nổi Bật

### 1. Ingestion Pipeline thông minh & Fact Extraction
- **Phân tách Chunk theo trang & Bảng biểu**: Cấu trúc trang của tài liệu báo cáo tài chính gốc được bảo toàn thông qua `FinancialReportParser` bằng cách định vị thẻ phân trang và tách biệt bảng biểu/văn bản thường.
- **Trích xuất sự kiện tài chính (Fact Extraction)**: Sử dụng mô hình LLM để tiền xử lý và trích xuất các thông tin số liệu cốt lõi trong mỗi trang, giảm thiểu nhiễu thông tin khi embedding và hỗ trợ việc đối chiếu số liệu có độ chính xác cao.
- **Đồng bộ hóa Vector & Metadata**:
  - **DuckDB**: Lưu trữ dữ liệu cấu trúc phục vụ tìm kiếm từ khóa nâng cao (Keyword Search).
  - **Qdrant Cloud**: Lưu trữ dense vectors phục vụ tìm kiếm ngữ nghĩa (Semantic Search).

### 2. Bộ tìm kiếm lai Hybrid Retriever & Rerank vượt trội
- **Reciprocal Rank Fusion (RRF)**: Kết hợp kết quả tìm kiếm từ khóa từ DuckDB và tìm kiếm vector từ Qdrant Cloud để cải thiện độ phủ và độ chính xác thu thập dữ liệu (Hit Rate).
- **FPT Cloud Embedding & Reranker**:
  - Tích hợp API Embedding tiếng Việt chuyên sâu từ FPT Cloud nhằm tối ưu hóa ngữ nghĩa tài chính tiếng Việt.
  - Sử dụng FPT Cloud Reranker ở giai đoạn 2 để xếp hạng lại độ liên quan của các đoạn tài liệu trước khi đưa vào mô hình sinh sinh văn bản, giúp lọc bỏ các văn cảnh nhiễu dưới ngưỡng `DEFAULT_RERANK_THRESHOLD`.

### 3. Quy trình điều hướng LangGraph Agentic
- **Planner Node**: Nhận diện năm tài chính mục tiêu từ câu hỏi của người dùng và thiết lập kế hoạch tìm kiếm phụ (Sub-questions).
- **Abstention Node (Chế độ từ chối thông minh)**: Do doanh nghiệp A32 không có báo cáo tài chính chính thức năm 2022, hệ thống tự động nhận diện và từ chối phân tích các yêu cầu liên quan đến năm 2022 hoặc khi độ liên quan của dữ liệu trích xuất quá thấp.
- **Fact-grounded Generation**: Buộc mô hình LLM chỉ sinh văn bản dựa trên thông tin đã trích dẫn trực tiếp từ báo cáo với cấu trúc `[BCTC <Năm>, trang <Số>]`, loại bỏ hoàn toàn hiện tượng ảo tưởng (hallucination).

### 4. Báo cáo tài chính Premium (Premium HTML & Interactive Charts)
- **Interactive Altair Charts**: Tự động tổng hợp số liệu tài chính của doanh nghiệp qua các năm và vẽ biểu đồ động dưới dạng Vega-Lite JSON (Doanh thu & Lợi nhuận, Cơ cấu Tài sản, Vốn lưu động, Cơ cấu Nguồn vốn, Chỉ số Thanh khoản, Dòng tiền tệ, Biên lợi nhuận).
- **Keyword Highlighting**: Tự động làm nổi bật các thực thể tiền tệ, tỷ phần phần trăm, tỷ số tài chính.
- **Dynamic Tooltips**: Khi người dùng hover chuột vào bất kỳ trích dẫn nào trong báo cáo HTML, hệ thống sẽ hiển thị một popup chứa nội dung gốc chi tiết từ trang báo cáo đó để đối chiếu trực tiếp.

### 5. Hệ thống đánh giá toàn diện RAG Triad & Evaluation
- Đánh giá chất lượng RAG qua tập 30 câu hỏi chuẩn hóa trong `data/A32/question_eval.json`.
- Các chỉ số đánh giá bao gồm: **Hit@K**, **MRR (Mean Reciprocal Rank)**, **Numeric Accuracy** (độ chính xác số liệu), **Abstention Accuracy** (độ chính xác khi từ chối trả lời).

---

## 📁 Cấu Trúc Thư Mục Dự Án

Xem chi tiết trong file [project-structure.yaml](project-structure.yaml). Dưới đây là tóm tắt các thư mục chính:
- **`src/rag_report`**: Mã nguồn lõi của hệ thống RAG.
  - `config/`: Quản lý cấu hình, tham số hệ thống và cài đặt logging.
  - `schemas/`: Định nghĩa Pydantic models lưu trữ siêu dữ liệu tài liệu và chunk.
  - `ingestion/`: Triển khai parser, FPT embedding client, DuckDB store, và đồng bộ vector với Qdrant.
  - `query/`: Công cụ lên kế hoạch truy vấn, Hybrid Retriever, FPT Reranker và LangGraph Workflow.
  - `evaluation/`: Đánh giá các chỉ số RAG Triad.
  - `exporter/`: Vẽ biểu đồ Altair và xuất bản báo cáo HTML Premium.
- **`flows/`**: Chứa các kịch bản chạy luồng dữ liệu tự động với Prefect.
- **`tests/`**: Chứa các kịch bản kiểm thử độc lập (smoke tests) cho từng thành phần dịch vụ Cloud/API.
- **`data/`**: Chứa dữ liệu đầu vào (tập tin OCR txt), dữ liệu phân tích đã xử lý, cơ sở dữ liệu DuckDB cục bộ và tài liệu đánh giá.

---

## ⚙️ Cài Đặt & Cấu Hình

### 1. Chuẩn bị môi trường
Yêu cầu Python phiên bản 3.10 trở lên. Khởi tạo và kích hoạt môi trường ảo Python:
```bash
python -m venv .venv
source .venv/bin/activate  # Trên Windows sử dụng: .venv\Scripts\activate
```

Cài đặt các gói thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường
Tạo file `.env` tại thư mục gốc của dự án với các thông số cấu hình sau:
```env
# Hugging Face Token (dùng cho model download nếu có)
HF_TOKEN=your_hf_token

# Llama Cloud API (nếu cần phân tích PDF nâng cao)
LLAMA_CLOUD_API_KEY=your_llama_cloud_key

# Qdrant Cloud Configuration
QDRANT_URL=https://your-qdrant-instance.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=finance_report_a32

# FPT Cloud API Services (Embedding & Reranker)
FPT_API_KEY=your_fpt_api_key
FPT_RERANK_URL=https://api.fpt.ai/v5/rerank
FPT_RERANK_MODEL=vietnamese-reranker

# OpenAI API Configuration
OPENAI_API_KEY=sk-proj-your_openai_key
OPENAI_API_BASE=https://api.openai.com/v1
```

---

## 🚀 Hướng Dẫn Vận Hành

Hệ thống có thể chạy thông qua CLI (xem chi tiết tại [run.txt](run.txt)). Dưới đây là các câu lệnh chính:

### 1. Chạy luồng Ingestion (Prefect Flow)
Thực hiện quét, tách trang báo cáo OCR, sinh embedding và đẩy lên DuckDB/Qdrant:
```bash
python flows/prefect_ingestion_flow.py
```

### 2. Sinh Báo Cáo Tài Chính Premium (Prefect Flow)
Lệnh sinh toàn bộ báo cáo phân tích tài chính tĩnh Premium kết hợp biểu đồ động Altair:
```bash
# Chạy ở chế độ thực tế: Sử dụng RAG Engine kết nối OpenAI & Qdrant Cloud
python flows/generate_report_flow.py --no-fallback

# Chạy ở chế độ Fallback: Sử dụng dữ liệu tài chính tĩnh đã được xác thực (Tránh tốn kém chi phí API khi phát triển giao diện)
python flows/generate_report_flow.py --fallback
```
*Kết quả báo cáo HTML Premium sẽ được lưu tại thư mục `data/reports/`.*

### 3. Chạy các bài đánh giá (Evaluation)
Thực hiện chạy bộ đánh giá tự động dựa trên tập 30 câu hỏi để đo lường Hit Rate, MRR, độ chính xác số liệu và khả năng từ chối:
```bash
python -m src.rag_report.evaluation.evaluator
```

### 4. Chạy các bài kiểm thử độc lập (Smoke Tests)
Trước khi chạy toàn bộ pipeline, hãy chắc chắn kiểm tra các dịch vụ kết nối đơn lẻ thông qua thư mục `tests/`:
```bash
# Kiểm tra kết nối và truy vấn Qdrant Cloud
python tests/smoke_test_qdrant.py

# Kiểm tra kết nối API FPT Embedding
python tests/smoke_test_fpt_embedding.py

# Kiểm tra kết nối API FPT Reranker
python tests/smoke_test_fpt_rerank.py

# Kiểm tra quy trình dựng biểu đồ Altair
python tests/test_chart_export.py
```

---

## ⚠️ Quy Tắc Phát Triển Đặc Biệt (Cần Tuân Thủ)

- **Quy tắc Kiểm thử độc lập (Smoke Tests)**: Khi thay đổi bất kỳ thành phần logic, API hay nhà cung cấp dịch vụ Cloud nào, bắt buộc phải viết smoke test cho riêng phần đó để kiểm thử hoạt động ổn định của đơn vị trước khi ghép vào pipeline lớn.
- **Phân tách môi trường DB khi kiểm thử**: Đảm bảo tham số tên database/collection vector của các lần gọi từ `smoke-test` phải khác với tên triển khai trong pipeline chính của hệ thống, tránh việc dồn dữ liệu rác vào chung một database sản xuất.
- **Tiêu chuẩn đầu ra (Alignment Output)**: Đầu ra của mỗi component (trích xuất facts, planner, retriever) phải được kiểm chứng tính logic và ngữ nghĩa hợp lý khi chạy smoke-test, tránh trường hợp code chạy thông suốt nhưng số liệu trích xuất sai lệch so với báo cáo gốc.
- **Xử lý ngoại lệ 2022**: Hệ thống được cài đặt bộ lọc Planner và Abstention Node cứng đối với năm 2022. Tuyệt đối không để LLM cố gắng suy luận/bịa đặt dữ liệu tài chính của A32 cho năm này.
