#!/usr/bin/env python3
"""
File Bridge Server — Run on your Windows PC.

Listens on a TCP port so a remote machine (e.g. Claude's dev environment)
can read files from the project directory over the network.

Usage:
    python tools/file_bridge.py [--port 9100] [--host 0.0.0.0]

Then from the remote machine:
    echo "list debug_crops" | nc <your-windows-ip> 9100
    echo "read debug_crops/shop_slot_0.png" | nc <your-windows-ip> 9100 > file.png

Protocol:
    - Client sends a single line command
    - Commands:
        ping                → "pong"
        list <dir>          → newline-separated file list
        read <path>         → "SIZE <bytes>\n" followed by raw binary
        readtext <path>     → file contents as UTF-8 text
    - Paths are relative to the project root

Security:
    - No authentication — only run on trusted networks.
    - Paths are restricted to the project root (no ../ escapes).
"""

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def safe_path(rel_path: str) -> Path | None:
    """Resolve a relative path and ensure it's within the project root."""
    try:
        full = (PROJECT_ROOT / rel_path).resolve()
        if not str(full).startswith(str(PROJECT_ROOT)):
            return None
        return full
    except (ValueError, OSError):
        return None


def handle_client(conn, addr):
    print(f"[{time.strftime('%H:%M:%S')}] Connection from {addr}")
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
        print(f"[{time.strftime('%H:%M:%S')}] Command: {command}")

        if not command:
            conn.sendall(b"ERROR: empty command\n")
            return

        if command == "ping":
            conn.sendall(b"pong\n")
            return

        if command.startswith("list "):
            rel_dir = command[5:].strip()
            path = safe_path(rel_dir)
            if path is None or not path.is_dir():
                conn.sendall(f"ERROR: directory not found: {rel_dir}\n".encode())
                return
            files = sorted(p.name for p in path.iterdir() if p.is_file())
            conn.sendall(("\n".join(files) + "\n").encode())
            return

        if command.startswith("read "):
            rel_file = command[5:].strip()
            path = safe_path(rel_file)
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
            path = safe_path(rel_file)
            if path is None or not path.is_file():
                conn.sendall(f"ERROR: file not found: {rel_file}\n".encode())
                return
            text = path.read_text(encoding="utf-8", errors="replace")
            conn.sendall(text.encode("utf-8"))
            return

        conn.sendall(b"ERROR: unknown command. Use: ping, list <dir>, read <path>, readtext <path>\n")

    except socket.timeout:
        print(f"[{time.strftime('%H:%M:%S')}] Client {addr} timed out")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error handling {addr}: {e}")
        try:
            conn.sendall(f"ERROR: {e}\n".encode())
        except Exception:
            pass
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="File Bridge Server")
    parser.add_argument("--port", type=int, default=9100,
                        help="TCP port to listen on (default: 9100)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)  # Allow Ctrl+C to interrupt on Windows
    server.bind((args.host, args.port))
    server.listen(5)

    # Show local IPs for convenience
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        local_ip = "unknown"

    print(f"File Bridge serving: {PROJECT_ROOT}")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Local IP: {local_ip}")
    print(f"\nFrom remote machine:")
    print(f'  echo "ping" | nc {local_ip} {args.port}')
    print(f'  echo "list debug_crops" | nc {local_ip} {args.port}')
    print(f'  echo "read debug_crops/shop_slot_0.png" | nc {local_ip} {args.port} > file.png')
    print(f"\nPress Ctrl+C to stop.\n")

    try:
        while True:
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(target=handle_client, args=(conn, addr),
                                     daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.close()


if __name__ == "__main__":
    main()
