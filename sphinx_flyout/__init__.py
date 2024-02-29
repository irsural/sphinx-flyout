from pathlib import Path
from typing import Any

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.util import logging

logger = logging.getLogger(__name__)


def setup(app: Sphinx) -> None:
    app.add_config_value("sphinx_flyout_current_version", "1.0", "html", str)
    app.add_config_value("sphinx_flyout_host", "http://0.0.0.0:8000", "html", str)
    app.add_config_value("sphinx_flyout_header", "Flyout", "html", str)

    app.add_config_value("sphinx_flyout_downloads", {}, "html", dict)
    app.add_config_value("sphinx_flyout_gitea", {}, "html", dict)
    app.add_config_value("sphinx_flyout_versions", {}, "html", dict)
    app.connect("config-inited", _add_templates)
    app.connect("html-page-context", add_flyout_to_context)


def _add_templates(app: Sphinx, config: Config):
    config.templates_path.insert(0, str(Path(__file__).parent / "templates"))


def add_flyout_to_context(app: Sphinx, pagename: str, templatename: str,
                          context: dict, doctree: Any):
    if app.config.html_theme != "sphinx_rtd_theme":
        logger.warning(f"Тема {app.config.html_theme} не поддерживается. Пожалуйста, используйте "
                       "'sphinx_rtd_theme'")
        return
    logger.info(f"Writing flyout to {pagename}")
    context["current_version"] = app.config.sphinx_flyout_current_version
    host = app.config.sphinx_flyout_host
    context["header"] = app.config.sphinx_flyout_header
    context["downloads"] = _make_links_relate_to_host(
        host, 'download', app.config.sphinx_flyout_downloads
    )
    context["gitea"] = app.config.sphinx_flyout_gitea
    context["versions"] = _make_links_relate_to_host(
        host, 'ver', app.config.sphinx_flyout_versions,
    )


def _make_links_relate_to_host(host: str, section: str, links: dict) -> dict:
    for key, value in links.items():
        links[key] = f"{host}/{section}/{value}"
    return links
