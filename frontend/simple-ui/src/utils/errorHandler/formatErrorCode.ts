export function formatErrorCode(code: string): string {
  if (code === "PERMISSION_DENIED" || code.includes("PERMISSION_DENIED")) {
    return "PERMISSION DENIED";
  }

  return code
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}
