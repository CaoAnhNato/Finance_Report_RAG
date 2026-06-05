__all__ = ["IntroReportVNextPipeline"]


def __getattr__(name: str):
    if name == "IntroReportVNextPipeline":
        from src.rag_report.report_vnext.pipeline import IntroReportVNextPipeline

        return IntroReportVNextPipeline
    raise AttributeError(name)
