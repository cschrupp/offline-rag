"""Compatibility shim for documented ``settings`` module location."""

from offline_rag.config import AppSettings, ConfigError, load_settings

__all__ = ["AppSettings", "ConfigError", "load_settings"]
