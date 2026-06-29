import { useCallback, useEffect, useRef, useState } from "react";
import { VALIDATION } from "../../../constants/validation";
import {
  runEmailAvailabilityCheck,
  type EmailAvailabilityStatus,
  type RunEmailAvailabilityCheckOptions,
} from "../../../utils/tenantEmailAvailability";
import {
  validateEmailFormatOnly,
  validateTenantContactEmailTaken,
} from "../../../utils/tenantEmailValidation";

interface UseEmailAvailabilityFieldOptions {
  enabled: boolean;
  email: string;
  patchError: (field: string, error: string | undefined) => void;
  getCheckOptions: (emailValue: string) => Omit<RunEmailAvailabilityCheckOptions, "email">;
  /** Re-run when the cached email lists finish loading. */
  recheckKey?: string | number;
}

export function useEmailAvailabilityField({
  enabled,
  email,
  patchError,
  getCheckOptions,
  recheckKey,
}: UseEmailAvailabilityFieldOptions) {
  const [status, setStatus] = useState<EmailAvailabilityStatus>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  const clear = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    requestIdRef.current += 1;
    setStatus("idle");
  }, []);

  const schedule = useCallback(
    (value: string) => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      const formatError = validateEmailFormatOnly(value);
      if (formatError) {
        requestIdRef.current += 1;
        patchError("email", formatError);
        setStatus("idle");
        return;
      }

      const options = getCheckOptions(value);
      const tenantTaken = validateTenantContactEmailTaken(
        value,
        options.tenantEmails,
        options.exclusions
      );
      if (tenantTaken) {
        requestIdRef.current += 1;
        patchError("email", tenantTaken);
        setStatus("idle");
        return;
      }

      const runCheck = () => {
        void (async () => {
          const requestId = ++requestIdRef.current;
          const result = await runEmailAvailabilityCheck({
            ...getCheckOptions(value),
            email: value,
          });
          if (requestId !== requestIdRef.current) return;
          patchError("email", result.error);
          setStatus(result.status);
        })();
      };

      patchError("email", undefined);
      setStatus("checking");

      timerRef.current = setTimeout(runCheck, VALIDATION.EMAIL.CHECK_DEBOUNCE_MS);
    },
    [getCheckOptions, patchError]
  );

  const handleChange = useCallback(
    (value: string) => {
      schedule(value);
    },
    [schedule]
  );

  const verifyNow = useCallback(async (): Promise<boolean> => {
    const result = await runEmailAvailabilityCheck({
      ...getCheckOptions(email),
      email,
    });
    patchError("email", result.error);
    setStatus(result.status);
    return !result.error && result.status === "available";
  }, [email, getCheckOptions, patchError]);

  useEffect(() => {
    if (!enabled) {
      clear();
      return;
    }
    const trimmed = email.trim();
    if (!trimmed || recheckKey === undefined) return;
    schedule(trimmed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, recheckKey]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      requestIdRef.current += 1;
    };
  }, []);

  return { status, handleChange, clear, verifyNow };
}
