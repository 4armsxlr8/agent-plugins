import io
import socket
import unittest
import urllib.error
from unittest import mock

from jsonfetch import fetch_json


def _no_network(*args, **kwargs):
    raise OSError("隠しテストは外部に接続しない")


_guards = []


def setUpModule():
    # 差し替えが効かない実装 (from urllib.request import urlopen など) でも実際の接続に出ないようにする
    for target in ("socket.create_connection", "socket.socket.connect"):
        patcher = mock.patch(target, _no_network)
        patcher.start()
        _guards.append(patcher)


def tearDownModule():
    for patcher in _guards:
        patcher.stop()


def fake_urlopen(body):
    """with 文でも直接 read() でも同じ本文を返す urlopen の代役"""
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = body
    resp.status = 200
    resp.getcode.return_value = 200
    resp.headers.get_content_charset.return_value = "utf-8"
    return mock.patch("urllib.request.urlopen", return_value=resp)


def called_url(m):
    arg = m.call_args.args[0] if m.call_args.args else m.call_args.kwargs["url"]
    return getattr(arg, "full_url", arg)


class HiddenFetchJsonTest(unittest.TestCase):
    def test_returns_object(self):
        # AC-1, AC-2
        with fake_urlopen(b'{"a": 1}') as m:
            self.assertEqual(fetch_json("https://example.com/data.json", 5), {"a": 1})
        self.assertEqual(m.call_count, 1)
        self.assertEqual(called_url(m), "https://example.com/data.json")
        self.assertEqual(m.call_args.kwargs["timeout"], 5)

    def test_http_array(self):
        # AC-3
        with fake_urlopen(b"[1, 2]"):
            self.assertEqual(fetch_json("http://example.com/data.json", 5), [1, 2])

    def test_invalid_json(self):
        # AC-4
        with fake_urlopen(b"not json"):
            with self.assertRaises(ValueError):
                fetch_json("https://example.com/data.json", 5)

    def test_rejects_other_schemes(self):
        # AC-5, AC-6
        for url in ["file:///etc/passwd", "ftp://example.com/data.json"]:
            with self.subTest(url=url):
                with fake_urlopen(b"{}") as m:
                    with self.assertRaises(ValueError):
                        fetch_json(url, 5)
                m.assert_not_called()

    def test_http_error_propagates(self):
        # AC-7
        err = urllib.error.HTTPError("https://example.com/data.json", 404, "Not Found", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                fetch_json("https://example.com/data.json", 5)
        self.assertIs(ctx.exception, err)

    def test_version_kept(self):
        # 守るべき既存挙動
        import jsonfetch
        self.assertEqual(jsonfetch.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
