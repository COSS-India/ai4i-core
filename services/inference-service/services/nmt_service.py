"""NMT (Neural Machine Translation) TaskService."""
from services.base.text_base import TextBase


class NMTTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    # postprocess_output: base default (source pairing + unwrap + config echo)
    # is the NMT contract — the /nmt route's response_model excludes config.

__all__ = ["NMTTaskService"]
