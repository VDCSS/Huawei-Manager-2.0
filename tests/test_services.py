from huawei_manager.services import (
    SERVICE_REGISTRY,
    VNF_CATEGORIES,
    VNF_TYPES,
    execute_service,
    get_all_show_commands,
    get_categories_for,
    get_service_by_id,
    get_services_for,
    parse_params,
)
from huawei_manager.services_data import _svc


class TestGetServicesFor:
    def test_router_returns_list(self):
        svcs = get_services_for("ROUTER")
        assert len(svcs) > 20
        assert all("ROUTER" in s.vnf_types for s in svcs)

    def test_router_with_category(self):
        svcs = get_services_for("ROUTER", "routing")
        assert len(svcs) > 0
        assert all(s.category == "routing" for s in svcs)

    def test_case_insensitive(self):
        svcs = get_services_for("router")
        assert len(svcs) > 20

    def test_invalid_type_returns_empty(self):
        assert get_services_for("NONEXISTENT") == []

    def test_invalid_category_returns_empty(self):
        assert get_services_for("ROUTER", "nonexistent") == []


class TestGetCategoriesFor:
    def test_router_returns_categories(self):
        cats = get_categories_for("ROUTER")
        assert "routing" in cats
        assert "system" in cats

    def test_invalid_type_returns_empty(self):
        assert get_categories_for("NONEXISTENT") == []

    def test_no_duplicates(self):
        cats = get_categories_for("ROUTER")
        assert len(cats) == len(set(cats))


class TestGetServiceById:
    def test_existing_id(self):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        assert svc.id == "router-routing-table"

    def test_nonexistent_id(self):
        assert get_service_by_id("nonexistent") is None

    def test_empty_id(self):
        assert get_service_by_id("") is None


class TestGetAllShowCommands:
    def test_returns_sorted(self):
        cmds = get_all_show_commands()
        names = [c[1] for c in cmds]
        assert names == sorted(names)

    def test_no_config_mode(self):
        cmds = get_all_show_commands()
        show_commands = {c[1] for c in cmds}
        for s in SERVICE_REGISTRY:
            if s.config_mode:
                cmd = s.cli_commands[0] if s.cli_commands else s.description
                assert cmd not in show_commands

    def test_no_duplicates(self):
        cmds = get_all_show_commands()
        commands = [c[1] for c in cmds]
        assert len(commands) == len(set(commands))


class TestParseParams:
    def test_extracts_params_from_description(self):
        svc = get_service_by_id("router-config-nat-outbound")
        assert svc is not None
        params = parse_params(svc)
        assert len(params) == 2
        assert params[0][0] == "acl"
        assert params[1][0] == "id"

    def test_defaults_from_cmd(self):
        svc = get_service_by_id("router-config-acl-number")
        assert svc is not None
        params = parse_params(svc)
        assert params[0][1] == "3000"

    def test_pipe_replaced_with_slash(self):
        svc = get_service_by_id("router-config-vlan-port-type")
        assert svc is not None
        params = parse_params(svc)
        assert "access/trunk/hybrid" in params[0][0]

    def test_no_params_returns_empty(self):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        assert parse_params(svc) == []

    def test_non_config_returns_empty(self):
        svc = get_service_by_id("router-bgp-summary")
        assert svc is not None
        assert parse_params(svc) == []

    def test_multiple_same_param_names(self):
        svc = get_service_by_id("router-config-nat-server")
        assert svc is not None
        params = parse_params(svc)
        ips = [p for p in params if p[0] == "ip"]
        assert len(ips) == 2


class TestExecuteServiceMock:
    def test_returns_string(self, mock_session):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        result = execute_service(svc, session_type="mock")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_includes_service_name(self, mock_session):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        result = execute_service(svc, session_type="mock")
        assert "Tabela de Roteamento" in result

    def test_includes_mock_footer(self, mock_session):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        result = execute_service(svc, session_type="mock")
        assert "MODO MOCK" in result


class TestExecuteServiceCLI:
    def test_calls_send_command(self, mock_netmiko_connection):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        execute_service(svc, session_type="cli", session=mock_netmiko_connection)
        mock_netmiko_connection.send_command.assert_called_once()

    def test_calls_send_config_set_for_config_mode(self, mock_netmiko_connection):
        svc = get_service_by_id("router-config-nat-outbound")
        assert svc is not None
        execute_service(svc, session_type="cli", session=mock_netmiko_connection)
        mock_netmiko_connection.send_config_set.assert_called_once()

    def test_no_connection_returns_error(self, mock_session):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        result = execute_service(svc, session_type="cli", session=None)
        assert "Sem conexão" in result


class TestRegistryIntegrity:
    def test_not_empty(self):
        assert len(SERVICE_REGISTRY) >= 144

    def test_all_ids_unique(self):
        ids = [s.id for s in SERVICE_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_vnf_types_are_valid(self):
        valid = set(VNF_TYPES.keys())
        for s in SERVICE_REGISTRY:
            for t in s.vnf_types:
                assert t in valid, f"{s.id} has invalid type {t}"

    def test_categories_in_vnf_categories(self):
        all_valid = set()
        for cats in VNF_CATEGORIES.values():
            all_valid.update(cats)
        for s in SERVICE_REGISTRY:
            assert s.category in all_valid, f"{s.id} has unknown category {s.category}"


class TestSvcFactory:
    def test_svc_backward_compat(self):
        svc = _svc("x", "Test", "display x", "system", ["ROUTER"])
        assert svc.id == "x"
        assert svc.name == "Test"
        assert svc.description == "display x"
        assert svc.category == "system"
        assert svc.vnf_types == ["ROUTER"]
        assert svc.cli_commands == ["display x"]
        assert not svc.config_mode

    def test_svc_keyword_args(self):
        svc = _svc(id="x", name="Test", desc="display x", cat="system", types=["ROUTER"])
        assert svc.id == "x"
        assert svc.name == "Test"
        assert svc.description == "display x"
        assert svc.category == "system"
        assert svc.vnf_types == ["ROUTER"]
        assert svc.cli_commands == ["display x"]
        assert not svc.config_mode

    def test_svc_keyword_with_config(self):
        svc = _svc(id="x", name="Test", desc="display x", cat="system", types=["ROUTER"], config=True)
        assert svc.config_mode

    def test_svc_backward_compat_with_cmds(self):
        svc = _svc("x", "Test", "display x", "system", ["ROUTER"], ["display x verbose"], True)
        assert svc.cli_commands == ["display x verbose"]
        assert svc.config_mode
