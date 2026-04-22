"""Routes package for Flask blueprints."""
from .auth import auth_bp
from .admin import admin_bp, init_drive_monitor
from .widget import widget_bp
from .google_auth import google_auth_bp
from .settings import settings_bp

__all__ = ['auth_bp', 'admin_bp', 'widget_bp', 'google_auth_bp', 'settings_bp', 'init_drive_monitor']
