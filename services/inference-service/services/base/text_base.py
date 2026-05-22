"""
TextBase — base class for all text-backed inference services.

Covers: NMT, TTS, NER, and any other text input/output task.

Inherits from BaseTaskService and implements the common text pipeline:
  _deserialize_payload  → converts raw dict to SimpleNamespace (for process() getattr/setattr)
  validate_request      → common text null check
  preprocess_input      → extract → sanitize → chunk pipeline
  postprocess_output    → stub; model classes use opt-in helpers

Task-specific helpers (_pair_with_sources, _chunk_inputs, etc.)
live here but are NOT called from the pipeline automatically — model
classes opt in by calling them in their overrides.
"""

from types import SimpleNamespace
from typing import Any, Dict, List

from interfaces.task_service import BaseTaskService


class TextBase(BaseTaskService):
    """Base class for all text inference services."""

    CHUNK_SIZE: int = 90

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> SimpleNamespace:
        """Convert raw dict to SimpleNamespace so process() can use getattr/setattr."""
        return SimpleNamespace(**payload)

    async def validate_request(self, request: SimpleNamespace) -> None:
        """
        Common text validation:
          1. Base null check (super)
          2. input and config must be present
        Task-specific validation is opt-in — call helpers in the model class override.
        """
        await super().validate_request(request)

        if not getattr(request, "input", None):
            raise ValueError(f"{self.task_name}: payload must contain a non-empty 'input' field")
        if not getattr(request, "config", None):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        Common text preprocessing pipeline:
          1. Base empty check (super)
          2. Extract source strings
          3. Sanitize each source
          4. Chunk into batches of at most CHUNK_SIZE segments
        Returns list of item dicts with sanitized source and _chunk index fields.
        """
        await super().preprocess_input(input_data)

        source_texts = await self.extract_field_from_items(input_data, "source")
        sanitized = [self._sanitize_source(t) for t in source_texts]

        items = []
        for flat_idx, item in enumerate(input_data):
            item_dict = item if isinstance(item, dict) else (item.dict() if hasattr(item, "dict") else item.__dict__)
            items.append({
                **item_dict,
                "source": sanitized[flat_idx] if flat_idx < len(sanitized) else "",
                "_chunk": flat_idx // self.CHUNK_SIZE,
            })

        return items

    async def postprocess_output(self, raw_triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stub — each task shapes output differently.
        Model classes implement using the opt-in helpers (_pair_with_sources, _normalize_text).
        """
        ...

    # ------------------------------------------------------------------
    # Text input helpers
    # ------------------------------------------------------------------

    def _sanitize_source(self, text: Any) -> str:
        """
        Sanitize a single source string:
          - None or empty → single space " "
          - Newlines → space
          - .strip() → clean string
        """
        if not text:
            return " "
        text = str(text).replace("\n", " ").replace("\r", " ")
        return text.strip() or " "

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
        """
        Zip each response item with its corresponding source text.
        Adds a 'source' key to every item dict.
        Opt-in — call from model class postprocess_output override.
        """
        paired = []
        for idx, item in enumerate(response_items):
            source = source_texts[idx] if idx < len(source_texts) else ""
            paired.append({**item, "source": source})
        return paired



