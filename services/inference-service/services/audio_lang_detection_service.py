"""Audio Language Detection TaskService."""

from services.base.audio_base import AudioBase
from services.base.task_service import PostProcessFormat


class AudioLanguageDetectionTaskService(AudioBase):
    """
    TaskService for Audio Language Detection inference.

    AudioBase handles base64-passthrough preprocessing and Triton I/O; the
    adapter_config maps Triton tensors to flat `language_code`/`confidence`/
    `all_scores` fields (ALL_SCORES parsed via transform "json_parse").
    postprocess_output reshapes those into ULCA's AudioLangDetectionList
    (`langPrediction: [{langCode, langScore}]`) — the tensor mapping itself
    stays adapter_config-driven; only this final reshape is code.
    """

    async def postprocess_output(self, result: PostProcessFormat):
        # Reuse the adapter-driven envelope (taskType + config echo already
        # declared in adapter_config) — only reshape each output item.
        response = await super().postprocess_output(result)
        response["output"] = [
            {"langPrediction": self._build_lang_prediction(item)}
            for item in response.get("output", [])
        ]
        return response

    @staticmethod
    def _build_lang_prediction(item):
        """
        Prefer the full candidate ranking (all_scores) when it's a usable
        {lang_code: score} dict — it already includes the top pick, so using
        language_code/confidence too would just duplicate that entry.
        Falls back to a single-entry prediction from language_code/confidence
        when all_scores is absent or not in the expected shape.
        """
        all_scores = item.get("all_scores")
        if isinstance(all_scores, dict) and all_scores:
            return [
                {"langCode": lang, "langScore": score}
                for lang, score in all_scores.items()
            ]

        language_code = item.get("language_code")
        if language_code is None:
            return []
        prediction = {"langCode": language_code}
        confidence = item.get("confidence")
        if confidence is not None:
            prediction["langScore"] = confidence
        return [prediction]


__all__ = ["AudioLanguageDetectionTaskService"]
