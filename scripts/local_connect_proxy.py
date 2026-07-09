#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import select
import socket
import socketserver
import sys
import threading
import time
from collections import Counter
from urllib.parse import urlsplit

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
CREDENTIAL_RE = re.compile(r"[:@].*(?:password|passwd|token|secret|key|gh[pousr]_|xox[baprs]-)", re.IGNORECASE)


def parse_authority(value: str) -> tuple[str, int]:
    raw = value.strip()
    if not raw:
        raise ValueError("empty authority")
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported proxy authority scheme: {parsed.scheme}")
        host = parsed.hostname
        port = parsed.port
        if not host or port is None:
            raise ValueError(f"authority requires host and port: {value!r}")
        return host, port
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0 or end + 2 > len(raw) or raw[end + 1] != ":":
            raise ValueError(f"IPv6 authority requires bracketed host and port: {value!r}")
        return raw[1:end], int(raw[end + 2 :])
    if raw.count(":") != 1:
        raise ValueError(f"authority requires exactly one host:port separator: {value!r}")
    host, port = raw.rsplit(":", 1)
    if not host or not port:
        raise ValueError(f"authority requires host and port: {value!r}")
    return host, int(port)


def sanitize_host(host: str) -> str:
    normalized = host.strip().lower().strip("[]")
    if not normalized:
        return "[redacted-empty-host]"
    if "@" in normalized or CREDENTIAL_RE.search(normalized):
        return "[redacted-credential-host]"
    if IPV4_RE.fullmatch(normalized):
        return "[redacted-ipv4]"
    if ":" in normalized:
        return "[redacted-ipv6]"
    if len(normalized) > 253:
        return "[redacted-long-host]"
    return normalized


def summarize_events(events: list[dict]) -> dict:
    methods = Counter(str(event.get("method", "unknown")).upper() for event in events)
    hosts = Counter()
    ports = Counter()
    for event in events:
        host = sanitize_host(str(event.get("host", "")))
        hosts[host] += 1
        if event.get("port") is not None:
            ports[str(event.get("port"))] += 1
    return {
        "total_events": len(events),
        "connect_count": methods.get("CONNECT", 0),
        "methods": dict(sorted(methods.items())),
        "hosts": dict(sorted(hosts.items())),
        "ports": dict(sorted(ports.items())),
    }


class ProxyState:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.lock = threading.Lock()

    def add(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)

    def snapshot(self) -> list[dict]:
        with self.lock:
            return list(self.events)


class ConnectProxyHandler(socketserver.StreamRequestHandler):
    timeout = 30

    def handle(self) -> None:
        line = self.rfile.readline(65536).decode("iso-8859-1", "replace").strip()
        if not line:
            return
        parts = line.split()
        if len(parts) < 3:
            return
        method, target, _version = parts[0].upper(), parts[1], parts[2]
        headers = {}
        while True:
            header = self.rfile.readline(65536).decode("iso-8859-1", "replace")
            if header in ("\r\n", "\n", ""):
                break
            name, _, value = header.partition(":")
            headers[name.lower()] = value.strip()
        try:
            if method == "CONNECT":
                host, port = parse_authority(target)
            else:
                parsed = urlsplit(target)
                if parsed.scheme and parsed.hostname and parsed.port:
                    host, port = parsed.hostname, parsed.port
                elif parsed.scheme and parsed.hostname:
                    host, port = parsed.hostname, 80 if parsed.scheme == "http" else 443
                else:
                    host_header = headers.get("host", "")
                    host, port = parse_authority(host_header if ":" in host_header else f"{host_header}:80")
        except Exception:
            self.wfile.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        self.server.state.add({"method": method, "host": host, "port": port, "ts": round(time.time(), 3)})
        try:
            upstream = socket.create_connection((host, port), timeout=15)
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        with upstream:
            if method == "CONNECT":
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                upstream.sendall((line + "\r\n").encode("iso-8859-1"))
                for name, value in headers.items():
                    if name.lower() == "proxy-connection":
                        continue
                    upstream.sendall(f"{name}: {value}\r\n".encode("iso-8859-1"))
                upstream.sendall(b"\r\n")
            self._tunnel(upstream)

    def _tunnel(self, upstream: socket.socket) -> None:
        sockets = [self.connection, upstream]
        end = time.time() + self.timeout
        while time.time() < end:
            readable, _, exceptional = select.select(sockets, [], sockets, 0.5)
            if exceptional:
                return
            if not readable:
                continue
            for sock in readable:
                try:
                    data = sock.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                target = upstream if sock is self.connection else self.connection
                try:
                    target.sendall(data)
                except OSError:
                    return


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, state: ProxyState):
        super().__init__(server_address, handler_class)
        self.state = state


def run_proxy(args) -> int:
    state = ProxyState()
    server = ThreadingTCPServer((args.listen_host, args.listen_port), ConnectProxyHandler, state)
    server.timeout = 0.5
    try:
        print(json.dumps({"listening": {"host": args.listen_host, "port": server.server_address[1]}}), flush=True)
        deadline = time.time() + args.max_seconds if args.max_seconds else None
        while deadline is None or time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
        summary = summarize_events(state.snapshot())
        output = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        if args.summary_json:
            with open(args.summary_json, "w", encoding="utf-8") as fh:
                fh.write(output)
        else:
            sys.stderr.write(output)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=18080)
    parser.add_argument("--summary-json")
    parser.add_argument("--max-seconds", type=int, default=120)
    return run_proxy(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
