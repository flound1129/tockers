#!/home/adam/tft/.venv/bin/python
"""Fetch debug crops from the Windows file bridge and save locally."""
import argparse
import socket
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "debug_crops"
DEFAULT_HOST = "10.0.0.190"
DEFAULT_PORT = 9100


def bridge_cmd(host: str, port: int, command: str, timeout: int = 10) -> bytes:
    """Send a command to the file bridge and return raw response."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall((command + "\n").encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def fetch_text(host: str, port: int, path: str) -> str:
    return bridge_cmd(host, port, f"readtext {path}").decode("utf-8", errors="replace")


def fetch_binary(host: str, port: int, path: str) -> bytes:
    raw = bridge_cmd(host, port, f"read {path}")
    # Response starts with "SIZE <n>\n" followed by binary data
    header_end = raw.index(b"\n") + 1
    return raw[header_end:]


def list_dir(host: str, port: int, path: str) -> list[str]:
    text = bridge_cmd(host, port, f"list {path}").decode().strip()
    if text.startswith("ERROR"):
        return []
    return [line for line in text.split("\n") if line]


def main():
    parser = argparse.ArgumentParser(description="Fetch debug crops from Windows file bridge")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bridge host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bridge port (default: {DEFAULT_PORT})")
    parser.add_argument("--reports-only", action="store_true", help="Only fetch .txt reports, skip images")
    args = parser.parse_args()

    # Ping first
    try:
        resp = bridge_cmd(args.host, args.port, "ping", timeout=5)
        if b"pong" not in resp:
            print(f"Unexpected ping response: {resp}")
            sys.exit(1)
    except Exception as e:
        print(f"Cannot reach bridge at {args.host}:{args.port}: {e}")
        sys.exit(1)

    print(f"Connected to bridge at {args.host}:{args.port}")

    files = list_dir(args.host, args.port, "debug_crops")
    if not files:
        print("No files in debug_crops/")
        sys.exit(0)

    OUT_DIR.mkdir(exist_ok=True)
    print(f"Found {len(files)} files in debug_crops/")

    # Fetch text reports first
    for f in sorted(files):
        if f.endswith(".txt"):
            text = fetch_text(args.host, args.port, f"debug_crops/{f}")
            out_path = OUT_DIR / f
            out_path.write_text(text, encoding="utf-8")
            print(f"\n=== {f} ===")
            print(text)

    if args.reports_only:
        return

    # Fetch images
    img_files = [f for f in files if f.endswith(".png")]
    for i, f in enumerate(sorted(img_files)):
        data = fetch_binary(args.host, args.port, f"debug_crops/{f}")
        out_path = OUT_DIR / f
        out_path.write_bytes(data)
        print(f"  [{i+1}/{len(img_files)}] {f} ({len(data):,} bytes)")

    print(f"\nSaved {len(img_files)} images to {OUT_DIR}/")


if __name__ == "__main__":
    main()
