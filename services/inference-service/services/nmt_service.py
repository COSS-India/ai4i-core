"""NMT (Neural Machine Translation) TaskService."""
from services.base.text_base import TextBase


class NMTTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    async def postprocess(self, payload, response_items, source_texts):
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target = self.unwrap_output_value(item.get("target", ""))
            output_list.append({"source": item["source"], "target": str(target)})
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

__all__ = ["NMTTaskService"]
