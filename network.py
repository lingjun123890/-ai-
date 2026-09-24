import socket
import threading
import pickle
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Optional, List


DEFAULT_PORT = 9999
BUFFER_SIZE = 65536
RECV_QUEUE_MAX = 128
PING_INTERVAL = 2.0

_PUBLIC_IP_SERVICES = [
    ("https://api.ipify.org", 8),
    ("https://icanhazip.com", 8),
    ("https://ifconfig.me/ip", 8),
]


def _fetch_public_ip() -> Optional[str]:
    for url, timeout in _PUBLIC_IP_SERVICES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("ascii", errors="ignore").strip()
                if raw and _is_valid_ipv4(raw):
                    return raw
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None


def _is_valid_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        n = int(p)
        if n < 0 or n > 255:
            return False
    return True


@dataclass
class Message:
    type: str
    payload: Any = None


class ConnectionError(Exception):
    pass


class Network:
    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._server_sock: Optional[socket.socket] = None
        self._recv_queue: List[Message] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._peer_addr: Optional[tuple] = None
        self._ping_thread: Optional[threading.Thread] = None
        self._last_rtt_ms: float = -1.0
        self._ping_lock = threading.Lock()
        self._pending_ping_id: Optional[int] = None
        self._pending_ping_ts: float = 0.0
        self._ping_counter: int = 0

        self._peer_socks: List[socket.socket] = []
        self._peer_recv_threads: List[threading.Thread] = []
        self._peer_running: List[bool] = []
        self._is_host_multi: bool = False
        self._peer_recv_queues: List[List[Message]] = []
        self._peer_locks: List[threading.Lock] = []
        self._accept_thread: Optional[threading.Thread] = None
        self._accept_running: bool = False
        self._max_accept: int = 0
        self._new_peer_event = threading.Event()

    @property
    def last_rtt_ms(self) -> float:
        with self._ping_lock:
            return self._last_rtt_ms

    # ───── Server ─────
    def host(self, port: int = DEFAULT_PORT) -> str:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("0.0.0.0", port))
        real_port = self._server_sock.getsockname()[1]
        self._server_sock.listen(1)

        try:
            hostname = socket.gethostname()
            lan_ip = socket.gethostbyname(hostname)
            if lan_ip.startswith("127."):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    lan_ip = s.getsockname()[0]
                except OSError:
                    lan_ip = "127.0.0.1"
                finally:
                    s.close()
        except OSError:
            lan_ip = "127.0.0.1"

        self._lan_ip = lan_ip
        self._port = real_port

        pub_fetch: List[Optional[str]] = [None]
        def _fetch_bg() -> None:
            pub_fetch[0] = _fetch_public_ip()
        t = threading.Thread(target=_fetch_bg, daemon=True)
        t.start()
        t.join(timeout=6.0)
        self._public_ip = pub_fetch[0]

        return f"{lan_ip}:{real_port}"

    @property
    def lan_ip(self) -> str:
        return getattr(self, "_lan_ip", "127.0.0.1")

    @property
    def public_ip(self) -> Optional[str]:
        return getattr(self, "_public_ip", None)

    @property
    def port(self) -> int:
        return getattr(self, "_port", DEFAULT_PORT)

    def accept(self, timeout: float = 60.0) -> None:
        self._server_sock.settimeout(timeout)
        try:
            conn, addr = self._server_sock.accept()
        except socket.timeout:
            raise ConnectionError("等待对手连接超时")
        self._sock = conn
        self._peer_addr = addr
        self._server_sock.close()
        self._server_sock = None
        self._sock.settimeout(None)
        self._start_recv_loop()
        self._start_ping_loop()

    def accept_many(self, count: int, per_client_timeout: float = 300.0) -> int:
        self._is_host_multi = True
        self._server_sock.settimeout(None)
        self._peer_socks = []
        self._peer_recv_queues = []
        self._peer_locks = []
        self._peer_running = []

        for i in range(count):
            try:
                conn, addr = self._server_sock.accept()
                print(f"[NET] accepted peer {i+1}/{count} from {addr}")
                conn.settimeout(None)
                self._peer_socks.append(conn)
                self._peer_recv_queues.append([])
                self._peer_locks.append(threading.Lock())
                self._peer_running.append(True)
            except OSError as e:
                print(f"[NET] accept_many error: {e}")
                break

        self._server_sock.close()
        self._server_sock = None

        for i, conn in enumerate(self._peer_socks):
            t = threading.Thread(target=self._peer_recv_loop, args=(i,), daemon=True)
            self._peer_recv_threads.append(t)
            t.start()

        self._running = True
        self._start_ping_loop()
        return len(self._peer_socks)

    def start_accept_loop(self, max_players: int = 4) -> None:
        self._is_host_multi = True
        self._max_accept = max_players
        self._peer_socks = []
        self._peer_recv_queues = []
        self._peer_locks = []
        self._peer_running = []
        self._accept_running = True
        self._running = True

        def _accept_loop() -> None:
            while self._accept_running and len(self._peer_socks) < self._max_accept:
                try:
                    self._server_sock.settimeout(1.0)
                    conn, addr = self._server_sock.accept()
                    conn.settimeout(None)
                    self._peer_socks.append(conn)
                    self._peer_recv_queues.append([])
                    self._peer_locks.append(threading.Lock())
                    self._peer_running.append(True)
                    print(f"[NET] accepted peer {len(self._peer_socks)} from {addr}")

                    idx = len(self._peer_socks) - 1
                    t = threading.Thread(target=self._peer_recv_loop, args=(idx,), daemon=True)
                    self._peer_recv_threads.append(t)
                    t.start()

                    self._new_peer_event.set()
                    self._new_peer_event.clear()
                except socket.timeout:
                    continue
                except OSError:
                    break

            self._start_ping_loop()

        self._accept_thread = threading.Thread(target=_accept_loop, daemon=True)
        self._accept_thread.start()

    def stop_accept_loop(self) -> None:
        self._accept_running = False
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)
            self._accept_thread = None

    def close_server_socket(self) -> None:
        self._accept_running = False
        ss = self._server_sock
        self._server_sock = None
        if ss is not None:
            try:
                ss.close()
            except OSError:
                pass

    def wait_for_new_peer(self, timeout: float = 1.0) -> bool:
        return self._new_peer_event.wait(timeout=timeout)

    @property
    def new_peer_available(self) -> bool:
        return self._new_peer_event.is_set()

    def _peer_recv_loop(self, peer_idx: int) -> None:
        sock = self._peer_socks[peer_idx]
        try:
            while self._peer_running[peer_idx]:
                length_buf = self._sock_recv_exact_from(sock, 4)
                if not length_buf:
                    break
                length = int.from_bytes(length_buf, "big")
                data = self._sock_recv_exact_from(sock, length)
                if not data:
                    break
                msg = pickle.loads(data)
                if msg.type == "PING":
                    try:
                        self._send_raw_to(peer_idx, Message("PONG", msg.payload))
                    except ConnectionError:
                        break
                    continue
                if msg.type == "PONG":
                    self._handle_pong(msg)
                    continue
                with self._peer_locks[peer_idx]:
                    if len(self._peer_recv_queues[peer_idx]) < RECV_QUEUE_MAX:
                        self._peer_recv_queues[peer_idx].append(msg)
        except (ConnectionResetError, OSError, EOFError, pickle.UnpicklingError) as e:
            print(f"[NET] peer_{peer_idx} recv error: {type(e).__name__}: {e}")
        finally:
            self._peer_running[peer_idx] = False

    def _sock_recv_exact_from(self, sock: socket.socket, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _send_raw_to(self, peer_idx: int, msg: Message) -> None:
        if peer_idx < 0 or peer_idx >= len(self._peer_socks):
            raise ConnectionError(f"peer_idx {peer_idx} out of range")
        sock = self._peer_socks[peer_idx]
        data = pickle.dumps(msg)
        length = len(data).to_bytes(4, "big")
        try:
            sock.sendall(length + data)
        except OSError as e:
            raise ConnectionError(f"send to peer_{peer_idx} failed: {e}")

    def send_to(self, peer_idx: int, msg: Message) -> None:
        self._send_raw_to(peer_idx, msg)

    def broadcast(self, msg: Message, except_idx: int = -1) -> None:
        for i in range(len(self._peer_socks)):
            if i == except_idx:
                continue
            if not self._peer_running[i]:
                continue
            try:
                self._send_raw_to(i, msg)
            except ConnectionError:
                pass

    def poll_peer(self, peer_idx: int) -> List[Message]:
        if peer_idx < 0 or peer_idx >= len(self._peer_socks):
            return []
        with self._peer_locks[peer_idx]:
            msgs = list(self._peer_recv_queues[peer_idx])
            self._peer_recv_queues[peer_idx].clear()
        return msgs

    @property
    def peer_count(self) -> int:
        return len(self._peer_socks)

    def is_peer_alive(self, peer_idx: int) -> bool:
        if peer_idx < 0 or peer_idx >= len(self._peer_running):
            return False
        return self._peer_running[peer_idx]

    # ───── Client ─────
    def connect(self, host_ip: str, port: int = DEFAULT_PORT) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(15.0)
        try:
            self._sock.connect((host_ip, port))
        except socket.timeout:
            raise ConnectionError(f"连接 {host_ip}:{port} 超时（15秒）。检查地址是否正确、内网穿透是否启动")
        except OSError as e:
            if getattr(e, "errno", None) == 110 or "timed out" in str(e).lower():
                raise ConnectionError(f"连接 {host_ip}:{port} 超时。检查内网穿透是否正常转发")
            if getattr(e, "errno", None) == 111 or "refused" in str(e).lower():
                raise ConnectionError(f"连接 {host_ip}:{port} 被拒绝。目标端口没有服务在监听")
            raise ConnectionError(f"无法连接: {e}")
        self._peer_addr = (host_ip, port)
        self._sock.settimeout(None)
        self._start_recv_loop()
        self._start_ping_loop()

    # ───── Relay 模式（双方连中继服务器，绕过 NAT） ─────
    def relay_connect(self, relay_ip: str, relay_port: int, room_id: str) -> None:
        """连接到中继服务器。双方填同一个中继地址和同一个房间号即可互通。"""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(15.0)
        try:
            self._sock.connect((relay_ip, relay_port))
        except socket.timeout:
            raise ConnectionError(f"中继服务器 {relay_ip}:{relay_port} 超时")
        except OSError as e:
            raise ConnectionError(f"无法连接中继: {e}")

        handshake = f"RELAY_JOIN {room_id[:64]}".encode("utf-8")
        self._sock.sendall(len(handshake).to_bytes(4, "big") + handshake)

        resp = self._recv_relay_msg(30.0)
        if resp == b"WAITING":
            resp2 = self._recv_relay_msg(300.0)
            if resp2 != b"RELAY_PAIRED":
                raise ConnectionError(f"中继返回异常: {resp2!r}")
        elif resp == b"RELAY_PAIRED":
            pass
        elif resp == b"ROOM_FULL":
            raise ConnectionError("房间已满，请换一个房间号")
        else:
            raise ConnectionError(f"中继返回未知响应: {resp!r}")

        self._peer_addr = (f"relay:{relay_ip}", relay_port)
        self._sock.settimeout(None)
        self._start_recv_loop()
        self._start_ping_loop()

    def _recv_relay_msg(self, timeout: float) -> bytes:
        self._sock.settimeout(timeout)
        try:
            length_buf = b""
            while len(length_buf) < 4:
                chunk = self._sock.recv(4 - len(length_buf))
                if not chunk:
                    raise ConnectionError("中继服务器断开")
                length_buf += chunk
            length = int.from_bytes(length_buf, "big")
            data = b""
            while len(data) < length:
                chunk = self._sock.recv(length - len(data))
                if not chunk:
                    raise ConnectionError("中继服务器断开")
                data += chunk
            return data
        except socket.timeout:
            raise ConnectionError("等待中继服务器响应超时")

    # ───── Send / Recv ─────
    def send(self, msg: Message) -> None:
        if self._sock is None:
            raise ConnectionError("未连接")
        data = pickle.dumps(msg)
        length = len(data).to_bytes(4, "big")
        self._sock.sendall(length + data)

    def poll(self) -> Optional[Message]:
        with self._lock:
            if self._recv_queue:
                return self._recv_queue.pop(0)
        return None

    def recv_all(self) -> List[Message]:
        with self._lock:
            msgs = list(self._recv_queue)
            self._recv_queue.clear()
        return msgs

    # ───── Ping ─────
    def _start_ping_loop(self) -> None:
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()

    def _ping_loop(self) -> None:
        while self._running:
            try:
                time.sleep(PING_INTERVAL)
            except Exception:
                break
            if not self._running:
                break
            if self._sock is None:
                continue
            self._ping_counter += 1
            ping_id = self._ping_counter
            with self._ping_lock:
                self._pending_ping_id = ping_id
                self._pending_ping_ts = time.monotonic()
            try:
                self.send(Message("PING", ping_id))
            except ConnectionError:
                break

    def _handle_ping(self, msg: Message) -> None:
        try:
            self.send(Message("PONG", msg.payload))
        except ConnectionError:
            pass

    def _handle_pong(self, msg: Message) -> None:
        rtt = -1.0
        with self._ping_lock:
            if self._pending_ping_id is not None and msg.payload == self._pending_ping_id:
                now = time.monotonic()
                rtt = (now - self._pending_ping_ts) * 1000.0
                self._last_rtt_ms = rtt
                self._pending_ping_id = None
        if rtt < 0:
            pass

    # ───── 内部 ─────
    def _start_recv_loop(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self) -> None:
        try:
            while self._running:
                length_buf = self._sock_recv_exact(4)
                if not length_buf:
                    break
                length = int.from_bytes(length_buf, "big")
                data = self._sock_recv_exact(length)
                if not data:
                    break
                msg = pickle.loads(data)
                if msg.type == "PING":
                    self._handle_ping(msg)
                    continue
                if msg.type == "PONG":
                    self._handle_pong(msg)
                    continue
                with self._lock:
                    if len(self._recv_queue) < RECV_QUEUE_MAX:
                        self._recv_queue.append(msg)
        except (ConnectionResetError, OSError, EOFError, pickle.UnpicklingError) as e:
            print(f"[NET] recv_loop error: {type(e).__name__}: {e}")
        finally:
            self._running = False
            self._close()

    def _sock_recv_exact(self, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            if self._sock is None:
                return None
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _close(self) -> None:
        with self._lock:
            s = self._sock
            self._sock = None
            ss = self._server_sock
            self._server_sock = None
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
        if ss is not None:
            try:
                ss.close()
            except OSError:
                pass

    def close(self) -> None:
        self._running = False
        self._accept_running = False
        self._close()

    @property
    def is_alive(self) -> bool:
        return self._running and self._sock is not None