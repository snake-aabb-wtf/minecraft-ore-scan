import socket
import struct
import time


class RconClient:
    def __init__(self, host, port, password, timeout=120):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.sock = None
        self._connect()

    def _connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self._send_packet(1, 3, self.password)
        request_id, _, _ = self._recv_packet()
        if request_id == -1:
            self.close()
            raise RuntimeError("RCON 认证失败")

    def _check_socket(self):
        if self.sock is None:
            raise ConnectionError("RCON 连接已关闭")

    def _send_packet(self, request_id, packet_type, body):
        self._check_socket()
        payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\0\0"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)

    def _recv_packet(self):
        self._check_socket()
        try:
            size_data = self._recv_exact(4)
            size = struct.unpack("<i", size_data)[0]
            if size <= 0 or size > 4096 * 4:
                raise ConnectionError(f"Invalid RCON packet size: {size}")
            data = self._recv_exact(size)
            request_id, packet_type = struct.unpack("<ii", data[:8])
            return request_id, packet_type, data[8:-2].decode("utf-8", "replace")
        except socket.timeout:
            raise
        except (ConnectionError, OSError):
            raise

    def _recv_exact(self, size):
        self._check_socket()
        data = bytearray()
        while len(data) < size:
            part = self.sock.recv(size - len(data))
            if not part:
                raise ConnectionError("RCON 连接已关闭")
            data.extend(part)
        return bytes(data)

    def command(self, cmd, retries=2):
        last_exc = None
        for attempt in range(retries + 1):
            try:
                self._send_packet(2, 2, cmd)
                request_id, _, body = self._recv_packet()
                if request_id != 2:
                    raise RuntimeError(f"RCON 响应异常: request_id={request_id}")
                return body
            except socket.timeout as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(2)
                    try:
                        self._connect()
                    except:
                        pass
            except (ConnectionError, OSError, RuntimeError) as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(3)
                    try:
                        self._connect()
                    except:
                        pass
        raise last_exc

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
