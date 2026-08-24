from urllib.request import proxy_bypass


def test_loopback_http_requests_bypass_machine_proxy():
    assert proxy_bypass("127.0.0.1")
    assert proxy_bypass("localhost")
