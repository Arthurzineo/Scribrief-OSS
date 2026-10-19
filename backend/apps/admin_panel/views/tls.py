"""Private administrative TLS status and certificate/key rotation."""

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import record_audit

from ..permissions import ActiveStaff
from ..tls_service import MAX_PEM_BYTES, TLS_ROOT, current_status, hostnames, install_pair


class TLSUploadSerializer(serializers.Serializer):
    certificate = serializers.FileField()
    private_key = serializers.FileField()
    current_password = serializers.CharField(write_only=True)


class AdminTLSView(APIView):
    permission_classes = [ActiveStaff]
    parser_classes = [MultiPartParser]

    def _available(self):
        if not TLS_ROOT.is_dir():
            raise Http404("Gestão TLS disponível apenas na instalação beta.")

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        self._available()
        response = Response({**current_status(), "hostnames": hostnames()})
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(request=TLSUploadSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        self._available()
        password = request.data.get("current_password")
        if not isinstance(password, str) or not request.user.check_password(password):
            record_audit(
                request.user,
                "tls_certificate_rotation",
                outcome="denied",
                request=request,
                target_type="tls",
            )
            raise PermissionDenied("Confirme sua senha de administrador.")
        certificate = request.FILES.get("certificate")
        private_key = request.FILES.get("private_key")
        if (
            not certificate
            or not private_key
            or certificate.size > MAX_PEM_BYTES
            or private_key.size > MAX_PEM_BYTES
        ):
            record_audit(
                request.user,
                "tls_certificate_rotation",
                outcome="failed",
                request=request,
                target_type="tls",
                details={"reason": "missing_or_large_file"},
            )
            raise serializers.ValidationError("Envie certificado e chave PEM com até 64 KiB cada.")
        try:
            details = install_pair(certificate.read(), private_key.read(), hostnames())
        except ValueError as exc:
            record_audit(
                request.user,
                "tls_certificate_rotation",
                outcome="failed",
                request=request,
                target_type="tls",
                details={"reason": "invalid_pair"},
            )
            raise serializers.ValidationError(str(exc)) from None
        record_audit(
            request.user,
            "tls_certificate_rotation",
            request=request,
            target_type="tls",
            details={"fingerprint_sha256": details["fingerprint_sha256"]},
        )
        response = Response({"configured": True, **details, "activation": "pending_reload"})
        response["Cache-Control"] = "no-store"
        return response
