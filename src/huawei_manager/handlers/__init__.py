"""Event handlers — mixin composite from 7 domain modules."""

from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.handlers.commands import CommandsMixin
from huawei_manager.handlers.dashboard import DashboardMixin
from huawei_manager.handlers.fetch import FetchMixin
from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.handlers.ssh import SshMixin
from huawei_manager.handlers.vnfs import VnfsMixin


class EventHandlers(
    AuthMixin,
    SshMixin,
    FetchMixin,
    CommandsMixin,
    ServicesMixin,
    VnfsMixin,
    DashboardMixin,
):
    """Event handlers mixin — composite from 7 domain modules."""

    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30
