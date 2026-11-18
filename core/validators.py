"""Upload validation: 5 MB hard cap, extension allow-list, executable block-list and content sniffing."""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

HARD_LIMIT_MB = 5  # SRS change request: no upload may exceed 5 MB

# Never accepted, whatever the allow-list says (also catches double extensions such as "cv.pdf.exe").
BLOCKED_EXTENSIONS = {
    "exe", "msi", "bat", "cmd", "com", "scr", "pif", "cpl", "dll", "sys", "vbs", "vbe", "js", "jse", "wsf", "wsh",
    "ps1", "psm1", "sh", "bash", "jar", "apk", "app", "dmg", "bin", "run", "elf", "hta", "lnk", "reg", "msp", "gadget",
    "php", "py", "pl", "rb", "html", "htm", "svg", "xhtml", "docm", "xlsm", "pptm", "iso", "img",
}

# Magic numbers of executable formats, rejected even if renamed to .pdf / .jpg.
EXECUTABLE_SIGNATURES = [b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"<script", b"<?php"]

SIGNATURES = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF8"],
    "webp": [b"RIFF"],
    "docx": [b"PK\x03\x04"],
    "xlsx": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0"],
    "xls": [b"\xd0\xcf\x11\xe0"],
}


@deconstructible
class UploadValidator:
    def __init__(self, extensions=None, max_mb=None):
        self.extensions = extensions
        self.max_mb = max_mb

    def __call__(self, f):
        extensions = self.extensions or settings.ALLOWED_DOCUMENT_EXTENSIONS
        max_mb = min(self.max_mb or settings.MAX_UPLOAD_MB, HARD_LIMIT_MB)
        name = os.path.basename(f.name).lower()
        parts = name.split(".")[1:]
        if any(p in BLOCKED_EXTENSIONS for p in parts):
            raise ValidationError("Executable and script files (e.g. .exe) cannot be uploaded.")
        ext = parts[-1] if parts else ""
        if ext not in extensions:
            raise ValidationError(f"File type '.{ext}' is not allowed. Allowed types: {', '.join(extensions)}.")
        if f.size > max_mb * 1024 * 1024:
            raise ValidationError(f"File is too large ({f.size / 1048576:.1f} MB). Maximum size is {max_mb} MB.")
        if hasattr(f, "read"):
            pos = f.tell() if hasattr(f, "tell") else 0
            head = f.read(16)
            f.seek(pos)
            if any(head.startswith(sig) for sig in EXECUTABLE_SIGNATURES):
                raise ValidationError("This file looks like a program or script and cannot be uploaded.")
            sigs = SIGNATURES.get(ext)
            if sigs and head and not any(head.startswith(s) for s in sigs):
                raise ValidationError("The file content does not match its extension.")

    def __eq__(self, other):
        return isinstance(other, UploadValidator) and (self.extensions, self.max_mb) == (other.extensions, other.max_mb)


validate_document = UploadValidator()
