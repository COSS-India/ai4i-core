"""
TextBase — base class for all text-backed inference services.

Covers: NMT, NER, Transliteration, and any other text input/output task.

Inherits from BaseTaskService and implements the common text pipeline:
  _deserialize_payload    → raises NotImplementedError; subclasses parse to typed request
  validate_request        → common text null check (input + config presence)
  preprocess_input        → extract → sanitize → chunk pipeline
  run_inference           → reads service_info, calls _create_inference_model hook,
                            runs per-item loop, calls postprocess_output + _build_response
  postprocess_output      → raises NotImplementedError; subclasses shape output
  _create_inference_model → raises NotImplementedError; subclasses return InferenceModel
  _build_response         → raises NotImplementedError; subclasses wrap in typed response

Task-specific helpers (_pair_with_sources, _chunk_inputs, etc.)
live here and are available to subclasses as opt-in utilities.
"""

from typing import Any, Dict, List

from interfaces.task_service import BaseTaskService


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

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        if not getattr(request, "input", None):
            raise ValueError(f"{self.task_name}: payload must contain a non-empty 'input' field")
        if not getattr(request, "config", None):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

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

    # Should move to BaseTaskService
    #So that it can be used by all services and it is common for all services
    async def run_inference(self, request: Any) -> Any:
        config = getattr(request, "config")
        input_items = getattr(request, "input") or []

        service_id = self.service_info.get("service_id", "")
        model_name = self.service_info.get("name", "")
        triton_endpoint = self.service_info.get("endpoint", "")
        api_key = self.service_info.get("api_key")
        adapter_config = self.service_info.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                "Ensure the Orchestrator resolved the service before creating this task service."
            )

        self.logger.debug(f"Building inference model for {model_name}")
        inference_model = self._create_inference_model(adapter_config)

        config_dict = (
            config.model_dump(by_alias=False) if hasattr(config, "model_dump")
            else config.dict()
        )

        all_response_data: List[Dict[str, Any]] = []
        source_texts: List[str] = []

        for item in input_items:
            item_dict = (
                item if isinstance(item, dict)
                else (item.model_dump(by_alias=False) if hasattr(item, "model_dump") else item.dict())
            )
            source_texts.append(item_dict.get("source", ""))

            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                [item_dict], config_dict
            )
            raw_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )
            response_data = await inference_model.convert_triton_output_to_task_format(raw_output)
            all_response_data.extend(response_data)

        self.logger.info(f"inference completed: service_id={service_id}")
        postprocessed = await self.postprocess_output(all_response_data, source_texts=source_texts)
        return self._build_response(request, postprocessed)

    # ------------------------------------------------------------------
    # Text input helpers
    # ------------------------------------------------------------------

    def _sanitize_source(self, text: Any) -> str:
        """Normalize a source string: None/empty → single space, strip newlines."""
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
        """Zip each response item with its source text, adding a 'source' key."""
        paired = []
        for idx, item in enumerate(response_items):
            source = source_texts[idx] if idx < len(source_texts) else ""
            paired.append({**item, "source": source})
        return paired
