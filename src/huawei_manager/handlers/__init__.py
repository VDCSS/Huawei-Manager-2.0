"""Event handlers — mixin composite from 3 domain modules."""

from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.handlers.devices import DevicesMixin
from huawei_manager.handlers.ssh import SshMixin


class EventHandlers(
    AuthMixin,
    SshMixin,
    DevicesMixin,
):
    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30
