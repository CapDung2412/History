from __future__ import annotations

from fastapi import Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .quality import ImageValidationError
from .settings import APISettings


async def read_upload(request: Request, settings: APISettings) -> bytes:
    """Parse one bounded image; accepted uploads never roll over to disk.

    The ASGI guard caps the complete body before any chunk reaches this parser.
    Setting a per-parser spool threshold above that cap avoids the framework's
    default 1 MB disk spill without mutating framework-global configuration.
    """

    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise ImageValidationError("invalid_request", "Hãy gửi một tệp ảnh trong trường file.", 422)
    parser = MultiPartParser(request.headers, request.stream(), max_files=1, max_fields=0)
    parser.spool_max_size = settings.max_upload_bytes + settings.multipart_overhead_bytes + 1
    try:
        form = await parser.parse()
        values = form.multi_items()
        if len(values) != 1 or values[0][0] != "file" or not isinstance(values[0][1], UploadFile):
            raise ImageValidationError("invalid_request", "Hãy gửi đúng một tệp ảnh trong trường file.", 422)
        file = values[0][1]
        if file.size is not None and file.size > settings.max_upload_bytes:
            raise ImageValidationError("file_too_large", "Ảnh vượt quá giới hạn dung lượng.", 413)
        return await file.read(settings.max_upload_bytes + 1)
    except (MultiPartException, MultipartParseError) as exc:
        raise ImageValidationError("invalid_request", "Dữ liệu tải ảnh không hợp lệ.", 400) from exc
    finally:
        # Also close partially parsed streams after timeout, cancellation, or a
        # streamed body-limit exception. Nothing is retained after the request.
        for file in parser._files_to_close_on_error:
            file.close()
