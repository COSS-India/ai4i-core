"""Thin re-export of ai4i_core.pii_crypto — kept at this import path so
existing call sites (``from consumers.notifications_consumer import
pii_crypto``) don't need to change.

This used to be its own copy of auth-service's decrypt logic; moved into
ai4i_core once platform-core-service and payperuse_consumer needed the same
decrypt (ai4i_core.kafka.recipients), per this module's own former
docstring: "If a third consumer of this key ever shows up, this belongs in
ai4i_core instead of a second copy here."
"""
from ai4i_core.pii_crypto import (  # noqa: F401
    EMAIL_CONTEXT,
    PIIEncryptionError,
    _PREFIX,
    configure_key,
    decrypt_email,
    is_encrypted,
)
