"""Validate beta bind configuration and TLS material before containers start."""

import ipaddress
import re
import ssl
import sys
import time
from pathlib import Path


def config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Linha inválida em beta.env")
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError(f"Configuração repetida: {key}")
        values[key] = value
    return values


def private_bind(value: str, label: str) -> None:
    address = ipaddress.ip_address(value)
    if address.version != 4 or address.is_unspecified or address.is_global or address.is_multicast:
        raise ValueError(f"{label} deve ser IPv4 explícito de loopback ou rede privada")


def validate(directory: Path) -> None:
    values = config(directory / "beta.env")
    project = values.get("SCRIBRIEF_PROJECT_NAME", "scribrief-beta")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise ValueError("SCRIBRIEF_PROJECT_NAME inválido")
    private_bind(values.get("PUBLIC_BIND_IP", "127.0.0.1"), "PUBLIC_BIND_IP")
    private_bind(values.get("ADMIN_BIND_IP", "127.0.0.1"), "ADMIN_BIND_IP")
    hostnames = {
        "PUBLIC_HOSTNAME": values.get("PUBLIC_HOSTNAME", "").strip(),
        "ADMIN_HOSTNAME": values.get("ADMIN_HOSTNAME", "127.0.0.1").strip(),
    }
    for label, hostname in hostnames.items():
        if not hostname or any(char in hostname for char in " /\\:@"):
            raise ValueError(f"{label} inválido")
    for name, default in (("PUBLIC_HTTPS_PORT", "18574"), ("ADMIN_HTTPS_PORT", "18575")):
        port = int(values.get(name, default))
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} fora do intervalo TCP")
    if values.get("PUBLIC_BIND_IP", "127.0.0.1") == values.get("ADMIN_BIND_IP", "127.0.0.1") and values.get("PUBLIC_HTTPS_PORT", "18574") == values.get("ADMIN_HTTPS_PORT", "18575"):
        raise ValueError("Portas pública e administrativa não podem coincidir no mesmo IP")

    cert = directory / "certs" / "localhost.crt"
    key = directory / "certs" / "localhost.key"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))  # also verifies that the key matches
    decoded = ssl._ssl._test_decode_cert(str(cert))
    if ssl.cert_time_to_seconds(decoded["notAfter"]) <= time.time():
        raise ValueError("Certificado TLS expirado")
    names = {(kind, value.lower()) for kind, value in decoded.get("subjectAltName", ())}
    for label, hostname in hostnames.items():
        try:
            expected = ("IP Address", str(ipaddress.ip_address(hostname)))
        except ValueError:
            expected = ("DNS", hostname.lower())
        if expected not in names:
            raise ValueError(f"Certificado TLS não contém {label} no SAN")


if __name__ == "__main__":
    try:
        validate(Path(sys.argv[1]))
    except (OSError, ValueError, ssl.SSLError, ssl.CertificateError) as exc:
        print(f"Preflight TLS/configuração falhou: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print("Preflight TLS/configuração aprovado (cadeia de confiança deve ser validada no cliente).")
