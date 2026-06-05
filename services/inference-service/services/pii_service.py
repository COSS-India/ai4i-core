"""PII (Personally Identifiable Information) Detection and Redaction TaskService."""

from services.base.task_service import BaseTaskService


class PIITaskService(BaseTaskService):
    """
    TaskService for PII Detection and Redaction inference — NOT YET IMPLEMENTED.

    Registered in task_service_registry so PII requests fail loudly
    (NotImplementedError → 501) instead of falling through the base
    pipeline's defaults into a confusing mapper error.

    To implement: replace validate_request below with real checks (language /
    redaction mode), set payload_key, add postprocess (entity formatting +
    redaction) and any PII-specific convert hooks — see NERTaskService for
    the closest template.
    """

    async def validate_request(self, payload):
        raise NotImplementedError(
            f"{self.task_name}: PII inference is not implemented"
        )


__all__ = ["PIITaskService"]
