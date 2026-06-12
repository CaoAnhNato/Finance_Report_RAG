# VNext Report Code Mapping Guide

This guide provides a direct mapping between the generated vNext HTML report components/sections and the source code implementation. Use this guide to immediately identify where to apply changes for specific tasks.

---

## 1. Report Sections vs. Code Map

| Report Section / Visual Component | Key Source File | Key Class / Function / Constant | Description |
| :--- | :--- | :--- | :--- |
| **Cover Page** (Trang bìa) | `src/rag_report/report_vnext/exporter.py` | `VNextHTMLExporter.compile_report` | HTML templates, layout, CSS variables for cover page, title constraints. |
| **Step 1 - Data Source Reliability** (Nguồn số liệu có đáng tin không?) | `src/rag_report/report_vnext/evidence.py` | `build_intro_evidence_pack`<br>`_extract_audit_snapshot` | Rules & logic for collecting audit firm names, opinion matching, base facts. |
| **Audit opinion & auditor name matching** (Regex logic) | `src/rag_report/report_vnext/evidence.py` | `AUDIT_OPINION_PATTERNS`<br>`_detect_audit_opinion`<br>`_clean_auditor_name` | Regex patterns and clean-up lookup dict for AASCS, An Việt, etc. |
| **Step 2 - Key Financial Metrics & Charts** (Chỉ số cốt lõi) | `src/rag_report/report_vnext/metrics.py` | `calculate_metrics`<br>`MetricPack` | Metric formulas, display labels, value calculation logic (LNST, CFO, etc.). |
| **Charts Specs & Legends** (Biểu đồ Altair) | `src/rag_report/report_vnext/charts.py` | `build_charts`<br>`_chart_earnings_cash`<br>`_chart_receivables_revenue` | Chart specifications, color palettes, legend configurations, axis scales. |
| **Metric LLM Backfill** (Trích xuất bổ sung khi thiếu số liệu) | `src/rag_report/report_vnext/backfill.py` | `IntroExtractionBackfill` | LLM prompts and pipelines to extract missing fields from OCR text. |
| **Step 3 - Detailed Narrative** (Nhận định chi tiết sức khỏe tài chính) | `src/rag_report/report_vnext/writer.py` | `IntroNarrativeWriter`<br>Prompts and templates | LLM prompts, structural instructions, writing guidelines for narrative paragraphs. |
| **Narrative Editing & Wording Cleanup** (Chuẩn hóa văn phong & tiêu đề) | `src/rag_report/report_vnext/editor.py` | `IntroNarrativeEditor` | LLM narrative editing layer and deterministic regex-based corrections. |
| **Hover Tooltips & Provenance Cards** (Chú giải nguồn số liệu) | `src/rag_report/report_vnext/exporter.py` | `_render_provenance_card` | HTML, CSS templates for metric tooltips, popup layout, active links. |
| **Number & Label Formatting** (Định dạng tiếng Việt) | `src/rag_report/report_vnext/formatting.py` | `fold_text`<br>`public_source_label` | Formatting of numbers (millions/billions), Vietnamese source citations. |
| **Auto-Audit & Feedback Loop** (Tự đánh giá & sửa sai) | `src/rag_report/report_vnext/audit.py`<br>`src/rag_report/report_vnext/feedback_log.py` | `audit_report_html`<br>`seed_feedback_log`<br>`rules_to_style_notes`<br>`narrative_wording_hygiene` | Grading criteria, style guidelines, narrative wording hygiene checks, feedback extraction loop. |

---

## 2. Execution Pipeline Orchestration

- **Pipeline Runner**: `src/rag_report/report_vnext/pipeline.py` (defines `IntroReportVNextPipeline` with sequential stages: `evidence extraction` -> `backfilling` -> `metric calculation` -> `chart planning` -> `narrative writing` -> `narrative editing` -> `bundle assembly`).
- **Prefect Flow Orchestration**: `flows/generate_report_vnext_flow.py` (orchestrates loop validation, runs the audit engine, saves feedback rules, and retries generation if quality thresholds are not met).
- **Smoke Tests**:
  - `tests/smoke_test_vnext.py`: General pipeline and exporter rendering verification.
  - `tests/test_report_vnext_metrics.py`: Unit tests checking metric formulas and output structures.
  - `tests/test_report_vnext_charts.py`: Tests for chart legends and axis configurations.
  - `tests/test_report_vnext_editor.py`: Unit tests for narrative cleanup editor and wording hygiene checks.

---

## 3. Legacy v2 Report Pipeline Map

If you need to edit, fix bugs, or check extraction in the v2 report (`data/reports/A32_Financial_Report_v2.html`), refer to the following mapping:

| Component / Task (v2) | Key Source File | Key Class / Function / Prompt | Description |
| :--- | :--- | :--- | :--- |
| **RAG Query Node Orchestration** | `src/rag_report/query/graph.py` | `FinancialRAGGraph` | LangGraph nodes coordinating parallel/sequential retrieval and prompt answering. |
| **Section Prompt Queries** | `tests/run_generate_v2.py` | `QUERIES` dictionary | Custom LLM prompts for Executive Summary, Business Performance, Capital Structure, etc. |
| **HTML Report Template** | `src/rag_report/exporter/exporter.py` | `HTMLExporter` | HTML templates, layouts, and style definitions for the v2 report. |
| **v2 Chart Rendering** | `src/rag_report/exporter/charting.py` | `FinancialCharter` | Matplotlib / image charts creation and integration. |

---

## 4. Target Report Identification Conventions

To guide the AI agent on which report pipeline to work on, use the following phrases or references:

- **To target vNext Report (`A32_Financial_Report_vNext.html`)**:
  - Refer directly to "vNext", "báo cáo mới", "báo cáo vNext", or "phiên bản vNext".
  - Mention specific vNext components: "Bước 1 / 2 / 3", "Evidence pack", "Metric pack", or "Bright theme HTML".
- **To target Legacy v2 Report (`A32_Financial_Report_v2.html`)**:
  - Refer directly to "v2", "báo cáo cũ", "báo cáo v2", or "phiên bản v2".
  - Mention specific v2 components: "LangGraph query", "RAG Node", "run_generate_v2.py", or "matplotlib charts".
