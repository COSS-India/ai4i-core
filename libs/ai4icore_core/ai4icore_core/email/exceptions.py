class EmailError(Exception):
    """Base class for email lib errors."""


class EmailConfigError(EmailError):
    """Raised when settings are invalid or missing for the selected provider."""


class EmailDeliveryError(EmailError):
    """Raised when a provider fails to send a message."""
