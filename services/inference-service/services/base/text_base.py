"""
TextBase — base class for all text-backed inference services (NMT, NER, Transliteration, etc.).

Implements common text pipeline steps:
  validate_request  → input + config presence check
  preprocess_input  → extract → sanitize → chunk pipeline

Subclasses must implement:
  _deserialize_payload, _get_inference_model_class, postprocess_output, _build_response

Task-specific helpers (_pair_with_sources, _chunk_inputs, etc.) are available opt-in.
"""

from typing import Any, Dict, List

from interfaces.task_service import BaseTaskService
from ai4icore_core.telemetry import async_trace_stage


class TextBase(BaseTaskService):
    """Base class for all text inference services."""

    CHUNK_SIZE: int = 90

    # ------------------------------------------------------------------
    # Pipeline hooks — subclasses must implement all four
    # ------------------------------------------------------------------

    # async def postprocess_output(
    #     self,
    #     response_items: List[Dict[str, Any]],
    #     source_texts: List[str] = None,
    #     **kwargs: Any,
    # ) -> Dict[str, Any]:
    #     raise NotImplementedError(f"{self.__class__.__name__} must implement postprocess_output")

    # def _create_inference_model(self, adapter_config: Any) -> Any:
    #     raise NotImplementedError(f"{self.__class__.__name__} must implement _create_inference_model")

    # def _build_response(self, request: Any, postprocessed: Dict[str, Any]) -> Any:
    #     raise NotImplementedError(f"{self.__class__.__name__} must implement _build_response")

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    @async_trace_stage("validate")
    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        if not getattr(request, "input", None):
            raise ValueError(f"{self.task_name}: payload must contain a non-empty 'input' field")
        if not getattr(request, "config", None):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

        input_items = getattr(request, "input", [])
        for idx, item in enumerate(input_items):
            source = item.get("source") if isinstance(item, dict) else getattr(item, "source", None)
            if not source or not isinstance(source, str):
                raise ValueError(f"{self.task_name}: input[{idx}]['source'] must be a non-empty string")

    @async_trace_stage("preprocess_input")
    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        await super().preprocess_input(input_data)

        source_texts = await self.extract_field_from_items(input_data, "source")
        sanitized = [self._sanitize_source(t) for t in source_texts]

        items = []
        for flat_idx, item in enumerate(input_data):
            item_dict = (
                item if isinstance(item, dict)
                else (item.model_dump(by_alias=False) if hasattr(item, "model_dump") else item.dict())
            )
            items.append({
                **item_dict,
                "source": sanitized[flat_idx] if flat_idx < len(sanitized) else "",
                "_chunk": flat_idx // self.CHUNK_SIZE,
            })

        return items

    # ------------------------------------------------------------------
    # Text input helpers
    # ------------------------------------------------------------------

    def _sanitize_source(self, text: Any) -> str:
        """Normalize a source string: None/empty → single space, collapse whitespace runs."""
        if not text:
            return " "
        text = str(text).replace("\n", " ").replace("\r", " ")
        return self._normalize_text(text) or " "

    def _chunk_inputs(self, items: List[Any], size: int = 90) -> List[List[Any]]:
        """Split a flat list into consecutive chunks of at most `size` items."""
        return [items[i: i + size] for i in range(0, len(items), size)]

    def _normalize_text(self, text: str) -> str:
        """Collapse all whitespace runs to a single space and strip ends."""
        return " ".join(text.split()).strip()

    # ------------------------------------------------------------------
    # Postprocess helpers (opt-in)
    # ------------------------------------------------------------------

    def _pair_with_sources(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> List[Dict[str, Any]]:
        """Zip each response item with its source text, adding a 'source' key."""
        paired = []
        for idx, item in enumerate(response_items):
            source = source_texts[idx] if idx < len(source_texts) else ""
            paired.append({**item, "source": source})
        return paired
