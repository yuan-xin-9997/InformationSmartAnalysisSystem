"""ORM models.

Importing each model module here registers it on ``Base.metadata`` so that
``init_db()`` / ``Base.metadata.create_all`` creates the corresponding tables.
"""
from .analysis import AnalysisResult, AnalysisTask, TaskSource
from .info_source import InfoItem, InfoItemFigure, InfoSource
from .push import PushRule, PushRun, SmtpConfig, get_smtp_config_row
from .scheduled_job import ScheduledJob
from .task import TaskLog, TaskRun
from .user import PagePermission, User

__all__ = [
    "User",
    "PagePermission",
    "TaskRun",
    "TaskLog",
    "InfoSource",
    "InfoItem",
    "InfoItemFigure",
    "AnalysisTask",
    "TaskSource",
    "AnalysisResult",
    "ScheduledJob",
    "PushRule",
    "PushRun",
    "SmtpConfig",
    "get_smtp_config_row",
]
