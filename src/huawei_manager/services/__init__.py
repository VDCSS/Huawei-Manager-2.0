# services/__init__.py — Package de serviços Huawei Manager.
# Re-exporta todo o conteúdo do catálogo legado para backward compat.
from huawei_manager.services.catalog import (  # noqa: F401
    DEVICE_CATEGORIES,
    DEVICE_TYPES,
    SERVICE_REGISTRY,
    ServiceDef,
    execute_service,
    get_all_show_commands,
    get_categories_for,
    get_service_by_id,
    get_services_for,
    parse_params,
)
