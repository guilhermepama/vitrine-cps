"""Imagens de media/ servidas só no desenvolvimento local (DEBUG=1, sem R2)."""

import importlib

from django.urls import Resolver404, clear_url_caches, resolve

import config.urls


def _rotas(settings, debug, backend):
    settings.DEBUG = debug
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": backend}}
    clear_url_caches()
    return importlib.reload(config.urls)


def _serve_media(modulo):
    try:
        resolve("/media/projetos/capa.jpg", urlconf=modulo)
    except Resolver404:
        return False
    return True


def test_media_servida_no_desenvolvimento_local(settings):
    try:
        assert _serve_media(_rotas(settings, True, "django.core.files.storage.FileSystemStorage"))
    finally:
        _rotas(settings, False, "django.core.files.storage.FileSystemStorage")


def test_media_nao_servida_sem_debug_nem_com_r2(settings):
    try:
        assert not _serve_media(_rotas(settings, False, "django.core.files.storage.FileSystemStorage"))
        assert not _serve_media(_rotas(settings, True, "storages.backends.s3.S3Storage"))
    finally:
        _rotas(settings, False, "django.core.files.storage.FileSystemStorage")
