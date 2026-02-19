"""Embedded file bridge server — runs as a daemon thread inside the companion."""

import socket
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _safe_path(rel_path: str) -> Path | None:
    try:
        full = (PROJECT_ROOT / rel_path).resolve()
        if not str(full).startswith(str(PROJECT_ROOT)):
            return None
        return full
    except (ValueError, OSError):
        return None


def _handle_client(conn, addr):
    try:
        conn.settimeout(30)
        data = b""
        while b"\n" not in data and len(data) < 4096:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk

        if not data:
            return

        command = data.decode("utf-8", errors="replace").strip()
        print(f"[bridge {time.strftime('%H:%M:%S')}] {addr}: {command}")

        if not command:
            conn.sendall(b"ERROR: empty command\n")
            return

        if command == "ping":
            conn.sendall(b"pong\n")
            return

        if command.startswith("list "):
            rel_dir = command[5:].strip()
            path = _safe_path(rel_dir)
            if path is None or not path.is_dir():
                conn.sendall(f"ERROR: directory not found: {rel_dir}\n".encode())
                return
            files = sorted(p.name for p in path.iterdir() if p.is_file())
            conn.sendall(("\n".join(files) + "\n").encode())
            return

        if command.startswith("read "):
            rel_file = command[5:].strip()
            path = _safe_path(rel_file)
            if path is None or not path.is_file():
                conn.sendall(f"ERROR: file not found: {rel_file}\n".encode())
                return
            size = path.stat().st_size
            conn.sendall(f"SIZE {size}\n".encode())
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    conn.sendall(chunk)
            return

        if command.startswith("readtext "):
            rel_file = command[9:].strip()
            path = _safe_path(rel_file)
            if path is None or not path.is_file():
                conn.sendall(f"ERROR: file not found: {rel_file}\n".encode())
                return
            text = path.read_text(encoding="utf-8", errors="replace")
            conn.sendall(text.encode("utf-8"))
            return

        conn.sendall(b"ERROR: unknown command\n")

    except socket.timeout:
        pass
    except Exception as e:
        try:
            conn.sendall(f"ERROR: {e}\n".encode())
        except Exception:
            pass
    finally:
        conn.close()


def _accept_loop(server: socket.socket):
    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_handle_client, args=(conn, addr), daemon=True).start()


def start_bridge(host: str = "0.0.0.0", port: int = 9100) -> socket.socket | None:
    """Start the file bridge TCP server in a daemon thread. Returns the server socket."""
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.settimeout(1.0)
        server.bind((host, port))
        server.listen(5)
    except OSError as e:
        print(f"[bridge] Could not start on {host}:{port}: {e}")
        return None

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        local_ip = "unknown"

    print(f"[bridge] Serving {PROJECT_ROOT} on {host}:{port} (IP: {local_ip})")

    thread = threading.Thread(target=_accept_loop, args=(server,), daemon=True)
    thread.start()
    return server
