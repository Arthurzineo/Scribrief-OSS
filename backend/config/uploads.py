from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class SizeLimitUploadHandler(FileUploadHandler):
    """Abort streaming as soon as the configured file limit is crossed."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        from apps.meetings.services.upload_capacity import admit_multipart

        admit_multipart(self.request, content_length)

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.bytes_seen = 0

    def receive_data_chunk(self, raw_data, start):
        self.bytes_seen += len(raw_data)
        if self.bytes_seen > settings.MAX_UPLOAD_BYTES:
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None
