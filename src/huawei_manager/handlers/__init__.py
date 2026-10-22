"""Event handlers — mixin composite from 5 domain modules."""

from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.handlers.dashboard import DashboardMixin
from huawei_manager.handlers.devices import DevicesMixin
from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.handlers.ssh import SshMixin


class EventHandlers(
    AuthMixin,
    SshMixin,
    ServicesMixin,
    DevicesMixin,
    DashboardMixin,
):
    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30
