"""
Endpoint-host policy: what ENDPOINT_VALIDATION_ALLOW_PRIVATE_HOSTS does and,
more importantly, what it must never do.

The setting exists so a deployment whose model fleet sits entirely on private
infrastructure can register those endpoints at all. It relaxes exactly one
rule: the private/reserved address check. Cloud metadata, loopback,
link-local, unspecified, multicast and cluster-internal hostnames stay blocked
with the setting on, and those cases are the point of this file.
"""

import asyncio
import socket

import pytest

from app.utils import security


@pytest.fixture
def allow_private(monkeypatch):
    """Turn ENDPOINT_VALIDATION_ALLOW_PRIVATE_HOSTS on for one test."""
    monkeypatch.setattr(
        security.settings, "endpoint_validation_allow_private_hosts", True
    )


@pytest.fixture(autouse=True)
def _default_off(monkeypatch):
    """Every test starts from the shipped default, whatever the env holds."""
    monkeypatch.setattr(
        security.settings, "endpoint_validation_allow_private_hosts", False
    )


def _fake_resolver(monkeypatch, *addresses):
    """Make getaddrinfo return *addresses* without touching the network."""

    async def _getaddrinfo(host, port, **kwargs):
        await asyncio.sleep(0)  # keep this a real coroutine for wait_for
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in addresses
        ]

    class _Loop:
        getaddrinfo = staticmethod(_getaddrinfo)

    monkeypatch.setattr(security.asyncio, "get_running_loop", lambda: _Loop())


# The endpoints from AI4IDS-2767 that the guard was rejecting.
TICKET_HOSTS = [
    "10.185.33.143",
    "10.185.33.147",
    "10.185.33.138",
    "10.185.35.68",
    "10.185.33.133",
]


class TestDefaultIsUnchanged:
    """The guard must behave exactly as before for anyone who does not set
    the flag. This is the regression that matters most."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", TICKET_HOSTS)
    async def test_private_host_blocked_when_setting_off(self, host):
        assert await security.is_safe_host(host) is False

    @pytest.mark.asyncio
    async def test_public_host_still_allowed_when_setting_off(self):
        assert await security.is_safe_host("8.8.8.8") is True

    @pytest.mark.asyncio
    async def test_empty_hostname_still_blocked(self):
        assert await security.is_safe_host("") is False


class TestAllowPrivateHosts:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", TICKET_HOSTS)
    async def test_ticket_hosts_allowed_when_setting_on(self, host, allow_private):
        assert await security.is_safe_host(host) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host", ["172.16.4.9", "192.168.1.5", "10.0.0.1", "fd12:3456::1"]
    )
    async def test_other_private_ranges_allowed_too(self, host, allow_private):
        """No range list to maintain: any private address is accepted, which
        is the whole point of a boolean over a CIDR allowlist."""
        assert await security.is_safe_host(host) is True

    @pytest.mark.asyncio
    async def test_public_host_still_allowed(self, allow_private):
        assert await security.is_safe_host("8.8.8.8") is True


class TestHardBlocksSurviveTheSetting:
    """These must fail with the setting ON. Each one is a real attack path,
    not a hypothetical."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host",
        [
            "169.254.169.254",  # cloud metadata, hands out credentials
            "fd00:ec2::254",  # the same thing over IPv6, a unique-local addr
            "127.0.0.1",  # this service's own pod
            "::1",
            "0.0.0.0",
            "224.0.0.1",  # multicast
        ],
    )
    async def test_address_blocked_even_when_setting_on(self, host, allow_private):
        assert await security.is_safe_host(host) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "kubernetes.default.svc",
            "platform-core.default.svc.cluster.local",
            "some-service.cluster.local",
        ],
    )
    async def test_cluster_internal_hostname_blocked_even_when_setting_on(
        self, host, allow_private
    ):
        assert await security.is_safe_host(host) is False


class TestResolvedHostnames:
    """A DNS name gets the same policy as a literal, applied per resolved
    address, so the setting cannot be sidestepped in either direction."""

    @pytest.mark.asyncio
    async def test_name_resolving_to_private_blocked_when_setting_off(
        self, monkeypatch
    ):
        _fake_resolver(monkeypatch, "10.185.33.143")
        assert await security.is_safe_host("llm.internal.example") is False

    @pytest.mark.asyncio
    async def test_name_resolving_to_private_allowed_when_setting_on(
        self, monkeypatch, allow_private
    ):
        _fake_resolver(monkeypatch, "10.185.33.143")
        assert await security.is_safe_host("llm.internal.example") is True

    @pytest.mark.asyncio
    async def test_name_resolving_to_metadata_blocked_when_setting_on(
        self, monkeypatch, allow_private
    ):
        _fake_resolver(monkeypatch, "169.254.169.254")
        assert await security.is_safe_host("rebind.example") is False

    @pytest.mark.asyncio
    async def test_all_resolved_addresses_must_pass(self, monkeypatch, allow_private):
        """One bad address in a multi-A record poisons the whole host."""
        _fake_resolver(monkeypatch, "10.185.33.143", "169.254.169.254")
        assert await security.is_safe_host("mixed.example") is False

    @pytest.mark.asyncio
    async def test_resolution_failure_still_fails_closed(
        self, monkeypatch, allow_private
    ):
        async def _boom(host, port, **kwargs):
            await asyncio.sleep(0)
            raise socket.gaierror("no such host")

        class _Loop:
            getaddrinfo = staticmethod(_boom)

        monkeypatch.setattr(security.asyncio, "get_running_loop", lambda: _Loop())
        assert await security.is_safe_host("nonexistent.example") is False


class TestExemptionIsLogged:
    @pytest.mark.asyncio
    async def test_allowed_private_host_is_logged(self, caplog, allow_private):
        """Every SSRF exemption leaves an audit trail naming the host."""
        with caplog.at_level("INFO", logger=security.__name__):
            assert await security.is_safe_host("10.185.33.143") is True
        assert any(
            "10.185.33.143" in record.getMessage() for record in caplog.records
        ), [r.getMessage() for r in caplog.records]

    @pytest.mark.asyncio
    async def test_public_host_is_not_logged_as_an_exemption(
        self, caplog, allow_private
    ):
        with caplog.at_level("INFO", logger=security.__name__):
            assert await security.is_safe_host("8.8.8.8") is True
        assert not caplog.records
