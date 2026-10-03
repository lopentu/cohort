"""Public serving configuration must fail closed before opening research state."""
import pytest

from cohort.ui.hosting import HostingConfig


@pytest.mark.parametrize('root', ['/cohort/', '//cohort', '/cohort/../other', '/cohort?x=1', '/cohort%2fother'])
def test_rejects_ambiguous_prefix(root):
    with pytest.raises(ValueError):
        HostingConfig(root_path=root)


@pytest.mark.parametrize('origin', ['http://example.org', 'https://user:secret@example.org',
                                    'https://example.org/cohort', 'https://example.org?x=1',
                                    'https://example.org:bad', 'https://'])
def test_public_origin_is_exact_https_origin(origin):
    with pytest.raises(ValueError):
        HostingConfig(public_origin=origin, trusted_proxy_ips='127.0.0.1')


@pytest.mark.parametrize('proxies', ['*', '0.0.0.0/0', 'example.org', '192.0.2.1', ''])
def test_trusted_proxy_is_explicit_loopback(proxies):
    with pytest.raises(ValueError):
        HostingConfig(public_origin='https://example.org', trusted_proxy_ips=proxies)


def test_default_hosting_keeps_proxy_headers_disabled():
    config = HostingConfig()
    assert config.trusted_proxy_ips is None and config.public_origin is None
    assert config.root_path == ''


@pytest.mark.parametrize('origin', ['https://example.org\n', 'https://example.org:0',
                                    'https://example.org#', 'https://example.org?'])
def test_rejects_noncanonical_origin_spelling(origin):
    with pytest.raises(ValueError):
        HostingConfig(public_origin=origin, trusted_proxy_ips='127.0.0.1')
