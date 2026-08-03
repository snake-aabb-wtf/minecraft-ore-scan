"""app.rcon 的单元测试：mock socket 的认证、命令收发、超时重连与关闭。"""
import socket
import struct
import unittest
from unittest.mock import Mock, patch

from app.rcon import RconClient


def make_packet(request_id, packet_type, body):
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\0\0"
    return struct.pack("<i", len(payload)) + payload


class FakeSocket:
    """返回预置 packet 列表的假 socket；耗尽后 recv 返回 b''（连接关闭）。

    timeout_when_empty=True 时耗尽后抛 socket.timeout（模拟超时断连）。
    """

    def __init__(self, packets, timeout_when_empty=False):
        self._packets = list(packets)
        self._buffer = b""
        self.sent = []
        self.timeout_when_empty = timeout_when_empty

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, n):
        if not self._buffer:
            if not self._packets:
                if self.timeout_when_empty:
                    raise socket.timeout("timed out")
                return b""
            self._buffer = self._packets.pop(0)
        chunk = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return chunk

    def settimeout(self, timeout):
        pass

    def close(self):
        pass


def _auth_packet(ok=True):
    return make_packet(1 if ok else -1, 3, "")


class RconAuthenticationTest(unittest.TestCase):
    def test_authentication_success(self):
        sock = FakeSocket([_auth_packet()])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            client = RconClient("127.0.0.1", 25575, "secret")
        self.assertIsNotNone(client.sock)
        client.close()

    def test_authentication_failure_raises(self):
        sock = FakeSocket([_auth_packet(ok=False)])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            with self.assertRaisesRegex(RuntimeError, "RCON 认证失败"):
                RconClient("127.0.0.1", 25575, "secret")

    def test_connect_sends_auth_packet(self):
        sock = FakeSocket([_auth_packet()])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            client = RconClient("127.0.0.1", 25575, "secret")
        sent = sock.sent[0]
        self.assertEqual(sent[:4], struct.pack("<i", len(sent) - 4))
        self.assertEqual(struct.unpack("<ii", sent[4:12]), (1, 3))
        client.close()


class RconCommandTest(unittest.TestCase):
    def test_command_roundtrip(self):
        sock = FakeSocket([_auth_packet(), make_packet(2, 2, "players: 0")])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            client = RconClient("127.0.0.1", 25575, "secret")
        body = client.command("list", retries=0)
        self.assertEqual(body, "players: 0")
        client.close()

    def test_command_uses_request_id_two(self):
        sock = FakeSocket([_auth_packet(), make_packet(2, 2, "ok")])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            client = RconClient("127.0.0.1", 25575, "secret")
        client.command("list", retries=0)
        sent = sock.sent[1]
        self.assertEqual(struct.unpack("<ii", sent[4:12]), (2, 2))
        client.close()

    def test_request_id_mismatch_raises(self):
        # 每次连接都返回 request_id!=2 的响应；重试用尽后抛出 RuntimeError
        sock1 = FakeSocket([_auth_packet(), make_packet(99, 2, "bad")])
        sock2 = FakeSocket([_auth_packet(), make_packet(99, 2, "bad")])
        with (
            patch("app.rcon.socket.create_connection", side_effect=[sock1, sock2]),
            patch("app.rcon.time.sleep"),
        ):
            client = RconClient("127.0.0.1", 25575, "secret")
            with self.assertRaises(RuntimeError):
                client.command("list", retries=1)
        client.close()

    def test_timeout_reconnects_and_succeeds(self):
        # 第一次连接认证正常，但 command 阶段 recv 抛 timeout；重连后成功
        bad_sock = FakeSocket([_auth_packet()], timeout_when_empty=True)
        good_sock = FakeSocket([_auth_packet(), make_packet(2, 2, "players: 1")])
        with (
            patch("app.rcon.socket.create_connection", side_effect=[bad_sock, good_sock]),
            patch("app.rcon.time.sleep"),
        ):
            client = RconClient("127.0.0.1", 25575, "secret")
            body = client.command("list", retries=2)
        self.assertEqual(body, "players: 1")
        self.assertIsNotNone(client.sock)
        client.close()


class RconCloseTest(unittest.TestCase):
    def test_close_is_idempotent(self):
        sock = FakeSocket([_auth_packet()])
        with patch("app.rcon.socket.create_connection", return_value=sock):
            client = RconClient("127.0.0.1", 25575, "secret")
        client.close()
        client.close()
        self.assertIsNone(client.sock)

    def test_command_after_close_raises(self):
        client = RconClient.__new__(RconClient)
        client.sock = None
        client.host = "127.0.0.1"
        client.port = 25575
        client.password = "x"
        client.timeout = 5
        with self.assertRaises(ConnectionError):
            client.command("list", retries=0)


if __name__ == "__main__":
    unittest.main()
