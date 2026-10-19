"""Certificate validation and atomic storage for the isolated beta TLS volume."""

import ipaddress
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

MAX_PEM_BYTES = 64 * 1024
TLS_ROOT = Path(os.environ.get("TLS_ROOT", "/app/tls"))


def hostnames():
    return tuple(
        dict.fromkeys(
            (
                os.environ.get("PUBLIC_HOSTNAME", "127.0.0.1"),
                os.environ.get("ADMIN_HOSTNAME", "127.0.0.1"),
            )
        )
    )


def _san(host):
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        if not host or any(char in host for char in " /\\:@"):
            raise ValueError("Hostname TLS inválido.") from None
        return x509.DNSName(host)


def generate_self_signed(names):
    """Generate a local-use leaf with explicit SAN, not a CA/trust anchor."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([_san(name) for name in names]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM), key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def validate_pair(certificate_pem, key_pem, names):
    if (
        not certificate_pem
        or not key_pem
        or len(certificate_pem) > MAX_PEM_BYTES
        or len(key_pem) > MAX_PEM_BYTES
    ):
        raise ValueError("Certificado ou chave vazios ou grandes demais (máximo 64 KiB cada).")
    try:
        cert = x509.load_pem_x509_certificate(certificate_pem)
        key = serialization.load_pem_private_key(key_pem, password=None)
        if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
            raise ValueError("Use chave RSA ou EC sem senha.")
        if isinstance(key, rsa.RSAPrivateKey) and key.key_size < 2048:
            raise ValueError("Chave RSA deve ter pelo menos 2048 bits.")
        if isinstance(key, ec.EllipticCurvePrivateKey) and key.key_size < 256:
            raise ValueError("Chave EC deve ter pelo menos 256 bits.")
        if key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ):
            raise ValueError("A chave privada não corresponde ao certificado.")
        now = datetime.now(UTC)
        if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= now + timedelta(hours=24):
            raise ValueError("Certificado fora da validade ou a vencer em menos de 24 horas.")
        if cert.signature_hash_algorithm and cert.signature_hash_algorithm.name.lower() in {
            "md5",
            "sha1",
        }:
            raise ValueError("Assinatura fraca não permitida.")
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        present = set(sans.get_values_for_type(x509.DNSName)) | {
            str(address) for address in sans.get_values_for_type(x509.IPAddress)
        }
        if any(name not in present for name in names):
            raise ValueError("SAN deve conter os hostnames público e administrativo configurados.")
        try:
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if ExtendedKeyUsageOID.SERVER_AUTH not in eku:
                raise ValueError("Certificado não autorizado para servidor TLS.")
        except x509.ExtensionNotFound:
            pass
    except (TypeError, ValueError, x509.ExtensionNotFound) as exc:
        raise ValueError(f"Par TLS inválido: {exc}") from None
    return {
        "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
        "expires_at": cert.not_valid_after_utc.isoformat(),
        "subject": cert.subject.rfc4514_string(),
        "self_issued": cert.subject == cert.issuer,
    }


def install_pair(certificate_pem, key_pem, names, root=None):
    """Publish one combined PEM atomically; nginx reads cert/key from same file."""
    details = validate_pair(certificate_pem, key_pem, names)
    root = Path(root or TLS_ROOT)
    if root.is_symlink():
        raise ValueError("Diretório TLS não pode ser um link simbólico.")
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    target = root / "current.pem"
    if target.is_symlink():
        raise ValueError("Arquivo TLS não pode ser um link simbólico.")
    fd, name = tempfile.mkstemp(prefix=".tls-", suffix=".pem", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(certificate_pem.rstrip() + b"\n" + key_pem.rstrip() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o640)
        # Docker Desktop may clear setgid on named-volume directories. Assign
        # the Nginx reader group explicitly; backend app belongs to it.
        if os.name == "posix":
            os.chown(name, -1, 101)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return details


def current_status(root=None):
    path = Path(root or TLS_ROOT) / "current.pem"
    if not path.is_file() or path.is_symlink():
        return {"configured": False}
    data = path.read_bytes()
    key_starts = [
        data.find(b"-----BEGIN " + label + b"PRIVATE KEY-----") for label in (b"", b"RSA ", b"EC ")
    ]
    key_starts = [position for position in key_starts if position >= 0]
    if not key_starts:
        return {"configured": False}
    position = min(key_starts)
    try:
        return {
            "configured": True,
            "valid": True,
            **validate_pair(data[:position], data[position:], hostnames()),
        }
    except ValueError:
        return {"configured": True, "valid": False}
