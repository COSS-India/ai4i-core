"""PII Detection and Anonymization TaskService using Presidio."""

from services.base.task_service import BaseTaskService


class PIITaskService(BaseTaskService):
    """Placeholder — wired up once the Presidio endpoint test passes."""

    async def validate_request(self, payload):
        raise NotImplementedError(
            f"{self.task_name}: PII inference is not implemented yet"
        )

    # async def run_inference(self, payload, serviceInfo):
    #     from services.pii.engine import get_engine
    #
    #     engine = get_engine()
    #     language = self._get_language(payload)
    #     source_lang = self._extract_source_lang(language) or "en"
    #
    #     self.source_lang = source_lang
    #     self.target_lang = ""
    #     self.billed_input = 0
    #
    #     input_items = payload.get("input", [])
    #     source_texts = self.extract_field_from_items(input_items, "source")
    #     response_data = []
    #
    #     for text in source_texts:
    #         analyzer_results = engine.analyze(text, source_lang)
    #         anonymized = engine.anonymize(text, analyzer_results)
    #         self.billed_input += len(text.split())
    #         response_data.append({
    #             "anonymizedText": anonymized,
    #             "entities": [
    #                 {
    #                     "entityType": r.entity_type,
    #                     "start": r.start,
    #                     "end": r.end,
    #                     "score": round(r.score, 4),
    #                 }
    #                 for r in analyzer_results
    #             ],
    #         })
    #
    #     return PostProcessFormat(
    #         payload=payload,
    #         response_data=response_data,
    #         source_texts=source_texts,
    #     )
    #
    # async def postprocess_output(self, result):
    #     output = [
    #         {"source": result.source_texts[i] if i < len(result.source_texts) else "", **item}
    #         for i, item in enumerate(result.response_data)
    #     ]
    #     return {"output": output, "config": result.payload.get("config")}


__all__ = ["PIITaskService"]
