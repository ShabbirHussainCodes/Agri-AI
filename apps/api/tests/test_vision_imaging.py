"""Upload sanitising (app/vision/imaging.py): no database, no network, no model."""
import io
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from app.vision import imaging

from ._images import encode, jpeg_with_exif, leaf_like


def reject_code(data: bytes) -> str:
    with pytest.raises(imaging.ImageRejected) as caught:
        imaging.prepare_image(data)
    return caught.value.code


def test_a_normal_jpeg_is_accepted_and_reencoded():
    prepared = imaging.prepare_image(encode(leaf_like(800, 600), "JPEG"))
    assert prepared.original_format == "jpeg"
    assert (prepared.width, prepared.height) == (800, 600)
    assert prepared.rgb.shape == (600, 800, 3) and prepared.rgb.dtype == np.uint8
    assert imaging.sniff_type(prepared.jpeg) == "jpeg"


@pytest.mark.parametrize("fmt,kind", [("PNG", "png"), ("WEBP", "webp")])
def test_png_and_webp_are_accepted_and_come_out_as_jpeg(fmt, kind):
    prepared = imaging.prepare_image(encode(leaf_like(300, 300), fmt))
    assert prepared.original_format == kind
    assert imaging.sniff_type(prepared.jpeg) == "jpeg"


def test_empty_upload():
    assert reject_code(b"") == imaging.REASON_EMPTY


def test_oversized_upload_is_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(imaging, "MAX_UPLOAD_BYTES", 1000)
    assert reject_code(b"\xff\xd8\xff" + b"0" * 2000) == imaging.REASON_TOO_LARGE


@pytest.mark.parametrize("data", [b"GIF89a" + b"0" * 50, b"%PDF-1.7 " + b"0" * 50, b"<svg></svg>", b"\x00" * 64])
def test_the_file_type_comes_from_the_bytes_not_from_a_name(data):
    assert reject_code(data) == imaging.REASON_UNSUPPORTED


def test_jpeg_magic_with_garbage_behind_it_is_unreadable():
    assert reject_code(b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 20) == imaging.REASON_UNREADABLE


def test_a_truncated_jpeg_is_unreadable():
    good = encode(leaf_like(400, 300), "JPEG")
    assert reject_code(good[: len(good) // 3]) == imaging.REASON_UNREADABLE


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG whose header announces a huge canvas but whose data is tiny: the shape of a decompression bomb."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


def test_a_pixel_bomb_is_refused_from_its_header():
    assert reject_code(_png_header_only(30000, 30000)) == imaging.REASON_TOO_MANY_PIXELS


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_a_canvas_above_the_cap_but_below_pillows_own_bomb_limit_is_still_refused():
    # 7000 x 7000 = 49 MP: Pillow only warns between 40 and 80 MP, so our own cap is what refuses it.
    assert reject_code(_png_header_only(7000, 7000)) == imaging.REASON_TOO_MANY_PIXELS


def test_exif_gps_and_make_do_not_survive():
    original = jpeg_with_exif(leaf_like(500, 400), orientation=1, gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825), "the fixture must carry GPS"
    prepared = imaging.prepare_image(original)
    out = Image.open(io.BytesIO(prepared.jpeg))
    assert dict(out.getexif()) == {}
    assert b"SecretPhone" not in prepared.jpeg
    assert out.info.get("exif") is None


def test_exif_orientation_is_applied_before_it_is_dropped():
    # Orientation 6 = the stored pixels must be rotated 90 degrees to display upright: 600x400 becomes 400x600.
    prepared = imaging.prepare_image(jpeg_with_exif(leaf_like(600, 400), orientation=6, gps=False))
    assert (prepared.width, prepared.height) == (400, 600)


def test_large_photos_are_scaled_down_and_small_ones_are_not_scaled_up():
    big = imaging.prepare_image(encode(leaf_like(3000, 2000), "JPEG"))
    assert max(big.width, big.height) == imaging.MAX_SIDE
    assert (big.original_width, big.original_height) == (3000, 2000)
    assert abs(big.width / big.height - 1.5) < 0.01
    small = imaging.prepare_image(encode(leaf_like(300, 200), "JPEG"))
    assert (small.width, small.height) == (300, 200)


def test_the_rgb_array_is_the_pixels_of_the_returned_jpeg():
    prepared = imaging.prepare_image(encode(leaf_like(500, 400), "PNG"))
    decoded = np.asarray(Image.open(io.BytesIO(prepared.jpeg)).convert("RGB"))
    assert decoded.shape == prepared.rgb.shape
    assert np.abs(decoded.astype(int) - prepared.rgb.astype(int)).mean() < 8  # JPEG round trip only, on a noisy fixture


def test_an_animated_webp_is_read_as_its_first_frame():
    frames = [Image.fromarray(leaf_like(120, 120, seed=s)) for s in range(3)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=50)
    prepared = imaging.prepare_image(buffer.getvalue())
    assert (prepared.width, prepared.height) == (120, 120)
