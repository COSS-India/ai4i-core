import { OCR_ERRORS, MAX_IMAGE_FILE_SIZE } from "../constants";
import { showToast } from "./toast";
import { isSafeUserImageUrl } from "./safeImageUrl";

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const base64 = (reader.result as string).split(",")[1];
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("File read failed"));
  });
}

function isSupportedImage(file: File): boolean {
  const name = file.name.toLowerCase();
  return (
    file.type === "image/jpeg" ||
    file.type === "image/jpg" ||
    file.type === "image/png" ||
    name.endsWith(".jpg") ||
    name.endsWith(".jpeg") ||
    name.endsWith(".png")
  );
}

export function validateOCRImageFile(file: File): (typeof OCR_ERRORS)[keyof typeof OCR_ERRORS] | null {
  if (!isSupportedImage(file)) return OCR_ERRORS.INVALID_FORMAT;
  if (file.size > MAX_IMAGE_FILE_SIZE) return OCR_ERRORS.FILE_TOO_LARGE;
  if (file.size === 0) return OCR_ERRORS.EMPTY_FILE;
  return null;
}

export function showOCRError(error: (typeof OCR_ERRORS)[keyof typeof OCR_ERRORS]): void {
  showToast({ type: "error", message: error.description });
}

export function requireOCRService(selectedServiceId: string): boolean {
  if (selectedServiceId.trim()) return true;
  showToast({ type: "warning", message: "Please select an OCR service before uploading an image." });
  return false;
}

export type OCRImagePayload =
  | { ok: true; imageContent: string | null; imageUri: string | null }
  | { ok: false };

export async function prepareOCRImagePayload(
  imageFile: File | null,
  imageUri: string
): Promise<OCRImagePayload> {
  if (imageFile) {
    try {
      const imageContent = await fileToBase64(imageFile);
      if (!imageContent) {
        showOCRError(OCR_ERRORS.EMPTY_FILE);
        return { ok: false };
      }
      return { ok: true, imageContent, imageUri: null };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "";
      showOCRError(message === "EMPTY_FILE" ? OCR_ERRORS.EMPTY_FILE : OCR_ERRORS.INVALID_FILE);
      return { ok: false };
    }
  }

  if (!isSafeUserImageUrl(imageUri)) {
    showToast({
      type: "error",
      message: "Please provide a valid image URL (http://, https://, or data:image/*).",
    });
    return { ok: false };
  }

  return { ok: true, imageContent: null, imageUri };
}

export function updateImageUriPreview(value: string): string | null {
  if (!value.trim()) return null;
  if (isSafeUserImageUrl(value)) return value;
  showToast({
    type: "error",
    message: "Please provide a valid image URL (http://, https://, or data:image/*).",
  });
  return null;
}
