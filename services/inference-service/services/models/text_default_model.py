"""Default text inference model using TextBase."""

from services.base.text_base import TextBase


class TextDefaultModel(TextBase):
    """
    Default NMT model service.

    Extends TextBase pipeline with NMT-specific steps:
      validate_request   → adds language pair validation
      preprocess_input   → adds script code resolution per segment
      postprocess_output → pairs source texts, wraps in TranslationOutput
      run_inference      → wraps result in NMTInferenceResponse
    """
    ...

    # Send response different for different models.
