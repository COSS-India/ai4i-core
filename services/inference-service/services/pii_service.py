"""PII (Personally Identifiable Information) Detection and Redaction TaskService."""

from services.base.task_service import BaseTaskService


class PIITaskService(BaseTaskService):
    """
    TaskService for PII Detection and Redaction inference — NOT YET IMPLEMENTED.

    Registered in task_service_registry so PII requests fail loudly
    (NotImplementedError from the base pipeline) instead of silently
    returning nothing.

    To implement: set payload_key, add validate_request (language / redaction
    mode checks), postprocess (entity formatting + redaction), and any
    PII-specific convert hooks — see NERTaskService for the closest template.
    """


__all__ = ["PIITaskService"]
