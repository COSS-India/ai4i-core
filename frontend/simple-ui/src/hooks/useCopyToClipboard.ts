// Clipboard and file-download helpers for service page response actions

import { useCallback } from "react";
import { showToast } from "../utils/toast";

export function downloadTextFile(
  content: string,
  filename: string,
  mimeType = "text/plain"
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function useCopyToClipboard() {
  const copy = useCallback(
    async (text: string, successDescription = "Copied to clipboard.") => {
      const notifySuccess = () => {
        showToast({ type: "success", message: successDescription });
      };

      const fallbackCopy = () => {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
          document.execCommand("copy");
          notifySuccess();
        } catch {
          showToast({
            type: "error",
            message: "Failed to copy text to clipboard.",
          });
        }
        document.body.removeChild(textArea);
      };

      if (navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(text);
          notifySuccess();
        } catch {
          fallbackCopy();
        }
      } else {
        fallbackCopy();
      }
    },
    []
  );

  const download = useCallback(
    (
      content: string,
      filename: string,
      options?: { mimeType?: string; successDescription?: string }
    ) => {
      const { mimeType = "text/plain", successDescription = "File downloaded." } =
        options ?? {};
      try {
        downloadTextFile(content, filename, mimeType);
        showToast({ type: "success", message: successDescription });
      } catch {
        showToast({
          type: "error",
          message: "Failed to download file.",
        });
      }
    },
    []
  );

  return { copy, download };
}
