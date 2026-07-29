// ConsentCheckbox — shared ToS/Privacy Policy consent control used across
// all registration flows (Sign Up, Create Tenant, Add Tenant User).

import React from "react";
import { Checkbox, FormControl, FormErrorMessage, Link } from "@chakra-ui/react";
import { UI_ERROR_MESSAGES } from "../../config/constants";

export interface ConsentCheckboxProps {
  isChecked: boolean;
  onChange: (checked: boolean) => void;
  error?: string;
}

/** Submit-time validation — returns the error message when consent is missing. */
export function getConsentValidationError(accepted: boolean): string | undefined {
  return accepted ? undefined : UI_ERROR_MESSAGES.CONSENT_REQUIRED;
}

const ConsentCheckbox: React.FC<ConsentCheckboxProps> = ({ isChecked, onChange, error }) => (
  <FormControl isRequired isInvalid={!!error}>
    <Checkbox isChecked={isChecked} onChange={(e) => onChange(e.target.checked)}>
      I agree to AI4I Orchestrate&apos;s{" "}
      <Link
        href="https://github.com/COSS-India/ai4i-core/blob/master/docs/legal/terms-of-service.md"
        isExternal
        color="blue.500"
      >
        Terms of Service
      </Link>{" "}
      and{" "}
      <Link
        href="https://github.com/COSS-India/ai4i-core/blob/master/docs/legal/privacy-policy.md"
        isExternal
        color="blue.500"
      >
        Privacy Policy
      </Link>
    </Checkbox>
    {error && <FormErrorMessage>{error}</FormErrorMessage>}
  </FormControl>
);

export default ConsentCheckbox;
