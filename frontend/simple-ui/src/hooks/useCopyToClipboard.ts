// Clipboard and file-download helpers for service page response actions

import { useCallback } from "react";
import { useToastWithDeduplication } from "./useToastWithDeduplication";

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
  const toast = useToastWithDeduplication();

  const copy = useCallback(
    async (text: string, successDescription = "Copied to clipboard.") => {
      const notifySuccess = () => {
        toast({
          title: "Copied to Clipboard",
          description: successDescription,
          status: "success",
          duration: 2000,
          isClosable: true,
        });
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
          toast({
            title: "Copy Failed",
            description: "Failed to copy text to clipboard.",
            status: "error",
            duration: 3000,
            isClosable: true,
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
    [toast]
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
        toast({
          title: "Download Started",
          description: successDescription,
          status: "success",
          duration: 2000,
          isClosable: true,
        });
      } catch {
        toast({
          title: "Download Failed",
          description: "Failed to download file.",
          status: "error",
          duration: 3000,
          isClosable: true,
        });
      }
    },
    [toast]
  );

  return { copy, download };
}
