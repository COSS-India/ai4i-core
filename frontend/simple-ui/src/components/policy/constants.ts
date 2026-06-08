import type { MaskFormat } from "../../services/policyService";

export const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;

/** Set to `true` to show the Audit log tab again. */
export const SHOW_POLICY_AUDIT_TAB = false;

export const POLICY_TAB_CONFIG = SHOW_POLICY_AUDIT_TAB
  ? ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
      { id: "audit" as const, label: "Audit log" },
    ] as const)
  : ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
    ] as const);


export type PolicySectionId = (typeof POLICY_TAB_CONFIG)[number]["id"];

export const LANGUAGE_OPTIONS = ["en", "hi"] as const;

export const MASK_OPTIONS: MaskFormat[] = ["full", "partial", "redact"];
