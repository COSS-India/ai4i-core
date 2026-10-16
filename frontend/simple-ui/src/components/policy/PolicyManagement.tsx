import { Alert, AlertIcon } from "@chakra-ui/react";
import PiiPoliciesExperience from "./pii/PiiPoliciesExperience";
import type { PortalRole } from "./pii/model";

export interface PolicyManagementProps {
  /** Adopter admin manages policies. Institution admin browses and subscribes. */
  role: PortalRole | null;
  institutionId: string;
}

export default function PolicyManagement({ role, institutionId }: PolicyManagementProps) {
  if (!role) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Policy Management is available to adopter admins and institution admins.
      </Alert>
    );
  }

  return <PiiPoliciesExperience role={role} institutionId={institutionId} />;
}
