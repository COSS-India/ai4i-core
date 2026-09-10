"""Shared helper for enqueueing notification/alert emails."""

import logging
from typing import Callable, Optional

from ai4i_core.email import EmailClient, EmailMessage
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


def enqueue_email(
    background_tasks: Optional[BackgroundTasks],
    email_client: EmailClient,
    factory: Callable[[], EmailMessage],
) -> None:
    """Render and enqueue a send_safe call.

    ``factory`` is a zero-arg callable that returns an EmailMessage (e.g.
    ``lambda: render_alert_email(...)``). Render is wrapped in try/except so
    a template/data bug never 5xx's a request whose DB commit already
    succeeded — orphan-row prevention. Render failures are logged at ERROR
    for ops to catch via metrics.

    Silent no-op when no BackgroundTasks available (e.g. tests calling the
    service directly without a request).
    """
    if background_tasks is None:
        return
    try:
        message = factory()
    except Exception:
        logger.exception("email render failed")
        return
    background_tasks.add_task(email_client.send_safe, message)
