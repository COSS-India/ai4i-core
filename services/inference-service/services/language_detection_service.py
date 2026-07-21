"""Language Detection TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat


class LanguageDetectionTaskService(TextBase):
    # No language config required — language is DETECTED not specified.
    # Base validate_request handles input existence; language block skipped.
    #
    # Output is adapter_config-driven: transform ["json_parse", "wrap_list"]
    # turns the model's JSON prediction string into [prediction], and
    # pair_with_input "input.source" pairs each item with its input text.
    # postprocess_output below reuses that shaping, then normalizes each
    # prediction's key names to the ULCA contract (langCode/ScriptCode/
    # langScore) — the raw model JSON isn't guaranteed to use those names.

    async def postprocess_output(self, result: PostProcessFormat):
        response = await super().postprocess_output(result)
        for item in response.get("output", []):
            predictions = item.get("langPrediction")
            if isinstance(predictions, list):
                item["langPrediction"] = [
                    self._normalize_prediction(p) for p in predictions if isinstance(p, dict)
                ]
        return response

    @staticmethod
    def _normalize_prediction(prediction):
        lang_code = (
            prediction.get("langCode") or prediction.get("lang_code") or prediction.get("code")
        )
        script_code = (
            prediction.get("ScriptCode") or prediction.get("scriptCode")
            or prediction.get("script_code") or prediction.get("script")
        )
        lang_score = (
            prediction.get("langScore") or prediction.get("lang_score")
            or prediction.get("score") or prediction.get("confidence")
        )
        normalized = {}
        if lang_code is not None:
            normalized["langCode"] = lang_code
        if script_code is not None:
            normalized["ScriptCode"] = script_code
        if lang_score is not None:
            normalized["langScore"] = lang_score
        return normalized


__all__ = ["LanguageDetectionTaskService"]
