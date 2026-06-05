import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Hugging Face
HF_TOKEN = os.getenv("HF_TOKEN", "")

# LlamaIndex / LlamaCloud
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")
LLAMA_CLOUD_PROJECT_ID = os.getenv("LLAMA_CLOUD_PROJECT_ID", "")
LLAMA_CLOUD_PIPELINE_NAME = os.getenv("LLAMA_CLOUD_PIPELINE_NAME", "financial-rag-report-pipeline")
LLAMA_CLOUD_EMBED_MODEL = os.getenv("LLAMA_CLOUD_EMBED_MODEL", "")
LLAMA_DATA_SINKS_ID = os.getenv("LLAMA_DATA_SINKS_ID", "")

# Qdrant Cloud
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "financial_ocr_chunks")

# FPT Cloud Reranker & Embedding
FPT_RERANK_BASE_URL = os.getenv("FPT_RERANK_BASE_URL", "https://mkp-api.fptcloud.com")
FPT_RERANK_API_KEY = os.getenv("FPT_RERANK_API_KEY", "")
FPT_RERANK_MODEL = os.getenv("FPT_RERANK_MODEL", "bge-reranker-v2-m3")
FPT_RERANK_TPM = int(os.getenv("FPT_RERANK_TPM", "100000"))
FPT_RERANK_RPM = int(os.getenv("FPT_RERANK_RPM", "50"))

FPT_EMBEDDING_MODEL = os.getenv("FPT_EMBEDDING_MODEL", "Vietnamese_Embedding")
FPT_EMBEDDING_TPM = int(os.getenv("FPT_EMBEDDING_TPM", "100000"))
FPT_EMBEDDING_RPM = int(os.getenv("FPT_EMBEDDING_RPM", "50"))

# OpenAI LLM API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-5.4-mini")
REPORT_MODEL = os.getenv("REPORT_MODEL", "deepseek-v4-pro")
PLANNER_API_KEY = os.getenv("PLANNER_API_KEY", OPENAI_API_KEY)
PLANNER_API_BASE = os.getenv("PLANNER_API_BASE", OPENAI_API_BASE)

# vNext task-specific LLM routing
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "gemini-2.5-flash")
EXTRACTION_API_KEY = os.getenv(
    "EXTRACTION_API_KEY",
    os.getenv(
        "SHOPAPI_LLM_API_KEY",
        os.getenv("SHOPAIKEY_API_KEY", ""),
    ),
)
EXTRACTION_API_BASE = os.getenv(
    "EXTRACTION_API_BASE",
    os.getenv("SHOPAPI_LLM_API_BASE", "https://direct.shopaikey.com/v1"),
)

FINANCIAL_REASONING_MODEL = os.getenv("FINANCIAL_REASONING_MODEL", "qwen3-235b-a22b-thinking-2507")
FINANCIAL_REASONING_API_KEY = os.getenv(
    "FINANCIAL_REASONING_API_KEY",
    os.getenv(
        "SHOPAPI_LLM_API_KEY",
        os.getenv("SHOPAIKEY_API_KEY", ""),
    ),
)
FINANCIAL_REASONING_API_BASE = os.getenv(
    "FINANCIAL_REASONING_API_BASE",
    "https://api.shopaikey.com/v1",
)

CHART_PLANNING_MODEL = os.getenv("CHART_PLANNING_MODEL", "qwen3-235b-a22b-thinking-2507")
CHART_PLANNING_API_KEY = os.getenv("CHART_PLANNING_API_KEY", FINANCIAL_REASONING_API_KEY)
CHART_PLANNING_API_BASE = os.getenv("CHART_PLANNING_API_BASE", FINANCIAL_REASONING_API_BASE)
VNEXT_REPORT_FILENAME = os.getenv("VNEXT_REPORT_FILENAME", "A32_Financial_Report_vNext.html")
VNEXT_AUDIT_THRESHOLD = float(os.getenv("VNEXT_AUDIT_THRESHOLD", "0.88"))
VNEXT_MAX_ATTEMPTS = int(os.getenv("VNEXT_MAX_ATTEMPTS", "3"))
REPORT_BENCHMARK_REFERENCE_HTML = os.getenv(
    "REPORT_BENCHMARK_REFERENCE_HTML",
    "data/reports/A32_Financial_Report_v2.html",
)

# Local paths
RAW_OCR_DIR = os.getenv("RAW_OCR_DIR", "data/A32")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "data/processed")
EVAL_FILE = os.getenv("EVAL_FILE", "data/A32/question_eval.json")
REPORT_OUTPUT_DIR = os.getenv("REPORT_OUTPUT_DIR", "data/reports")
LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", "data/processed/rag_report.duckdb")

# Helper to get absolute paths
def get_abs_path(rel_path_str: str) -> str:
    path = Path(rel_path_str)
    if path.is_absolute():
        return str(path)
    return str(BASE_DIR / path)

# Resolve paths
RAW_OCR_DIR_ABS = get_abs_path(RAW_OCR_DIR)
PROCESSED_DIR_ABS = get_abs_path(PROCESSED_DIR)
EVAL_FILE_ABS = get_abs_path(EVAL_FILE)
REPORT_OUTPUT_DIR_ABS = get_abs_path(REPORT_OUTPUT_DIR)
LOCAL_DB_PATH_ABS = get_abs_path(LOCAL_DB_PATH)

# Ensure directories exist
os.makedirs(PROCESSED_DIR_ABS, exist_ok=True)
os.makedirs(REPORT_OUTPUT_DIR_ABS, exist_ok=True)
os.makedirs(os.path.join(REPORT_OUTPUT_DIR_ABS, "charts"), exist_ok=True)
os.makedirs(os.path.join(REPORT_OUTPUT_DIR_ABS, "html"), exist_ok=True)
os.makedirs(os.path.join(REPORT_OUTPUT_DIR_ABS, "markdown"), exist_ok=True)
os.makedirs(os.path.join(REPORT_OUTPUT_DIR_ABS, "eval_runs"), exist_ok=True)

# Retrieval defaults
DEFAULT_VECTOR_TOP_K = int(os.getenv("DEFAULT_VECTOR_TOP_K", "30"))
DEFAULT_KEYWORD_TOP_K = int(os.getenv("DEFAULT_KEYWORD_TOP_K", "30"))
DEFAULT_RERANK_TOP_N = int(os.getenv("DEFAULT_RERANK_TOP_N", "10"))
DEFAULT_REPORT_TOP_N = int(os.getenv("DEFAULT_REPORT_TOP_N", "15"))
MIN_EVIDENCE_SCORE = float(os.getenv("MIN_EVIDENCE_SCORE", "0.35"))
ABSTAIN_MIN_CONTEXTS = int(os.getenv("ABSTAIN_MIN_CONTEXTS", "1"))
ABSTAIN_MIN_RERANK_SCORE = float(os.getenv("ABSTAIN_MIN_RERANK_SCORE", "0.20"))
