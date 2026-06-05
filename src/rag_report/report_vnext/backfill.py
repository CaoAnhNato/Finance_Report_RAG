from __future__ import annotations

import json
from typing import Any

from src.rag_report.report_vnext.evidence import (
    OCR_EXTRACTION_SPECS,
    _chunk_items,
    _collect_snippet_for_item,
    _load_ocr_document,
    _parse_backfill_json,
    _recompute_data_gaps,
)
from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import FinancialFact, IntroEvidencePack


class IntroExtractionBackfill:
    def __init__(self, use_llm: bool = True) -> None:
        self.use_llm = use_llm

    def _backfill_batch(
        self,
        *,
        client: Any,
        config: Any,
        year: int,
        doc: Any,
        batch_index: int,
        batch_items: list[str],
    ) -> dict[str, object]:
        snippets = {item_name: _collect_snippet_for_item(doc, item_name) for item_name in batch_items}
        messages = [
            {
                "role": "system",
                "content": (
                    "Trich xuat JSON ngan gon cho cac field tai chinh con thieu tu OCR bao cao tai chinh. "
                    "Chi tra ve JSON object, key la canonical field name, value gom raw_value, normalized_value, page, "
                    "statement_or_note, excerpt. Neu khong tim thay thi bo qua key do. Khong bia."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Fiscal year: {year}\n"
                    f"Required fields: {', '.join(batch_items)}\n"
                    f"Relevant snippets:\n{json.dumps(snippets, ensure_ascii=False, indent=2)}"
                ),
            },
        ]

        for attempt in range(1, 3):
            print(
                f"[vNext]     backfill request year {year} batch {batch_index} attempt {attempt}: {', '.join(batch_items)}"
            )
            raw_json = call_llm_until_nonempty(
                client,
                config.model,
                messages,
                temperature=0.0,
                max_tokens=800,
                sleep_seconds=0.5,
                max_attempts=1,
                task_type="extraction",
                base_url=config.base_url,
                debug=True,
                debug_label=f"backfill year {year} batch {batch_index}",
                stream=True,
            )
            parsed = _parse_backfill_json(raw_json)
            if isinstance(parsed, dict):
                return parsed
            print(
                f"[vNext]     backfill parse failed year {year} batch {batch_index} attempt {attempt}: "
                f"content_length={len(raw_json.strip())}"
            )
        return {}

    def backfill(self, evidence_pack: IntroEvidencePack) -> IntroEvidencePack:
        if not self.use_llm:
            return evidence_pack

        client, config = get_llm_client("extraction")
        updated = evidence_pack.model_copy(deep=True)
        known_pairs = {(fact.fiscal_year, fact.canonical_line_item) for fact in updated.facts}

        for year in updated.years:
            doc = _load_ocr_document(year)
            if doc is None:
                continue
            print(f"[vNext]     backfill OCR year {year}")
            missing_items = [
                item_name
                for item_name in OCR_EXTRACTION_SPECS
                if (year, item_name) not in known_pairs
            ]
            if not missing_items:
                continue
            print(f"[vNext]     backfill request year {year}: {', '.join(missing_items)}")
            for batch_index, batch_items in enumerate(_chunk_items(missing_items), start=1):
                parsed = self._backfill_batch(
                    client=client,
                    config=config,
                    year=year,
                    doc=doc,
                    batch_index=batch_index,
                    batch_items=batch_items,
                )
                if not parsed:
                    continue
                for item_name in batch_items:
                    payload = parsed.get(item_name)
                    if not isinstance(payload, dict):
                        continue
                    normalized_value = payload.get("normalized_value")
                    try:
                        normalized_value = float(normalized_value) if normalized_value is not None else None
                    except (TypeError, ValueError):
                        normalized_value = None
                    updated.facts.append(
                        FinancialFact(
                            canonical_line_item=item_name,
                            fiscal_year=year,
                            value=normalized_value,
                            unit="VND",
                            source_file=str(doc.path),
                            page=payload.get("page"),
                            statement_or_note=payload.get(
                                "statement_or_note",
                                OCR_EXTRACTION_SPECS[item_name]["statement_or_note"],
                            ),
                            raw_value=payload.get("raw_value"),
                            normalized_value=normalized_value,
                            excerpt=payload.get("excerpt"),
                        )
                    )

        updated.data_gaps = _recompute_data_gaps(updated.facts, updated.years)
        return updated
