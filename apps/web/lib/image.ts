/** Shrinks a phone photo before it is uploaded (frontend-architecture.md: "client-side image resize before
 *  upload"). A 12-megapixel photo is 4 to 8 MB; on a slow connection that is the whole difference between a
 *  result and a timeout. The server re-checks and re-encodes everything anyway (apps/api/app/vision/imaging.py);
 *  this is only for speed. Drawing to a canvas also drops EXIF, so the phone's GPS position leaves the device
 *  with the pixels removed. If anything here fails, the original file is sent and the server decides. */
export const MAX_SIDE = 1280;
const QUALITY = 0.85;

export async function resizeForUpload(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", QUALITY));
    return blob ?? file;
  } catch {
    return file;
  }
}
