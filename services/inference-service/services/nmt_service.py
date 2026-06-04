"""NMT (Neural Machine Translation) TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat


class NMTTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    async def postprocess_output(self, result: PostProcessFormat):
        paired = self._pair_with_sources(result.response_data, result.source_texts)
        output_list = []
        for item in paired:
            target = self.unwrap_output_value(item.get("target", ""))
            output_list.append({"source": item["source"], "target": str(target)})
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

__all__ = ["NMTTaskService"]
