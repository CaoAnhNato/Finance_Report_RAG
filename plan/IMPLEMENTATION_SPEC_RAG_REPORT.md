# IMPLEMENTATION SPEC — RAG REPORT từ OCR `.txt` báo cáo tài chính

Tài liệu này dùng như file triển khai cho AI Coding để build hệ thống RAG REPORT sinh báo cáo insight từ OCR `.txt` báo cáo tài chính. Mục tiêu là xây dựng pipeline end-to-end từ ingestion dữ liệu, chuẩn hóa OCR, chunking, embedding qua LlamaIndex Cloud, lưu vector vào Qdrant Cloud, retrieval/rerank, LLM tool-calling, sinh biểu đồ Altair offline, sinh report cuối cùng và evaluation bằng `question_eval.json`.

> Tuyệt đối không hard-code API key trong source code. Tất cả key phải đặt trong `.env`, `.env.local` hoặc secret manager. Các key từng paste trong notebook/prompt nên được rotate lại trước khi đưa vào hệ thống thật.

---

## 1. Kiến trúc tổng thể

```text
OCR .txt reports
    ↓
Prefect ingestion flow
    ↓
OCR normalizer + page parser + section detector
    ↓
table parser + financial fact extractor
    ↓
canonical fact store + raw chunk store + metadata store
    ↓
LlamaIndex Cloud embedding pipeline
    ↓
BAAI/bge-m3 multilingual embedding
    ↓
Qdrant Cloud vector collection
    ↓
LangGraph query-time workflow
    ↓
query planner → retriever → FPT bge-reranker-v2-m3 → evidence pack builder
    ↓
GPT 5.4 mini extraction/planning
    ↓
Altair offline chart generation
    ↓
GPT 5.5 report writer
    ↓
report validator + citation validator
    ↓
Markdown / HTML / PDF financial insight report
    ↓
evaluation bằng question_eval.json + RAGAS-style metrics
```

Pipeline chia thành 2 tầng:

1. **Data-time pipeline**: chạy batch khi có OCR `.txt` mới. Dùng Prefect để load file, normalize OCR, parse bảng, sinh facts, chunking, đẩy dữ liệu vào LlamaIndex Cloud và Qdrant Cloud.
2. **Query-time pipeline**: chạy khi user hỏi đáp hoặc yêu cầu sinh report. Dùng LangGraph để điều phối planner, retriever, reranker, LLM extraction, charting và report writer.

---

## 2. Tech stack bắt buộc

| Layer | Công nghệ / thư viện | Mục đích |
|---|---|---|
| Language | Python 3.10+ hoặc 3.11 | Runtime chính |
| Orchestration data pipeline | `prefect` | Ingestion, retry, logging, flow scheduling |
| Query-time orchestration | `langgraph`, `langchain-core` | Điều phối agent/tool-calling |
| LlamaIndex Cloud | `llama-cloud`, `llama-index`, `llama-index-indices-managed-llama-cloud` | Embedding pipeline + managed ingestion |
| Vector DB | Qdrant Cloud, `qdrant-client`, `llama-index-vector-stores-qdrant` | Lưu và truy xuất vector chunks |
| Embedding multilingual | `BAAI/bge-m3` qua LlamaIndex Cloud HuggingFace API embedding | Embedding tiếng Việt + tiếng Anh |
| Reranker multilingual | `bge-reranker-v2-m3` qua FPT Cloud API | Cross-encoder reranking |
| LLM extraction/planning | GPT 5.4 mini | Trích xuất claim, lập plan, tạo chart plan, kiểm tra evidence |
| LLM report writer | GPT 5.5 | Viết report cuối cùng |
| API client | `openai`, `httpx` | Gọi GPT và rerank endpoint kiểu OpenAI-compatible |
| Data processing | `pandas`, `numpy`, `python-dotenv`, `pydantic`, `orjson`, `duckdb` | Xử lý facts, schemas, env, JSON, local store |
| Text processing | `regex`, `beautifulsoup4`, `lxml`, `rapidfuzz`, `unidecode` | Normalize OCR, parse table HTML, fuzzy matching |
| Local storage | SQLite / DuckDB / Parquet | Lưu facts, chunks, eval outputs |
| Charting offline | `altair`, `vl-convert-python`, `pandas` | Sinh PNG/SVG/HTML chart offline |
| Report export | Markdown + optional `weasyprint` / `markdown-it-py` / `jinja2` | Xuất report cuối |
| Evaluation | `ragas`, `datasets`, `scikit-learn`, `rapidfuzz`, `pandas` | Đánh giá retrieval + generation |
| Testing | `pytest`, `pytest-dotenv` | Unit/integration tests |

---

## 3. Cấu trúc thư mục đề xuất

```text
rag_report_system/
│
├── .env.example
├── pyproject.toml
├── requirements.txt
├── README.md
├── IMPLEMENTATION_SPEC_RAG_REPORT.md
│
├── data/
│   ├── raw_ocr/
│   │   ├── A32_Baocaotaichinh_2017_Kiemtoan_extracted.txt
│   │   ├── A32_Baocaotaichinh_2018_Kiemtoan_extracted.txt
│   │   └── ...
│   ├── eval/
│   │   └── question_eval.json
│   ├── processed/
│   │   ├── chunks.jsonl
│   │   ├── financial_facts.parquet
│   │   ├── financial_facts.csv
│   │   ├── document_registry.json
│   │   └── section_registry.json
│   └── reports/
│       ├── charts/
│       ├── markdown/
│       ├── html/
│       └── eval_runs/
│
├── src/
│   └── rag_report/
│       ├── __init__.py
│       ├── config/
│       │   ├── settings.py
│       │   ├── logging.py
│       │   └── prompts.py
│       ├── schemas/
│       │   ├── documents.py
│       │   ├── chunks.py
│       │   ├── facts.py
│       │   ├── retrieval.py
│       │   ├── report.py
│       │   └── evaluation.py
│       ├── ingestion/
│       │   ├── load_ocr_files.py
│       │   ├── normalize_ocr.py
│       │   ├── page_parser.py
│       │   ├── section_detector.py
│       │   ├── table_extractor.py
│       │   ├── chunker.py
│       │   ├── fact_extractor.py
│       │   ├── fact_validator.py
│       │   ├── local_store.py
│       │   └── llama_cloud_ingest.py
│       ├── retrieval/
│       │   ├── query_planner.py
│       │   ├── qdrant_retriever.py
│       │   ├── keyword_retriever.py
│       │   ├── hybrid_fusion.py
│       │   ├── fpt_reranker.py
│       │   ├── evidence_pack.py
│       │   └── abstention.py
│       ├── agents/
│       │   ├── graph.py
│       │   ├── nodes.py
│       │   ├── tools.py
│       │   └── state.py
│       ├── llm/
│       │   ├── clients.py
│       │   ├── extraction_planner.py
│       │   ├── report_writer.py
│       │   └── validators.py
│       ├── charting/
│       │   ├── chart_plan_schema.py
│       │   ├── altair_renderer.py
│       │   ├── chart_validator.py
│       │   └── chart_registry.py
│       ├── report/
│       │   ├── templates/
│       │   │   ├── financial_report.md.j2
│       │   │   └── answer_card.md.j2
│       │   ├── composer.py
│       │   ├── citation_validator.py
│       │   └── exporter.py
│       ├── evaluation/
│       │   ├── load_eval_set.py
│       │   ├── run_eval.py
│       │   ├── retrieval_metrics.py
│       │   ├── generation_metrics.py
│       │   ├── ragas_adapter.py
│       │   └── eval_report.py
│       └── cli.py
│
├── flows/
│   ├── prefect_ingestion_flow.py
│   └── prefect_eval_flow.py
│
├── tests/
│   ├── test_ocr_normalize.py
│   ├── test_table_extractor.py
│   ├── test_fact_extractor.py
│   ├── test_retrieval.py
│   ├── test_abstention.py
│   └── test_eval_loader.py
│
└── notebooks/
    └── debug_retrieval.ipynb
```

---

## 4. `.env.example`

```text
# LlamaIndex / LlamaCloud
LLAMA_CLOUD_API_KEY=replace_me
LLAMA_CLOUD_PROJECT_ID=replace_me
LLAMA_CLOUD_PIPELINE_NAME=financial-rag-report-pipeline
LLAMA_CLOUD_EMBED_MODEL=BAAI/bge-m3
HF_TOKEN=replace_me

# Qdrant Cloud
QDRANT_URL=https://replace-me.qdrant.io
QDRANT_API_KEY=replace_me
QDRANT_COLLECTION=financial_ocr_chunks

# FPT Cloud reranker
FPT_RERANK_BASE_URL=https://mkp-api.fptcloud.com
FPT_RERANK_API_KEY=replace_me
FPT_RERANK_MODEL=bge-reranker-v2-m3

# LLM
OPENAI_API_KEY=replace_me
PLANNER_MODEL=gpt-5.4-mini
REPORT_MODEL=gpt-5.5

# Local paths
RAW_OCR_DIR=data/raw_ocr
PROCESSED_DIR=data/processed
EVAL_FILE=data/eval/question_eval.json
REPORT_OUTPUT_DIR=data/reports
LOCAL_DB_PATH=data/processed/rag_report.duckdb

# Retrieval
DEFAULT_VECTOR_TOP_K=30
DEFAULT_KEYWORD_TOP_K=30
DEFAULT_RERANK_TOP_N=10
DEFAULT_REPORT_TOP_N=15
MIN_EVIDENCE_SCORE=0.35
ABSTAIN_MIN_CONTEXTS=1
ABSTAIN_MIN_RERANK_SCORE=0.20
```

---

## 5. Data contracts bằng Pydantic

### 5.1 `DocumentRecord`

```text
DocumentRecord:
  document_id: str
  company_id: str
  company_name: str
  fiscal_year: int
  report_type: str
  source_filename: str
  source_path: str
  checksum_sha256: str
  language: str
  created_at: datetime
```

### 5.2 `PageRecord`

```text
PageRecord:
  page_id: str
  document_id: str
  page_number: int
  raw_text: str
  normalized_text: str
  detected_headers: list[str]
  detected_statement_type: str | None
  ocr_noise_score: float
```

### 5.3 `SectionChunk`

```text
SectionChunk:
  chunk_id: str
  document_id: str
  company_id: str
  fiscal_year: int
  page_start: int
  page_end: int
  section_title: str
  statement_type: str
  chunk_type: str
  text: str
  normalized_text: str
  tokens_estimate: int
  source_filename: str
  table_id: str | None
  row_index: int | None
  line_item_code: str | None
  line_item_name: str | None
  unit: str
  metadata: dict
```

`statement_type` dùng một trong các giá trị:

```text
balance_sheet
income_statement
cash_flow
notes
equity_change
audit_report
management_report
unknown
```

`chunk_type` dùng một trong các giá trị:

```text
narrative
table
table_row
mixed
```

### 5.4 `FinancialFact`

```text
FinancialFact:
  fact_id: str
  company_id: str
  company_name: str
  fiscal_year: int
  statement_type: str
  line_item_code: str | None
  line_item_name_raw: str
  line_item_name_canonical: str
  value: Decimal | None
  value_raw: str
  unit: str
  period_type: str
  column_label_raw: str
  source_chunk_id: str
  source_page: int
  confidence: float
  extraction_method: str
```

`period_type` dùng các giá trị:

```text
ending_balance
current_year
previous_year
movement
note_balance
unknown
```

### 5.5 `EvidencePack`

```text
EvidencePack:
  user_request: str
  query_plan: dict
  retrieved_chunks: list[RetrievedChunk]
  reranked_chunks: list[RerankedChunk]
  selected_facts: list[FinancialFact]
  missing_data_warnings: list[str]
  abstain_decision: dict
```

### 5.6 `ReportPlan`

```text
ReportPlan:
  report_title: str
  report_scope: dict
  key_claims: list[Claim]
  used_facts: list[str]
  used_chunks: list[str]
  unsupported_claims: list[str]
  chart_plans: list[ChartPlan]
  risk_flags: list[RiskFlag]
  sections: list[ReportSectionPlan]
```

### 5.7 `ChartPlan`

```text
ChartPlan:
  chart_id: str
  title: str
  chart_type: str
  metric: str
  x_field: str
  y_field: str
  filters: dict
  source_fact_ids: list[str]
  insight_message: str
```

### 5.8 `EvalSample`

File `question_eval.json` hiện có 30 mẫu.

```text
EvalSample:
  id: str
  question_type: str
  user_input: str
  reference: str
  reference_contexts: list[str]
  answerable: bool
  expected_behavior: str
```

Phân bố hiện tại:

| question_type | Số lượng |
|---|---:|
| `abstention` | 3 |
| `issue_extraction` | 6 |
| `multi_hop` | 5 |
| `multi_year_trend` | 7 |
| `single_fact` | 9 |

Tổng số mẫu cần trả lời: **27**.  
Tổng số mẫu phải abstain: **3**.

---

## 6. Ingestion pipeline bằng Prefect

Tên flow: `financial_ocr_ingestion_flow`

Input:

```text
raw_ocr_dir: data/raw_ocr
company_id: A32
force_reindex: false
```

Output:

```text
data/processed/document_registry.json
data/processed/section_registry.json
data/processed/chunks.jsonl
data/processed/financial_facts.parquet
data/processed/financial_facts.csv
Qdrant collection đã được upsert thông qua LlamaIndex Cloud pipeline
```

Thứ tự task:

```text
load_ocr_files
  → register_documents
  → normalize_ocr_text
  → split_pages
  → detect_report_metadata
  → detect_sections
  → extract_tables
  → extract_financial_facts
  → validate_financial_facts
  → build_chunks
  → persist_local_artifacts
  → upsert_llama_cloud_pipeline
  → ingest_documents_to_llama_cloud
  → verify_qdrant_sync
  → write_ingestion_summary
```

---

## 7. Chi tiết từng task ingestion

### 7.1 `load_ocr_files`

Nhiệm vụ:

- Scan tất cả file `.txt` trong `data/raw_ocr`.
- Chỉ nhận file OCR tài chính đã extract text.
- Đọc UTF-8, fallback `utf-8-sig` hoặc `latin-1` nếu lỗi encoding.
- Tính `checksum_sha256` để tránh ingest trùng.
- Không xóa file gốc.

Acceptance criteria:

- Với mỗi file, tạo `DocumentRecord`.
- Nếu file rỗng hoặc dưới ngưỡng ký tự tối thiểu, raise warning.
- Nếu checksum đã tồn tại và `force_reindex=false`, bỏ qua file đó.

### 7.2 `normalize_ocr_text`

Nhiệm vụ:

- Chuẩn hóa Unicode về NFC.
- Chuẩn hóa khoảng trắng, tab, dấu xuống dòng bất thường.
- Xóa ký tự rác do OCR như chuỗi lặp quá dài, watermark rời rạc, header/footer trùng quá nhiều.
- Chuẩn hóa biến thể dấu câu và số:
  - `1.234.567.890` giữ nguyên là số VND.
  - `(1.234.567)` chuyển thành số âm ở bước parse numeric.
  - `-` trong bảng tài chính được hiểu là null hoặc 0 tùy line item.
- Chuẩn hóa các lỗi OCR phổ biến:
  - `BẢNG CÂN ĐÓI` → `BẢNG CÂN ĐỐI`
  - `LƯU CHUYÊN TIÊN TÊ` → `LƯU CHUYỂN TIỀN TỆ`
  - `NỘ PHẢI TRẢ` → `NỢ PHẢI TRẢ`
  - `VỐN CHỦ SỐ HỮU` → `VỐN CHỦ SỞ HỮU`
  - `Chi tiên`, `Chỉ tiêu(1)`, `Chỉ tiêu` map về cùng nhãn.
- Giữ lại `<table>...</table>` nếu OCR đã có table HTML.

Acceptance criteria:

- Không làm mất giá trị số.
- Không normalize quá mạnh khiến mất tên chỉ tiêu.
- Lưu song song `raw_text` và `normalized_text`.

### 7.3 `split_pages`

Nhiệm vụ:

- Tách trang theo marker dạng `===== PAGE n =====`.
- Nếu không có marker, fallback bằng heuristic theo header lặp lại.
- Gắn `page_number`, `document_id`.
- Tính `ocr_noise_score` dựa trên:
  - tỷ lệ ký tự lạ,
  - số token một chữ cái liên tiếp,
  - số numeric token bất thường,
  - số đoạn `[Non-Text]`.

Acceptance criteria:

- Tất cả page có `page_id`.
- Không merge nhiều báo cáo vào một page.
- Page chứa bảng tài chính phải còn nguyên table text.

### 7.4 `detect_report_metadata`

Nhiệm vụ:

- Detect `company_id`, `company_name`, `fiscal_year`, `report_type`.
- `fiscal_year` lấy từ dòng như:
  - `Cho năm tài chính kết thúc ngày 31/12/2019`
  - `Năm 2021`
- `company_id` lấy từ filename hoặc config.
- `company_name` lấy từ header, ví dụ `CÔNG TY CỔ PHẦN 32`.

Acceptance criteria:

- Mỗi document phải có đúng 1 `fiscal_year`.
- Nếu phát hiện nhiều năm, năm chính là năm trong title báo cáo, không phải cột so sánh năm trước.
- Với cột `Số đầu năm`, lưu thành `previous_year_value` hoặc fact `fiscal_year - 1` chỉ khi đã qua validation.

### 7.5 `detect_sections`

Phân loại page/chunk vào các section:

| Keyword | statement_type |
|---|---|
| `BẢNG CÂN ĐỐI KẾ TOÁN` | `balance_sheet` |
| `BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH` | `income_statement` |
| `LƯU CHUYỂN TIỀN TỆ` | `cash_flow` |
| `BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH` | `notes` |
| `BÁO CÁO KIỂM TOÁN ĐỘC LẬP` | `audit_report` |
| `BÁO CÁO CỦA BAN ĐIỀU HÀNH` | `management_report` |
| `BẢNG THAY ĐỔI VỐN CHỦ SỞ HỮU` | `equity_change` |

Acceptance criteria:

- Page bảng cân đối, KQKD, lưu chuyển tiền tệ phải detect đúng.
- Nếu section ambiguous, gắn `unknown` nhưng vẫn giữ chunk.

### 7.6 `extract_tables`

Nhiệm vụ:

- Ưu tiên parse block `<table>...</table>` bằng BeautifulSoup/lxml.
- Nếu không có table HTML, fallback regex theo dòng.
- Chuẩn hóa mỗi bảng thành dataframe-like structure:
  - `table_id`
  - `document_id`
  - `page_number`
  - `statement_type`
  - `headers`
  - `rows`
- Không cố sửa số liệu ở bước này, chỉ parse raw cells.

Yêu cầu đặc biệt:

- Bảng thường có cột `Chỉ tiêu`, `Mã số`, `Thuyết minh`, `Số cuối năm`, `Số đầu năm`, `Năm 2021`, `Năm 2020`.
- Cho phép table có header bị lệch, ví dụ `Mã số Thuyết minh` bị gộp.
- Nhận diện số âm trong ngoặc: `(12.592.587.802)`.
- Bỏ ký tự OCR lẫn trong cell số, ví dụ `100.100.000.000 H`.

Acceptance criteria:

- Parse được bảng cân đối kế toán.
- Parse được bảng kết quả hoạt động kinh doanh.
- Parse được lưu chuyển tiền tệ.
- Các cell numeric giữ raw string để trace.

### 7.7 `extract_financial_facts`

Biến table rows thành `FinancialFact`.

Các chỉ tiêu canonical tối thiểu phải support vì xuất hiện trong evaluation:

| Canonical name | Các biến thể tiếng Việt |
|---|---|
| `inventory` | Hàng tồn kho |
| `cash_and_equivalents` | Tiền và các khoản tương đương tiền, Tiền và tương đương tiền cuối kỳ |
| `revenue` | Doanh thu bán hàng và cung cấp dịch vụ, Doanh thu bán hàng |
| `owner_equity` | Vốn chủ sở hữu |
| `retained_earnings` | Lợi nhuận sau thuế chưa phân phối |
| `current_cit_expense` | Chi phí thuế TNDN hiện hành |
| `interest_expense` | Chi phí lãi vay |
| `basic_eps` | Lãi cơ bản trên cổ phiếu |
| `customer_receivables_unrelated` | Phải thu khách hàng từ đơn vị không liên quan |
| `customer_receivables_related` | Phải thu khách hàng từ đơn vị liên quan |
| `bad_debt_provision` | Dự phòng phải thu khó đòi |

Quy tắc parse numeric:

```text
"164.355.410.664"       → 164355410664
"(12.592.587.802)"      → -12592587802
"-"                     → 0 hoặc null tùy chỉ tiêu
"4.134" trong EPS       → 4134, không phải 4.134 VND nếu context là EPS
"2,425 tỷ đồng"         → 2425000000 nếu parse từ generated/normalized text
```

Quy tắc gán năm:

- Cột `Số cuối năm`, `Năm 2021`, `Năm 2025` → `fiscal_year` của document hoặc label cột.
- Cột `Số đầu năm`, `Năm trước`, `Năm 2020` trong report 2021 → có thể tạo fact cho năm trước nếu không trùng source tốt hơn.
- Không tạo dữ liệu cho năm 2022 nếu không có report/source tương ứng và không có fact được xác thực. Evaluation có 3 câu năm 2022 yêu cầu abstain.

Acceptance criteria:

- Extract được facts cho tất cả chỉ tiêu xuất hiện trong `question_eval.json`.
- Mỗi fact có `source_chunk_id`.
- Fact không có source không được dùng để trả lời.
- Nếu một chỉ tiêu có nhiều giá trị xung đột, giữ tất cả nhưng flag `confidence` và `conflict_group`.

### 7.8 `validate_financial_facts`

Validation bắt buộc:

1. **Balance validation**: `Tổng cộng tài sản` gần bằng `Tổng cộng nguồn vốn`.
2. **Hierarchy validation**: `Tài sản ngắn hạn` phải lớn hơn hoặc bằng các nhóm con lớn như `Tiền`, `Phải thu`, `Hàng tồn kho`.
3. **Year consistency**: Không gán nhầm `Số đầu năm` của 2021 thành `Số cuối năm` của 2021.
4. **Unit consistency**: Mặc định VND nếu report ghi `Đơn vị tính: VND`.
5. **Outlier detection**: Nếu một giá trị lớn hơn năm liền kề > 20 lần, flag để kiểm tra OCR.
6. **Eval coverage**: Với các query trong `question_eval.json`, hệ thống phải có fact hoặc chunk evidence cho các mẫu answerable.

Output:

```text
financial_facts.parquet
financial_facts.csv
fact_validation_report.json
```

### 7.9 `build_chunks`

Chunking strategy:

- Chunk theo section trước, sau đó theo token.
- Chunk size mục tiêu: 1024 tokens.
- Overlap: 128 tokens.
- Với table:
  - tạo `table` chunk cho toàn bảng nếu vừa;
  - tạo thêm `table_row` chunks cho từng dòng quan trọng;
  - mỗi `table_row` chunk phải chứa header + row text để retrieval hiểu context.
- Với facts:
  - mỗi fact quan trọng nên có text representation:
    - `Năm 2018 | Bảng cân đối kế toán | Hàng tồn kho | Số cuối năm | 164.355.410.664 VND`

Metadata bắt buộc:

```text
company_id
company_name
fiscal_year
document_id
source_filename
page_start
page_end
statement_type
section_title
chunk_type
line_item_code
line_item_name
canonical_line_item
unit
```

Acceptance criteria:

- Chunk text đủ tự chứa để reranker hiểu.
- Chunk table row không bị mất header cột.
- `chunk_id` deterministic để map evaluation và citations.

### 7.10 `persist_local_artifacts`

Lưu local song song với cloud để debug:

```text
chunks.jsonl
financial_facts.parquet
financial_facts.csv
document_registry.json
section_registry.json
table_registry.json
ingestion_summary.json
```

DuckDB tables:

```text
documents
pages
chunks
tables
financial_facts
ingestion_runs
```

---

## 8. LlamaIndex Cloud embedding pipeline

### 8.1 Mục tiêu

Dùng LlamaIndex Cloud để tạo embedding multilingual bằng `BAAI/bge-m3`, sau đó sync vector sang Qdrant Cloud thông qua data sink đã connect.

### 8.2 Cấu hình

```text
pipeline_name: financial-rag-report-pipeline
project_id: LLAMA_CLOUD_PROJECT_ID
embedding_config:
  type: HUGGINGFACE_API_EMBEDDING
  model_name: BAAI/bge-m3
  token: HF_TOKEN
transform_config:
  mode: auto
  chunk_size: 1024
  chunk_overlap: 128
```

### 8.3 Quy tắc triển khai

- Không ghi `LLAMA_CLOUD_API_KEY` hoặc `HF_TOKEN` trực tiếp trong notebook/source.
- Pipeline upsert chỉ chạy khi pipeline chưa tồn tại, config thay đổi, hoặc `force_reindex=true`.
- Khi data sink Qdrant đã connect trong LlamaIndex Cloud, ingestion task chỉ gửi documents/chunks vào pipeline và kiểm tra sync.
- Nếu tự tạo collection Qdrant thủ công, dense vector của `BAAI/bge-m3` thường dùng dimension 1024; ưu tiên để LlamaIndex Cloud/data sink tự quản collection nếu đã connect sẵn.

### 8.4 Kiểm tra sau ingestion

`verify_qdrant_sync` phải kiểm tra:

- Collection tồn tại.
- Số point trong Qdrant xấp xỉ số chunk đã ingest.
- Payload có đủ metadata: `company_id`, `fiscal_year`, `statement_type`, `chunk_id`.
- Có thể filter theo năm, ví dụ `fiscal_year=2019`.
- Có thể filter theo statement, ví dụ `statement_type=balance_sheet`.

---

## 9. Qdrant Cloud collection design

Tên collection:

```text
financial_ocr_chunks
```

Payload index:

```text
company_id: keyword
fiscal_year: integer
statement_type: keyword
chunk_type: keyword
canonical_line_item: keyword
document_id: keyword
source_filename: keyword
page_start: integer
page_end: integer
```

Retrieval filter examples:

```text
company_id == "A32"
fiscal_year in [2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]
statement_type in ["balance_sheet", "income_statement", "cash_flow", "notes", "equity_change"]
canonical_line_item in ["inventory", "revenue", "owner_equity"]
```

MVP retrieval:

- Dense vector search trên Qdrant.
- Metadata filter theo năm/chỉ tiêu nếu query planner detect được.
- Rerank bằng FPT `bge-reranker-v2-m3`.

Nâng cấp hybrid:

- Nếu Qdrant/LlamaIndex Cloud data sink hỗ trợ sparse vector: bật hybrid dense+sparse trong collection.
- Nếu chưa bật sparse vector: dùng local keyword retriever bằng SQLite FTS/BM25 trên `chunks.jsonl`, sau đó fusion với dense results trước rerank.

---

## 10. Query-time pipeline bằng LangGraph

### 10.1 State schema

```text
GraphState:
  user_request: str
  request_type: str
  company_id: str
  fiscal_years: list[int]
  target_metrics: list[str]
  query_plan: dict
  dense_results: list[RetrievedChunk]
  keyword_results: list[RetrievedChunk]
  fused_results: list[RetrievedChunk]
  reranked_results: list[RerankedChunk]
  selected_facts: list[FinancialFact]
  evidence_pack: EvidencePack
  report_plan: ReportPlan
  chart_paths: list[str]
  final_answer: str
  final_report_markdown: str
  validation_errors: list[str]
  abstain: bool
  abstain_reason: str | None
```

### 10.2 Nodes

```text
parse_user_request
  ↓
route_request_type
  ↓
plan_query_with_gpt54_mini
  ↓
retrieve_structured_facts
  ↓
retrieve_dense_qdrant
  ↓
retrieve_keyword_optional
  ↓
fuse_retrieval_results
  ↓
rerank_with_fpt_bge_v2_m3
  ↓
build_evidence_pack
  ↓
decide_abstention
  ↓
extract_claims_and_report_plan_with_gpt54_mini
  ↓
validate_claim_grounding
  ↓
generate_charts_altair
  ↓
write_report_with_gpt55
  ↓
validate_final_report
  ↓
export_report
```

### 10.3 Conditional edges

```text
if request_type == "qa":
    build answer card only
elif request_type == "report":
    build full financial insight report
elif abstain == true:
    return abstention answer, không gọi GPT 5.5 report writer
elif validation_errors contains unsupported numeric claim:
    retry evidence retrieval hoặc remove unsupported claim
```

---

## 11. Query planner — GPT 5.4 mini

### 11.1 Input

```text
user_request
available_years
canonical_metric_dictionary
company_id
```

### 11.2 Output JSON bắt buộc

```json
{
  "request_type": "qa",
  "company_id": "A32",
  "fiscal_years": [2018],
  "target_metrics": ["inventory"],
  "statement_types": ["balance_sheet"],
  "query_variants": [
    "Hàng tồn kho năm 2018",
    "Bảng cân đối kế toán hàng tồn kho số cuối năm 2018"
  ],
  "structured_fact_filters": {
    "canonical_line_item": ["inventory"],
    "fiscal_year": [2018]
  },
  "retrieval_filters": {
    "company_id": "A32",
    "fiscal_year": [2018],
    "statement_type": ["balance_sheet"]
  },
  "needs_chart": false,
  "expected_answer_type": "single_number",
  "abstention_sensitive": false
}
```

### 11.3 Quy tắc planner

- Câu hỏi chứa năm cụ thể → filter năm đó.
- Câu hỏi xu hướng → lấy tất cả năm trong khoảng.
- Câu hỏi issue/risk → không chỉ lấy facts, phải lấy thêm notes/narrative chunks.
- Câu hỏi năm 2022 trong dataset hiện tại phải được xử lý abstention nếu không có document/fact/chunk năm 2022.
- Planner không được tự suy đoán số liệu.

---

## 12. Structured fact retrieval

Dùng `financial_facts.parquet` hoặc DuckDB để truy vấn facts trước khi vector retrieval.

### 12.1 Vì sao cần fact retrieval

Các câu hỏi tài chính có số liệu cụ thể. Nếu chỉ dùng semantic retrieval, hệ thống dễ:

- lấy nhầm cột `Số đầu năm`;
- lấy nhầm năm;
- trả lời đúng ngữ nghĩa nhưng sai số;
- không phát hiện thiếu dữ liệu năm 2022.

Do đó query-time phải ưu tiên `financial_facts` cho numeric QA và chart.

### 12.2 Logic

```text
if query_plan.structured_fact_filters not empty:
    selected_facts = query facts by company_id + fiscal_year + canonical_line_item + statement_type
else:
    selected_facts = []
```

### 12.3 Output

- Danh sách `FinancialFact`.
- Nếu không có fact cho query numeric → set `missing_data_warnings`.
- Facts phải được join ngược sang `chunks` qua `source_chunk_id`.

---

## 13. Dense retrieval trên Qdrant

### 13.1 Input

```text
query_variants
retrieval_filters
top_k = DEFAULT_VECTOR_TOP_K
```

### 13.2 Output

```text
RetrievedChunk:
  chunk_id
  text
  score
  metadata
  source_filename
  fiscal_year
  page_start
  page_end
  statement_type
```

### 13.3 Retrieval strategy

- Với mỗi query variant, gọi Qdrant search.
- Gộp kết quả theo `chunk_id`.
- Score fusion bằng max score hoặc weighted average.
- Ưu tiên chunk có:
  - đúng năm;
  - đúng statement_type;
  - đúng canonical_line_item;
  - chunk_type là `table_row` nếu query là single fact.

### 13.4 Filter bắt buộc

Nếu query planner phát hiện năm/chỉ tiêu, filter phải được áp dụng trước khi search. Không để retrieval tự chọn toàn bộ collection nếu đã biết năm.

---

## 14. Keyword retrieval / Hybrid retrieval

MVP có thể dùng dense retrieval + reranker. Tuy nhiên với OCR tài chính, keyword retrieval quan trọng vì các dòng bảng có cụm cố định như `Hàng tồn kho`, `Vốn chủ sở hữu`, `Lãi cơ bản trên cổ phiếu`.

### 14.1 Local keyword retriever

Dùng SQLite FTS hoặc BM25 trên `chunks.jsonl`.

Index fields:

```text
chunk_id
normalized_text
line_item_name
canonical_line_item
statement_type
fiscal_year
```

### 14.2 Fusion

Gộp dense và keyword bằng Reciprocal Rank Fusion:

```text
fused_score = Σ 1 / (k + rank_i)
k = 60
```

### 14.3 Khi nào keyword bắt buộc

- Query có exact line item: `Hàng tồn kho`, `Doanh thu bán hàng`, `Vốn chủ sở hữu`.
- Query multi-hop trong thuyết minh.
- Query có thuật ngữ kế toán hiếm.
- Query hỏi năm 2022 để xác minh không có dữ liệu.

---

## 15. Reranker FPT Cloud — `bge-reranker-v2-m3`

### 15.1 Input

```text
query: str
documents: list[str]
top_n: int
```

`documents` nên được format giàu metadata:

```text
[chunk_id=A32_2018_p6_r_inventory]
Năm: 2018
Loại báo cáo: Bảng cân đối kế toán
Trang: 6
Nội dung:
Hàng tồn kho | Mã số 140 | Số cuối năm 164.355.410.664 | Số đầu năm 130.440.960.114
```

### 15.2 Output normalize

```text
RerankedChunk:
  chunk_id
  text
  rerank_score
  original_rank
  metadata
```

### 15.3 Quy tắc

- Chỉ rerank tối đa 50 documents/lần để tránh latency cao.
- Với QA single fact, `top_n=5`.
- Với trend/report, `top_n=10-15`.
- Nếu reranker lỗi, fallback về fused retrieval nhưng phải ghi warning.
- Không gọi GPT report writer nếu reranker không trả được evidence tối thiểu và câu hỏi cần số liệu.

---

## 16. Evidence pack builder

Evidence pack combine:

1. Top reranked chunks.
2. Structured facts liên quan.
3. Missing data warnings.
4. Metadata citation.

### 16.1 Evidence text format

```text
[EVIDENCE: chunk_id=A32_2018_balance_sheet_p6_inventory]
company_id: A32
fiscal_year: 2018
statement_type: balance_sheet
page: 6
source: A32_Baocaotaichinh_2018_Kiemtoan_extracted.txt
text:
Bảng cân đối kế toán năm 2018: Hàng tồn kho đạt 164.355.410.664 đồng.
```

### 16.2 Fact format

```text
[FACT: fact_id=A32_2018_inventory_ending_balance]
metric: inventory
fiscal_year: 2018
value: 164355410664
unit: VND
source_chunk_id: A32_2018_balance_sheet_p6_inventory
```

### 16.3 Guardrail

- GPT không được thấy quá nhiều chunk nhiễu.
- Evidence pack ưu tiên facts trước, chunks sau.
- Mọi numeric claim bắt buộc map được về `fact_id`.

---

## 17. Abstention logic

Hệ thống phải biết từ chối trả lời khi thiếu dữ liệu.

### 17.1 Điều kiện abstain

Abstain nếu thỏa một trong các điều kiện:

```text
No document for requested fiscal_year
No fact for requested metric + fiscal_year
No retrieved chunk above MIN_EVIDENCE_SCORE
Reranker top score below ABSTAIN_MIN_RERANK_SCORE
Evidence pack has zero source for required numeric claim
Question asks exact value but only trend/narrative evidence exists
```

### 17.2 Output abstain

```text
Không có đủ dữ liệu trong bộ báo cáo đã cung cấp để trả lời câu hỏi này.
```

Có thể bổ sung lý do ngắn:

```text
Hệ thống không tìm thấy báo cáo/fact/chunk đáng tin cậy cho năm 2022.
```

### 17.3 Evaluation-sensitive abstention

Trong `question_eval.json`, 3 câu `A32_Q028`, `A32_Q029`, `A32_Q030` yêu cầu abstain cho năm 2022. Không được nội suy năm 2022 từ 2021/2023.

---

## 18. GPT 5.4 mini — extraction và planning

### 18.1 Nhiệm vụ

GPT 5.4 mini không viết report cuối. Nó tạo output cấu trúc:

- answer plan;
- claims;
- used facts;
- chart plan;
- unsupported claims;
- missing information;
- risk flags.

### 18.2 Output JSON cho QA

```json
{
  "answer_type": "single_fact",
  "direct_answer": "Hàng tồn kho năm 2018 là khoảng 164,4 tỷ đồng.",
  "numeric_facts": [
    {
      "metric": "inventory",
      "fiscal_year": 2018,
      "value": 164355410664,
      "display_value": "khoảng 164,4 tỷ đồng",
      "source_fact_id": "A32_2018_inventory_ending_balance"
    }
  ],
  "claims": [
    {
      "claim": "Hàng tồn kho năm 2018 là khoảng 164,4 tỷ đồng.",
      "source_fact_ids": ["A32_2018_inventory_ending_balance"],
      "source_chunk_ids": ["A32_2018_balance_sheet_p6_inventory"]
    }
  ],
  "unsupported_claims": [],
  "abstain": false,
  "abstain_reason": null
}
```

### 18.3 Output JSON cho report

```json
{
  "report_title": "Báo cáo phân tích tài chính Công ty Cổ phần 32 giai đoạn 2017-2025",
  "sections": [
    {
      "section_id": "revenue_trend",
      "title": "Xu hướng doanh thu",
      "claims": [],
      "required_charts": ["chart_revenue_trend"]
    }
  ],
  "chart_plans": [],
  "risk_flags": [
    {
      "risk_name": "working_capital_locked_in_inventory",
      "evidence_fact_ids": [],
      "severity": "medium",
      "explanation": "..."
    }
  ],
  "unsupported_claims": []
}
```

### 18.4 Guardrails

Prompt phải yêu cầu:

- Không tạo số liệu mới.
- Không nội suy năm thiếu.
- Không dùng kiến thức ngoài evidence.
- Mỗi claim số phải có `source_fact_id`.
- Nếu không đủ source, chuyển sang `unsupported_claims`.

---

## 19. Chart generation bằng Altair offline

### 19.1 Input

`ChartPlan` + `FinancialFact`.

### 19.2 Chart types cần support trong MVP

| chart_type | Khi dùng |
|---|---|
| `line` | Xu hướng doanh thu, hàng tồn kho, tiền mặt qua nhiều năm |
| `bar` | So sánh một metric theo năm |
| `grouped_bar` | So sánh nhiều metric cùng kỳ |
| `area` | Tùy chọn cho cơ cấu/tích lũy |

### 19.3 Chart validator

Trước khi render:

- `source_fact_ids` phải tồn tại.
- Mỗi chart có ít nhất 2 điểm dữ liệu nếu là trend.
- Không vẽ năm thiếu.
- Không mix VND và EPS trên cùng trục.
- X-axis `fiscal_year` phải sort tăng dần.
- Title phải chứa metric và giai đoạn.
- Nếu có missing year, chart subtitle phải ghi rõ.

### 19.4 Output

```text
data/reports/charts/chart_inventory_2017_2025.png
data/reports/charts/chart_inventory_2017_2025.svg
data/reports/charts/chart_inventory_2017_2025.vl.json
```

Dùng `vl-convert-python` để export PNG/SVG offline. Không phụ thuộc browser.

---

## 20. GPT 5.5 — report writer

### 20.1 Input

```text
user_request
report_plan từ GPT 5.4 mini
evidence_pack
chart_paths
report_template
```

### 20.2 Output

Markdown report.

Cấu trúc report đề xuất:

```text
# Báo cáo phân tích tài chính [Company] giai đoạn [Years]

## 1. Phạm vi dữ liệu
- Danh sách báo cáo đã dùng
- Các năm có dữ liệu
- Các năm thiếu dữ liệu nếu có

## 2. Xu hướng doanh thu
- Insight
- Số liệu chính
- Chart

## 3. Xu hướng hàng tồn kho và vốn lưu động
- Insight
- Rủi ro vốn bị khóa
- Chart

## 4. Tiền và tương đương tiền
- Insight
- Biến động bất thường
- Chart

## 5. Vốn chủ sở hữu và lợi nhuận giữ lại
- Insight
- Chart

## 6. Các dấu hiệu/rủi ro cần chú ý
- Dự phòng phải thu khó đòi
- Lãi vay
- Biến động doanh thu/lợi nhuận
- Các khoản phải thu liên quan/không liên quan

## 7. Kết luận
- Tổng hợp điểm mạnh/yếu
- Các vấn đề cần kiểm tra thêm
```

### 20.3 Citation format trong report

Mỗi số liệu cần citation nội bộ:

```text
Hàng tồn kho năm 2018 đạt khoảng 164,4 tỷ đồng [fact:A32_2018_inventory_ending_balance; chunk:A32_2018_p6_r_inventory].
```

Nếu export cho người đọc cuối, convert citation thành footnote:

```text
[1] A32_Baocaotaichinh_2018_Kiemtoan_extracted.txt, Bảng cân đối kế toán, trang 6.
```

### 20.4 Guardrails

GPT 5.5 chỉ được viết lại nội dung từ `ReportPlan` và `EvidencePack`. Không được thêm claim mới ngoài plan. Nếu thêm insight mới, validator phải chặn.

---

## 21. Report validator

### 21.1 Numeric claim validator

- Extract số trong report.
- Match với `FinancialFact.value`.
- Cho phép sai số do làm tròn:
  - `164.355.410.664` → `164,4 tỷ đồng`: hợp lệ.
  - tolerance mặc định 0.2%.
- Nếu số không match fact nào → fail.

### 21.2 Citation validator

- Mỗi đoạn có số liệu phải có citation.
- Citation phải trỏ tới `fact_id` hoặc `chunk_id` tồn tại.
- Citation không được trỏ tới chunk không nằm trong evidence pack.

### 21.3 Abstention validator

- Nếu request thiếu dữ liệu, final answer phải chứa abstain message.
- Không được vừa abstain vừa đưa số ước lượng.

### 21.4 Chart validator

- Chart trong report phải có file tồn tại.
- Chart source facts phải khớp với text insight.
- Nếu chart thiếu năm, report phải nói rõ.

---

## 22. Evaluation pipeline với `question_eval.json`

### 22.1 Dataset hiện tại

File `question_eval.json` có 30 mẫu theo format:

```text
id
question_type
user_input
reference
reference_contexts
answerable
expected_behavior
```

Phân bổ:

- `single_fact`: hỏi một số liệu cụ thể.
- `multi_year_trend`: hỏi xu hướng qua nhiều năm.
- `issue_extraction`: hỏi dấu hiệu/rủi ro tài chính.
- `multi_hop`: cần nối bảng chính + thuyết minh hoặc nhiều evidence.
- `abstention`: bắt buộc từ chối vì thiếu dữ liệu.

### 22.2 Eval flow

Tên flow: `financial_rag_eval_flow`

```text
load_eval_set
  → run_each_question_through_langgraph
  → collect_answer_and_contexts
  → compute_retrieval_metrics
  → compute_generation_metrics
  → compute_abstention_metrics
  → compute_ragas_metrics_optional
  → write_eval_report
```

### 22.3 Output mỗi sample

```text
EvalRunRecord:
  id: str
  question_type: str
  user_input: str
  expected_behavior: str
  answerable: bool
  reference: str
  prediction: str
  retrieved_contexts: list[str]
  retrieved_chunk_ids: list[str]
  reranked_chunk_ids: list[str]
  used_fact_ids: list[str]
  abstain_predicted: bool
  latency_ms: int
  token_usage: dict
  metrics: dict
```

### 22.4 Retrieval metrics

#### Hit@K

```text
Hit@K = 1 nếu ít nhất một relevant_chunk_id xuất hiện trong top K
Hit@K = 0 nếu không có chunk đúng trong top K
```

Với `question_eval.json`, `reference_contexts` là evidence text. Cần map `reference_contexts` sang `relevant_chunk_ids` bằng:

1. exact string match trên `chunks.normalized_text`;
2. nếu không match, dùng fuzzy match `rapidfuzz`;
3. nếu vẫn không match, dùng embedding search reference_context để lấy chunk gần nhất;
4. lưu mapping vào `eval_ground_truth_chunks.json`.

#### MRR

```text
MRR = 1 / rank của chunk đúng đầu tiên
```

#### Context Recall

```text
Context Recall = số reference_contexts được tìm thấy trong retrieved_contexts / tổng số reference_contexts
```

Với sample `answerable=false`, retrieval không nên tìm evidence giả. Metric chính là abstention accuracy.

### 22.5 Generation metrics

#### Exact/semantic answer correctness

- Với câu số liệu, kiểm tra numeric value trong prediction có gần với reference không.
- Với câu trend, kiểm tra đúng chiều biến động: tăng, giảm, tăng rồi giảm, giảm rồi tăng.
- Với issue extraction, dùng semantic similarity hoặc LLM judge nhưng phải dựa trên reference.
- Với multi-hop, yêu cầu đủ các thành phần trong reference.

#### Numeric accuracy

Parse số từ prediction và reference:

```text
164,4 tỷ đồng ≈ 164400000000
164.355.410.664 đồng = 164355410664
```

Hợp lệ nếu:

```text
relative_error <= 0.5%
```

#### Abstention accuracy

```text
abstention_accuracy = số câu expected_behavior=abstain được hệ thống abstain đúng / tổng câu abstain
```

False positive abstain:

```text
answerable=true nhưng hệ thống abstain
```

False negative abstain:

```text
answerable=false nhưng hệ thống bịa số liệu
```

### 22.6 RAGAS adapter

Chuyển mỗi eval sample sang RAGAS-style row:

```json
{
  "user_input": "Hàng tồn kho năm 2018 là bao nhiêu?",
  "response": "Hàng tồn kho năm 2018 là khoảng 164,4 tỷ đồng.",
  "retrieved_contexts": ["..."],
  "reference": "Hàng tồn kho năm 2018 là khoảng 164,4 tỷ đồng.",
  "reference_contexts": ["Bảng cân đối kế toán năm 2018: Hàng tồn kho đạt 164.355.410.664 đồng."]
}
```

Metrics đề xuất:

```text
context_recall
faithfulness
answer_correctness
answer_relevancy
```

Lưu ý:

- RAGAS không thay thế numeric validator.
- Với tài chính, numeric accuracy phải là metric riêng bắt buộc.
- Với abstention, cần custom metric ngoài RAGAS.

### 22.7 Eval report output

```text
data/reports/eval_runs/eval_run_YYYYMMDD_HHMMSS/
  predictions.jsonl
  metrics_summary.json
  metrics_by_question_type.csv
  failed_cases.md
  retrieval_debug.csv
```

`failed_cases.md` phải liệt kê:

```text
id
question_type
user_input
reference
prediction
expected_behavior
retrieved_chunk_ids
used_fact_ids
failure_reason
suggested_fix
```

Failure reason categories:

```text
retrieval_miss
reranker_miss
wrong_year
wrong_column
numeric_parse_error
unsupported_generation
false_abstain
missed_abstain
chart_data_error
```

---

## 23. CLI cần có

```text
rag-report ingest --raw-dir data/raw_ocr --company-id A32
rag-report verify-index --collection financial_ocr_chunks
rag-report ask "Hàng tồn kho năm 2018 là bao nhiêu?"
rag-report report --company-id A32 --years 2017:2025 --output data/reports/markdown/a32_report.md
rag-report eval --eval-file data/eval/question_eval.json
rag-report debug-retrieval --query "Doanh thu bán hàng năm 2021 là bao nhiêu?"
```

Mỗi CLI command log:

```text
run_id
timestamp
input params
number of documents/chunks/facts
latency
errors/warnings
output path
```

---

## 24. Required prompts

### 24.1 Planner prompt — GPT 5.4 mini

```text
You are a financial RAG query planner.
Given a Vietnamese user request and available metadata, produce a JSON query plan.
Do not answer the question.
Do not invent facts.
Extract fiscal years, target financial metrics, statement types, and retrieval filters.
If the question asks for a year not available in metadata, mark abstention_sensitive=true.
```

### 24.2 Extraction prompt — GPT 5.4 mini

```text
You are a financial evidence extraction model.
Use only the provided EvidencePack.
Return JSON with claims, numeric_facts, used_fact_ids, used_chunk_ids, unsupported_claims, chart_plans.
Every numeric claim must cite at least one fact_id.
If evidence is insufficient, set abstain=true.
Do not infer missing years.
```

### 24.3 Report writer prompt — GPT 5.5

```text
You are a financial analyst writing a grounded Vietnamese report.
Use only the provided ReportPlan and EvidencePack.
Do not introduce new numeric claims.
Every important number must keep its citation token.
Write clearly, professionally, and cautiously.
If data is missing, state the limitation explicitly.
```

### 24.4 Validator prompt — optional

```text
Check whether each claim is supported by the provided evidence.
Return unsupported claims only.
Do not rewrite the report.
```

---

## 25. Unit tests bắt buộc

### 25.1 OCR normalizer

- Test normalize lỗi heading.
- Test không làm hỏng số VND.
- Test giữ số âm trong ngoặc.

### 25.2 Table extractor

- Test parse `<table>`.
- Test parse bảng cân đối.
- Test parse KQKD.
- Test parse lưu chuyển tiền tệ.
- Test header bị merge.

### 25.3 Fact extractor

Các facts tối thiểu phải pass:

```text
inventory 2018 = 164.355.410.664
inventory 2020 = 190.450.695.083
cash_and_equivalents 2021 = 97.299.243.376
revenue 2020 = 728.582.496.415
owner_equity 2019 = 223.615.948.462
```

Nếu source hiện tại chưa có đủ file năm tương ứng, test phải skip có lý do, không fail giả.

### 25.4 Abstention

- Query năm 2022 cho inventory/revenue/owner_equity phải abstain nếu không có facts năm 2022.
- Không được lấy `Số đầu năm` hoặc `Năm trước` để bịa câu trả lời cho năm 2022.

### 25.5 Retrieval

- Query exact line item phải retrieve chunk chứa line item.
- Query trend phải retrieve nhiều năm.
- Query notes phải retrieve notes/chú thích.

### 25.6 Report validator

- Numeric claim thiếu citation phải fail.
- Numeric claim sai quá tolerance phải fail.
- Chart thiếu source facts phải fail.

---

## 26. Milestone triển khai trong 1 ngày

### Phase 1 — Skeleton + config

Deliverables:

```text
project structure
.env.example
settings.py
schemas
CLI skeleton
```

### Phase 2 — Ingestion local

Deliverables:

```text
load OCR txt
normalize OCR
split pages
detect sections
extract tables
extract facts
save chunks/facts
```

### Phase 3 — Cloud indexing

Deliverables:

```text
LlamaCloud pipeline upsert
ingest chunks
verify Qdrant sync
basic Qdrant retrieval
```

### Phase 4 — Query-time RAG

Deliverables:

```text
query planner
structured fact lookup
dense retrieval
keyword retrieval optional
reranker FPT
evidence pack
abstention
QA answer
```

### Phase 5 — Report generation

Deliverables:

```text
report plan
Altair chart rendering
GPT 5.5 writer
citation/numeric validator
Markdown export
```

### Phase 6 — Evaluation

Deliverables:

```text
load question_eval.json
run all questions
compute metrics
failed_cases.md
metrics_summary.json
```

---

## 27. Definition of Done

Hệ thống được xem là hoàn thành MVP nếu đạt các điều kiện:

1. Ingest được tất cả OCR `.txt` trong `data/raw_ocr`.
2. Sinh được `chunks.jsonl` và `financial_facts.parquet`.
3. Qdrant Cloud có collection chứa chunks và metadata filter được theo năm.
4. Reranker FPT hoạt động và trả top evidence.
5. Câu hỏi single fact trong `question_eval.json` trả đúng số liệu sau làm tròn.
6. Câu hỏi trend trả đúng chiều biến động và số mốc chính.
7. Câu hỏi issue extraction trả lời có evidence, không suy diễn quá mức.
8. Câu hỏi năm 2022 abstain đúng.
9. Report Markdown sinh ra có biểu đồ Altair offline.
10. Mọi numeric claim trong report có citation hoặc bị validator chặn.
11. Evaluation xuất được `metrics_summary.json`, `failed_cases.md`, `predictions.jsonl`.

---

## 28. Gợi ý debug khi điểm evaluation thấp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Sai năm | Planner không filter năm hoặc fact extractor gán nhầm `Số đầu năm` | Siết year parser, thêm metadata filter |
| Sai số | Numeric parser hiểu sai dấu `.` hoặc số âm | Unit test numeric parser |
| Retrieve sai bảng | Chunk table thiếu header | Tạo table-row chunk có header |
| Reranker chọn narrative thay vì row bảng | Document text đưa vào reranker thiếu metadata | Format rerank documents với năm + statement_type + row |
| Không abstain năm 2022 | Hệ thống nội suy hoặc lấy cột năm trước | Thêm abstention guard theo available_years |
| Report bịa insight | GPT 5.5 được phép thêm claim mới | Chỉ cho GPT 5.5 viết từ ReportPlan, thêm validator |
| Chart sai | Chart dùng retrieved text thay vì fact table | Chart chỉ được lấy từ `FinancialFact` |
| RAGAS cao nhưng số sai | Metric semantic không bắt lỗi số | Bắt buộc numeric accuracy riêng |

---

## 29. Ghi chú bảo mật

- Không commit `.env`.
- Không log API key.
- Không ghi token vào notebook.
- Nếu token từng bị paste vào chat/notebook, rotate token trước khi deploy.
- Chỉ log 4 ký tự cuối của key nếu cần debug.
- Với report tài chính nội bộ, cân nhắc mask dữ liệu nhạy cảm nếu gửi lên cloud LLM.

---

## 30. Tài liệu đầu vào bắt buộc cho AI Coding

AI Coding cần có tối thiểu:

```text
data/raw_ocr/*.txt
data/eval/question_eval.json
.env.local
IMPLEMENTATION_SPEC_RAG_REPORT.md
```

Sau khi build xong, chạy thứ tự:

```text
rag-report ingest --raw-dir data/raw_ocr --company-id A32
rag-report verify-index --collection financial_ocr_chunks
rag-report eval --eval-file data/eval/question_eval.json
rag-report report --company-id A32 --years 2017:2025 --output data/reports/markdown/a32_financial_report.md
```
