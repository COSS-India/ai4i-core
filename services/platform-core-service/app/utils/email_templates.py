"""Alertmanager email subject + body templates.

Single source of truth — both alert-management and alert-config-sync used to
carry identical copies of these strings (one of the bigger DRY violations in
the source).

Templates use Alertmanager's Go-template syntax (`{{ ... }}`). Two placeholders
are *ours*, not Go-template:
  - ``__ENVIRONMENT_TITLE__`` — substituted at sync time from settings.
  - ``__TENANT_NAME__`` — substituted at sync time per tenant receiver.

Call ``format_email_templates(environment, tenant=None)`` to produce the final
strings ready to write into ``alertmanager.yml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def format_environment_title(env: Optional[str]) -> str:
    """Map an environment string to its display title.

    ``production``/``prod``/``live`` → ``Production``.
    ``staging``                       → ``Staging``.
    ``dev``/``development``/``local``/``test`` → ``Dev``.
    Anything else is title-cased; empty falls back to ``Dev``.
    """
    env_norm = (env or "").strip().lower()
    if env_norm in {"production", "prod", "live"}:
        return "Production"
    if env_norm == "staging":
        return "Staging"
    if env_norm in {"dev", "development", "local", "test"}:
        return "Dev"
    return env_norm.title() if env_norm else "Dev"


# ── Raw templates (placeholders are __ENVIRONMENT_TITLE__ and __TENANT_NAME__) ──

_SUBJECT_RAW = (
    "[{{ if eq .GroupLabels.severity \"critical\" }}CRITICAL"
    "{{ else if eq .GroupLabels.severity \"warning\" }}WARNING"
    "{{ else }}INFO{{ end }}] "
    "{{ .GroupLabels.alertname }} — __ENVIRONMENT_TITLE__ - "
    "{{ if eq .GroupLabels.severity \"critical\" }}Service Impacted"
    "{{ else if eq .GroupLabels.severity \"warning\" }}Service Degrading"
    "{{ else }}For Your Awareness{{ end }}"
)

_BODY_GLOBAL_RAW = """<p><strong>Alert Name</strong></p>
<p>{{ .GroupLabels.alertname }}</p>

<p><strong>Category</strong></p>
<p>{{ index (index .Alerts 0).Annotations "category_display" }}</p>

<p><strong>Signal</strong></p>
<p>{{ index (index .Alerts 0).Annotations "signal_display" }}</p>

{{ if index (index .Alerts 0).Annotations "service_type_full" }}<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Annotations "service_type_full" }}</p>
{{ else if index (index .Alerts 0).Labels "endpoint" }}<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Labels "endpoint" }}</p>
{{ end }}

<p><strong>Tenant</strong></p>
<p>Global (All Tenants)</p>

<p><strong>Environment</strong></p>
<p>__ENVIRONMENT_TITLE__</p>

<p><strong>Condition</strong></p>
<p>{{ index (index .Alerts 0).Annotations "condition_display" }}</p>

<p><strong>Current Value</strong></p>
<p>{{ index (index .Alerts 0).Annotations "current_value" }}</p>

<p><strong>Threshold</strong></p>
<p>{{ index (index .Alerts 0).Annotations "threshold_display" }}</p>

<p><strong>Triggered At</strong></p>
<p>{{ (index .Alerts 0).StartsAt }}</p>

<p><strong>Sustained For</strong></p>
<p>{{ index (index .Alerts 0).Annotations "sustained_for" }}</p>
"""

_BODY_TENANT_RAW = """<p><strong>Alert Name</strong></p>
<p>{{ .GroupLabels.alertname }}</p>

<p><strong>Category</strong></p>
<p>{{ index (index .Alerts 0).Annotations "category_display" }}</p>

<p><strong>Signal</strong></p>
<p>{{ index (index .Alerts 0).Annotations "signal_display" }}</p>

{{ if index (index .Alerts 0).Annotations "service_type_full" }}<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Annotations "service_type_full" }}</p>
{{ else if index (index .Alerts 0).Labels "endpoint" }}<p><strong>Service Type</strong></p>
<p>{{ index (index .Alerts 0).Labels "endpoint" }}</p>
{{ end }}

<p><strong>Tenant</strong></p>
<p>__TENANT_NAME__</p>

<p><strong>Environment</strong></p>
<p>__ENVIRONMENT_TITLE__</p>

<p><strong>Condition</strong></p>
<p>{{ index (index .Alerts 0).Annotations "condition_display" }}</p>

<p><strong>Current Value</strong></p>
<p>{{ index (index .Alerts 0).Annotations "current_value" }}</p>

<p><strong>Threshold</strong></p>
<p>{{ index (index .Alerts 0).Annotations "threshold_display" }}</p>

<p><strong>Triggered At</strong></p>
<p>{{ (index .Alerts 0).StartsAt }}</p>

<p><strong>Sustained For</strong></p>
<p>{{ index (index .Alerts 0).Annotations "sustained_for" }}</p>
"""


@dataclass
class EmailTemplates:
    """Resolved subject + body strings ready to embed into ``alertmanager.yml``."""

    subject: str
    body: str


def format_email_templates(
    environment: Optional[str],
    tenant: Optional[str] = None,
) -> EmailTemplates:
    """Return subject + body strings with ``__ENVIRONMENT_TITLE__`` (and
    optionally ``__TENANT_NAME__``) substituted.

    Pass ``tenant`` to get the tenant body variant — uses the global body
    when ``tenant`` is ``None`` or blank.
    """
    env_title = format_environment_title(environment)
    subject = _SUBJECT_RAW.replace("__ENVIRONMENT_TITLE__", env_title)

    if tenant and str(tenant).strip():
        body = _BODY_TENANT_RAW.replace(
            "__ENVIRONMENT_TITLE__", env_title
        ).replace("__TENANT_NAME__", str(tenant).strip())
    else:
        body = _BODY_GLOBAL_RAW.replace("__ENVIRONMENT_TITLE__", env_title)

    return EmailTemplates(subject=subject, body=body)
