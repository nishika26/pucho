"""Configuration module.

Holds settings + database connections. Submodules expose typed config
objects that other layers import (`from config.db import get_session`,
`from config.settings import settings`).
"""

from config.db import get_session

__all__ = ["get_session"]