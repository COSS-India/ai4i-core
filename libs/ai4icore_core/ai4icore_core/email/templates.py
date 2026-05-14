"""Jinja2 wrapper with autoescape forced on for HTML.

Each consuming service supplies its own template directory:

    renderer = TemplateRenderer([Path("app/templates/emails")])
    html, text = renderer.render("<template_name>", {"user": user})

Template naming convention: <name>.html and <name>.txt files in the
supplied directory. Both are rendered with the same context. HTML is
auto-escaped; text is not (text has no HTML exploit surface).
"""

from pathlib import Path
from typing import Iterable

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


class TemplateRenderer:
    def __init__(self, template_dirs: Iterable[Path]) -> None:
        loader = FileSystemLoader([str(p) for p in template_dirs])
        common = dict(
            loader=loader,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # HTML env auto-escapes; text env does not (no exploit surface).
        self._html_env = Environment(
            autoescape=select_autoescape(default_for_string=True, default=True),
            **common,
        )
        self._text_env = Environment(autoescape=False, **common)

    def render(self, name: str, ctx: dict) -> tuple[str, str]:
        html = self._html_env.get_template(f"{name}.html").render(**ctx)
        text = self._text_env.get_template(f"{name}.txt").render(**ctx)
        return html, text
