"""Installer-only TLS volume bootstrap; run as root before frontend startup."""

import argparse
import os
from pathlib import Path

from .tls_service import TLS_ROOT, generate_self_signed, hostnames, install_pair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--certificate")
    parser.add_argument("--private-key")
    parser.add_argument("--bundle")
    parser.add_argument("--preserve-existing", action="store_true")
    args = parser.parse_args()
    if bool(args.certificate) != bool(args.private_key):
        parser.error("Informe certificado e chave juntos.")
    if args.bundle and args.certificate:
        parser.error("Use bundle ou certificado/chave separados.")
    root = TLS_ROOT
    target = root / "current.pem"
    if target.exists() and (not (args.certificate or args.bundle) or args.preserve_existing):
        print("Certificado TLS existente preservado.")
        return
    if args.bundle:
        bundle = Path(args.bundle).read_bytes()
        starts = [
            bundle.find(b"-----BEGIN " + label + b"PRIVATE KEY-----")
            for label in (b"", b"RSA ", b"EC ")
        ]
        starts = [position for position in starts if position >= 0]
        if not starts:
            raise ValueError("Backup TLS sem chave privada PEM.")
        position = min(starts)
        cert, key = bundle[:position], bundle[position:]
    elif args.certificate:
        cert = Path(args.certificate).read_bytes()
        key = Path(args.private_key).read_bytes()
    else:
        cert, key = generate_self_signed(hostnames())
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    # Backend's app user owns the private volume; Nginx UID 101 reads via GID 101.
    app = __import__("pwd").getpwnam("app")
    os.chown(root, app.pw_uid, 101)
    os.chmod(root, 0o750)
    details = install_pair(cert, key, hostnames(), root)
    os.chown(target, app.pw_uid, 101)
    os.chmod(target, 0o640)
    print(f"TLS pronto; SHA-256 {details['fingerprint_sha256']}; expira {details['expires_at']}.")


if __name__ == "__main__":
    main()
