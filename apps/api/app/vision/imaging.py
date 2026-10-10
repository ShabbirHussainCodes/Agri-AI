"""Upload sanitising: nothing downstream sees the farmer's original bytes (CLAUDE.md section 5,
docs/security/security-model.md section 5).

What this does, in order:
  1. size cap on the raw bytes;
  2. the file type from its MAGIC BYTES (JPEG, PNG, WebP). The Content-Type header and the file name come
     from the client and are never trusted;
  3. the pixel count from the header, BEFORE anything is decoded (a small file can expand to gigabytes);
  4. a real decode (a file that merely starts with JPEG bytes fails here);
  5. EXIF orientation applied, then ALL metadata dropped by re-encoding. A phone photo carries GPS
     coordinates and a device id in EXIF: they must not be stored or sent to a model provider;
  6. downscale to MAX_SIDE and re-encode as JPEG. Smaller means cheaper to store and to send.

The output is a fresh JPEG plus the same pixels as an RGB array for the quality gate and the classifier.
Pure functions, no network. Errors are `ImageRejected` with a short code the API turns into a bilingual
message (app/vision/messages.py).
"""
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Decompression-bomb guard, checked on the header before decoding. 40 MP is a 6500x6500 photo, larger than
# any phone camera produces.
MAX_PIXELS = 40_000_000
MAX_SIDE = 1024
JPEG_QUALITY = 88

# Pillow's own guard as a second line (it warns above this and errors above twice this).
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

REASON_EMPTY = "empty_upload"
REASON_TOO_LARGE = "file_too_large"
REASON_UNSUPPORTED = "unsupported_image_type"
REASON_TOO_MANY_PIXELS = "image_too_large"
REASON_UNREADABLE = "unreadable_image"


class ImageRejected(Exception):
    """The upload cannot be used. `code` is one of the REASON_* values."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PreparedImage:
    jpeg: bytes  # EXIF-free, at most MAX_SIDE on the long side
    rgb: np.ndarray  # uint8, shape (height, width, 3), same pixels as `jpeg`
    width: int
    height: int
    original_format: str  # "jpeg" | "png" | "webp"
    original_width: int
    original_height: int


def sniff_type(data: bytes) -> str | None:
    """The image type from the first bytes, or None. Not from any client-supplied field."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def prepare_image(data: bytes) -> PreparedImage:
    if not data:
        raise ImageRejected(REASON_EMPTY)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected(REASON_TOO_LARGE)
    kind = sniff_type(data)
    if kind is None:
        raise ImageRejected(REASON_UNSUPPORTED)

    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            # The format Pillow detected must be the one the bytes announced.
            if (probe.format or "").lower() != kind:
                raise ImageRejected(REASON_UNSUPPORTED)
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ImageRejected(REASON_TOO_MANY_PIXELS)
            probe.seek(0)  # first frame only: an animated WebP is read as its first frame
            image = ImageOps.exif_transpose(probe)  # also returns a decoded copy
            image = image.convert("RGB")
    except ImageRejected:
        raise
    except Image.DecompressionBombError:
        # Pillow's own guard fires inside Image.open for a header announcing more than twice MAX_PIXELS.
        raise ImageRejected(REASON_TOO_MANY_PIXELS) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError):
        # SyntaxError: Pillow's PNG/JPEG plugins raise it for truncated or corrupt streams.
        raise ImageRejected(REASON_UNREADABLE) from None

    original_size = image.size
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)  # keeps aspect ratio, never upscales
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # no exif= argument: nothing carried over
    rgb = np.asarray(image, dtype=np.uint8)
    return PreparedImage(
        jpeg=buffer.getvalue(),
        rgb=rgb,
        width=image.width,
        height=image.height,
        original_format=kind,
        original_width=original_size[0],
        original_height=original_size[1],
    )
