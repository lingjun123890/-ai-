"""
极简 TCP 中继服务器
部署到有公网 IP 的机器上，双方都连到这里就能互通（内网穿透零配置）。

启动:  python -m game.relay --host 0.0.0.0 --port 9998
"""
import argparse
import socket
import threading
import time
from typing import Optional, Dict, Tuple


DEFAULT_RELAY_PORT = 9998


class RelayServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_RELAY_PORT) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.rooms: Dict[str, list] = {}
        self.rooms_lock = threading.Lock()
        self._stop = False
        self._stats = {"total_msgs": 0, "total_bytes": 0, "start": time.time()}
        self._stats_lock = threading.Lock()

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(64)
        print(f"[Relay] Listening on {self.host}:{self.port}")

        try:
            while not self._stop:
                self.sock.settimeout(1.0)
                try:
                    conn, addr = self.sock.accept()
                except socket.timeout:
                    continue
                t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("\n[Relay] Shutting down...")
        finally:
            self._stop = True
            if self.sock:
                self.sock.close()

    def _handle_client(self, conn: socket.socket, addr: Tuple) -> None:
        room_id = None
        peer_conn: Optional[socket.socket] = None
        try:
            conn.settimeout(15.0)
            length_buf = self._recv_exact(conn, 4)
            if not length_buf:
                return
            length = int.from_bytes(length_buf, "big")
            data = self._recv_exact(conn, length)
            if not data:
                return
            handshake = data.decode("utf-8", errors="replace")
            if not handshake.startswith("RELAY_JOIN "):
                return
            room_id = handshake[len("RELAY_JOIN "):].strip()[:64]
            if not room_id:
                return

            conn.settimeout(None)

            with self.rooms_lock:
                if room_id not in self.rooms:
                    self.rooms[room_id] = [conn]
                    side = "A"
                    peer_conn = None
                elif len(self.rooms[room_id]) == 1:
                    self.rooms[room_id].append(conn)
                    side = "B"
                    peer_conn = self.rooms[room_id][0]
                else:
                    conn.sendall(self._pack(b"ROOM_FULL"))
                    return

            print(f"[Relay] {addr[0]} joined room '{room_id}' as {side}")

            if peer_conn is not None:
                try:
                    peer_conn.sendall(self._pack(b"RELAY_PAIRED"))
                except OSError:
                    pass
                try:
                    conn.sendall(self._pack(b"RELAY_PAIRED"))
                except OSError:
                    pass
                self._relay_loop(conn, peer_conn, room_id)
            else:
                conn.sendall(self._pack(b"WAITING"))
                self._wait_loop(conn, room_id)

        except Exception as e:
            print(f"[Relay] Client {addr[0]} error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass
            if room_id:
                with self.rooms_lock:
                    members = self.rooms.get(room_id, [])
                    if conn in members:
                        members.remove(conn)
                    if len(members) == 0:
                        self.rooms.pop(room_id, None)
                        print(f"[Relay] Room '{room_id}' empty")

    def _wait_loop(self, conn: socket.socket, room_id: str) -> None:
        length_buf = self._recv_exact(conn, 4)
        if not length_buf:
            return
        length = int.from_bytes(length_buf, "big")
        self._recv_exact(conn, length)

    def _relay_loop(self, a: socket.socket, b: socket.socket, room_id: str) -> None:
        def _pipe(src: socket.socket, dst: socket.socket) -> None:
            try:
                while True:
                    length_buf = self._recv_exact(src, 4)
                    if not length_buf:
                        break
                    length = int.from_bytes(length_buf, "big")
                    data = self._recv_exact(src, length)
                    if not data:
                        break
                    with self._stats_lock:
                        self._stats["total_msgs"] += 1
                        self._stats["total_bytes"] += length + 4
                    dst.sendall(length_buf + data)
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass

        t1 = threading.Thread(target=_pipe, args=(a, b), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(b, a), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        print(f"[Relay] Room '{room_id}' link closed")

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _pack(data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + data


def main() -> None:
    parser = argparse.ArgumentParser(description="回合计牌游戏 - 中继服务器")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_RELAY_PORT, help="监听端口 (默认 9998)")
    args = parser.parse_args()

    print(f"[Relay] Starting relay server on {args.host}:{args.port}")
    RelayServer(args.host, args.port).start()


if __name__ == "__main__":
    main()