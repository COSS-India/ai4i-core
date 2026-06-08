import { ASR_ERRORS, COMMON_ERRORS } from "../../config/constants";
import { ApiValidationError } from "../../services/dto/apiValidationError";
import { resolveMappedServiceError, resolveUnknownCodeError } from "./errorMappings";
import { formatErrorCode } from "./formatErrorCode";
import { parseNestedDetailMessage, parseValidationErrors } from "./parseApiDetail";
import type { ErrorDetail, ErrorHandlerService, ErrorInfo } from "./types";

function handleStructuredDetail(
  detail: ErrorDetail,
  service: ErrorHandlerService | undefined,
  fallbackMessage: string
): { errorTitle: string; errorMessage: string; resolved?: ErrorInfo } {
  let errorMessage = fallbackMessage;
  let errorTitle = "Error";

  if (detail.message) {
    errorMessage = parseNestedDetailMessage(String(detail.message));
  }

  const errorCode = String(detail.error ?? detail.code ?? "").toUpperCase();
  if (errorCode) {
    const mapped = resolveMappedServiceError(service, errorCode, detail);
    if (mapped) {
      return { errorTitle: mapped.title, errorMessage: mapped.message, resolved: mapped };
    }

    if (detail.message) {
      return {
        errorTitle: formatErrorCode(errorCode),
        errorMessage,
        resolved: {
          title: formatErrorCode(errorCode),
          message: errorMessage,
          showOnlyMessage: true,
        },
      };
    }

    const unknown = resolveUnknownCodeError(errorCode, detail, errorMessage);
    errorTitle = unknown.title;
    errorMessage = unknown.message;
    return { errorTitle, errorMessage, resolved: unknown };
  }

  if (detail.hint && typeof detail.hint === "string") {
    errorMessage = errorMessage + (errorMessage.endsWith(".") ? " " : ". ") + detail.hint;
  }

  if ((detail.error || detail.code) && detail.message) {
    return {
      errorTitle,
      errorMessage,
      resolved: { title: errorTitle, message: errorMessage, showOnlyMessage: true },
    };
  }

  return { errorTitle, errorMessage };
}

function handleApiKeyError(error: unknown, errorTitle: string, errorMessage: string): ErrorInfo | null {
  const err = error as {
    response?: { data?: { detail?: ErrorDetail | string } };
    message?: string;
  };
  const detail = err?.response?.data?.detail;
  const detailObj = typeof detail === "object" && detail !== null ? detail : null;
  const detailMessage =
    detailObj?.message && typeof detailObj.message === "string" ? detailObj.message : "";
  const detailStr = typeof detail === "string" ? detail : "";

  if (
    detailObj?.message?.toString().toLowerCase().includes("api key") ||
    detailObj?.error === "API_KEY_MISSING" ||
    (detailObj?.error === "INVALID_API_KEY" && detailMessage) ||
    err?.message?.toLowerCase().includes("api key") ||
    detailStr.toLowerCase().includes("api key")
  ) {
    if (detailMessage && detailMessage.toLowerCase().includes("api key")) {
      return { title: errorTitle, message: detailMessage, showOnlyMessage: true };
    }
    if (detailStr && detailStr.toLowerCase().includes("api key")) {
      return { title: errorTitle, message: detailStr, showOnlyMessage: true };
    }
    if (err?.message?.toLowerCase().includes("api key")) {
      return { title: errorTitle, message: err.message, showOnlyMessage: true };
    }
    if (!errorMessage || errorMessage === "An unexpected error occurred. Please try again.") {
      return {
        title: errorTitle,
        message: "API key is required to access this service.",
        showOnlyMessage: true,
      };
    }
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }

  return null;
}

export function extractErrorInfo(error: unknown, service?: ErrorHandlerService): ErrorInfo {
  let errorMessage = "An unexpected error occurred. Please try again.";
  let errorTitle = "Error";

  if (error instanceof ApiValidationError) {
    return {
      title: "API Contract Mismatch",
      message: error.message,
      showOnlyMessage: true,
    };
  }

  const err = error as {
    response?: { status?: number; data?: Record<string, unknown> };
    status?: number;
    message?: string;
    code?: string;
  };

  if (err?.response?.data) {
    const data = err.response.data;
    const backendMessage = (data.detail as ErrorDetail)?.message ?? data.message;
    if (backendMessage && typeof backendMessage === "string") {
      errorMessage = backendMessage;
    }

    if (data.detail && Array.isArray(data.detail)) {
      const validation = parseValidationErrors(data.detail);
      if (validation) return validation;
    }

    if (data.detail && typeof data.detail === "object" && !Array.isArray(data.detail)) {
      const structured = handleStructuredDetail(data.detail as ErrorDetail, service, errorMessage);
      if (structured.resolved) return structured.resolved;
      errorTitle = structured.errorTitle;
      errorMessage = structured.errorMessage;
    } else if (typeof data.detail === "string") {
      errorMessage = data.detail;
    } else if (data.message) {
      errorMessage = String(data.message);
    }
  }

  const apiKeyError = handleApiKeyError(error, errorTitle, errorMessage);
  if (apiKeyError) return apiKeyError;

  const status = err?.response?.status;
  if (
    (status === 500 || status === 503) &&
    typeof errorMessage === "string" &&
    errorMessage.toLowerCase().includes("unavailable")
  ) {
    errorTitle = "Service Unavailable";
  }

  if (status === 401 || err?.status === 401 || err?.message?.includes("401")) {
    errorTitle = "Authentication Failed";
    errorMessage =
      err?.message?.includes("API key") || err?.message?.includes("api key")
        ? "API key is required to access this service."
        : ASR_ERRORS.AUTH_FAILED.description;
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }

  const detailObj = err?.response?.data?.detail;
  const detailMessage =
    typeof detailObj === "object" &&
    detailObj !== null &&
    !Array.isArray(detailObj) &&
    (detailObj as ErrorDetail).message
      ? String((detailObj as ErrorDetail).message)
      : "";
  const lowerMessage = (
    errorMessage ||
    detailMessage ||
    (err?.message && String(err.message)) ||
    ""
  ).toLowerCase();

  if (status === 403) {
    const errorCode = String(
      (detailObj as ErrorDetail)?.error ?? (detailObj as ErrorDetail)?.code ?? ""
    ).toUpperCase();
    if (errorCode === "TENANT_SUSPENDED" || errorCode.includes("SUSPENDED")) {
      const suspended = ASR_ERRORS.TENANT_SUSPENDED;
      return {
        title: suspended.title,
        message: suspended.description,
        showOnlyMessage: true,
      };
    }
    if (
      errorCode === "UNAUTHORIZED" ||
      lowerMessage.includes("unauthorized") ||
      lowerMessage.includes("permission")
    ) {
      const unauthorized = COMMON_ERRORS.UNAUTHORIZED;
      return {
        title: unauthorized.title,
        message:
          errorMessage !== "An unexpected error occurred. Please try again."
            ? errorMessage
            : unauthorized.description,
        showOnlyMessage: true,
      };
    }
  }

  if (
    err?.code === "ECONNREFUSED" ||
    err?.code === "ENOTFOUND" ||
    err?.code === "ETIMEDOUT" ||
    err?.code === "ECONNABORTED" ||
    err?.message?.includes("Network Error") ||
    err?.message?.includes("network") ||
    err?.message?.includes("Failed to fetch")
  ) {
    const network = COMMON_ERRORS.NETWORK_ERROR;
    return {
      title: network.title,
      message: network.description,
      showOnlyMessage: true,
    };
  }

  if (err?.message && errorMessage === "An unexpected error occurred. Please try again.") {
    errorMessage = err.message;
  }

  return {
    title: errorTitle,
    message: errorMessage,
    showOnlyMessage: false,
  };
}

export function isPermissionDeniedError(error: unknown): boolean {
  const err = error as { response?: { data?: { detail?: ErrorDetail } } };
  const errorCode = err?.response?.data?.detail?.error || err?.response?.data?.detail?.code || "";
  return String(errorCode).includes("PERMISSION_DENIED");
}
