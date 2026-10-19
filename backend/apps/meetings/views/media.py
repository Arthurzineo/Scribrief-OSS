import re
from pathlib import Path

from django.http import FileResponse, StreamingHttpResponse
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.audit.models import record_audit

from ..storage import safe_media_path


class MediaMixin:
    @action(detail=True, methods=["get"], url_path="original/download")
    def original_download(self, request, pk=None):
        meeting = self.get_object()
        if not meeting.original_path or meeting.staged_at is not None:
            raise NotFound("Original não disponível.")
        path = safe_media_path(meeting.original_path)
        if not path.is_file():
            raise NotFound("Original não disponível.")
        record_audit(request.user, "original_download", meeting.id, request=request)
        return FileResponse(
            path.open("rb"), as_attachment=True, filename=f"original{Path(path).suffix}"
        )

    @action(detail=True, methods=["get"])
    def audio(self, request, pk=None):
        meeting = self.get_object()
        if not meeting.audio_path:
            raise NotFound("Áudio não disponível.")
        path = safe_media_path(meeting.audio_path)
        if not path.is_file():
            raise NotFound("Áudio não disponível.")
        size = path.stat().st_size
        range_header = request.headers.get("Range", "")
        start, end, code = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or not any(match.groups()):
                return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            if start >= size or end < start:
                return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
            end = min(end, size - 1)
            code = 206

        def stream():
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        response = StreamingHttpResponse(stream(), status=code, content_type="audio/mpeg")
        response["Content-Length"] = str(end - start + 1)
        response["Accept-Ranges"] = "bytes"
        response["Cache-Control"] = "private, no-store"
        if code == 206:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        if start == 0:
            record_audit(request.user, "audio_play", meeting.id, request=request)
        return response
