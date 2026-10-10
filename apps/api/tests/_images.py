"""Synthetic photos for the vision tests: deterministic, no files, no network."""
import io

import numpy as np
from PIL import Image, ImageFilter


def leaf_like(width: int = 640, height: int = 480, seed: int = 0) -> np.ndarray:
    """A sharp, well-exposed, leaf-coloured image: green with brighter and darker blotches and fine texture."""
    rng = np.random.default_rng(seed)
    coarse = rng.uniform(0.0, 1.0, size=(height // 16 + 1, width // 16 + 1)).astype(np.float32)
    blotch = np.asarray(
        Image.fromarray((coarse * 255).astype(np.uint8)).resize((width, height), Image.Resampling.BICUBIC), dtype=np.float32
    ) / 255.0
    fine = rng.normal(0.0, 14.0, size=(height, width)).astype(np.float32)
    green = 70 + 110 * blotch + fine
    red = 30 + 60 * blotch + fine * 0.6
    blue = 20 + 40 * blotch + fine * 0.4
    return np.clip(np.stack([red, green, blue], axis=-1), 0, 255).astype(np.uint8)


def blurred(rgb: np.ndarray, radius: float = 8.0) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(radius)), dtype=np.uint8)


def scaled(rgb: np.ndarray, factor: float) -> np.ndarray:
    return np.clip(rgb.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def flat(width: int, height: int, rgb: tuple[int, int, int]) -> np.ndarray:
    out = np.zeros((height, width, 3), dtype=np.uint8)
    out[:] = rgb
    return out


def gray_wall(width: int = 640, height: int = 480, seed: int = 1) -> np.ndarray:
    """Sharp texture, exposed fine, but no leaf colour at all."""
    rng = np.random.default_rng(seed)
    base = 120 + rng.normal(0.0, 18.0, size=(height, width)).astype(np.float32)
    gray = np.clip(base, 0, 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def encode(rgb: np.ndarray, fmt: str = "JPEG", **kwargs) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def jpeg_with_exif(rgb: np.ndarray, orientation: int = 1, gps: bool = True) -> bytes:
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation
    exif[0x010F] = "SecretPhone Inc"  # Make
    if gps:
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1] = "N"
        gps_ifd[2] = (26.0, 51.0, 0.0)
        gps_ifd[3] = "E"
        gps_ifd[4] = (80.0, 57.0, 0.0)
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()
