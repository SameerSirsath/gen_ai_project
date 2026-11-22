"""
app/routes package — Blueprint route registrations.
"""

from .dashboard import dashboard_bp
from .company_api import company_bp
from .leads_api import leads_bp

__all__ = ["dashboard_bp", "company_bp", "leads_bp"]
