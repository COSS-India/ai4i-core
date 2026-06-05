"""Language Detection TaskService."""
from services.base.text_base import TextBase


class LanguageDetectionTaskService(TextBase):
    # No language config required — language is DETECTED not specified.
    # Base validate_request handles input existence; language block skipped.
    #
    # Output is adapter_config-driven: transform ["json_parse", "wrap_list"]
    # turns the model's JSON prediction string into [prediction], and
    # pair_with_input "input.source" pairs each item with its input text.
    # The base default postprocess_output applies that shaping — no code here.
    pass


__all__ = ["LanguageDetectionTaskService"]
