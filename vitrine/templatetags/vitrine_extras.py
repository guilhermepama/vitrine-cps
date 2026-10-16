"""Filtros da vitrine pública (spec 07)."""

from urllib.parse import urlsplit

from django import template

register = template.Library()


@register.filter
def dominio(url):
    """"https://www.github.com/x/y" → "github.com", para rotular o link sem mostrar a URL inteira."""
    host = urlsplit(url or "").hostname or ""
    return host[4:] if host.startswith("www.") else host
