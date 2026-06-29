"""NMT (Neural Machine Translation) TaskService."""
from services.base.text_base import TranslationTextBase


class NMTTaskService(TranslationTextBase):
    # Fully driven by the base + adapter_config: source/target validation comes
    # from TranslationTextBase, and the output_transform (source pairing + config
    # echo) is the NMT contract. The /nmt route's response_model excludes config.
    pass


__all__ = ["NMTTaskService"]
