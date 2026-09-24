import { Badge, Box, Text, VStack } from "@chakra-ui/react";
import React from "react";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
import {
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  type TenantUserStatusValue,
} from "../../config/constants";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";
import type { TenantUserView } from "../../types/tenant";
import InstitutionUserForm from "./InstitutionUserForm";

type ViewInstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
  resolveUserDisplayStatus: (user: TenantUserView) => TenantUserStatusValue;
};

export default function ViewInstitutionUserModal({
  tm,
  resolveUserDisplayStatus,
}: ViewInstitutionUserModalProps) {
  const u = tm.viewUserDetail;
  return (
    <StandardModal
      isOpen={tm.isViewUserModalOpen}
      onClose={tm.closeViewUserModal}
      size="xl"
      scrollBehavior="inside"
      title="User Details"
      description="View the user's information."
      modalProps={{ blockScrollOnMount: true }}
      headerProps={{ px: 6, pt: 5, pb: 4 }}
      bodyProps={{ px: 6, py: 5 }}
      footerProps={{ px: 6, py: 4 }}
      footer={
        <FormActions
          cancelLabel="Close"
          onCancel={tm.closeViewUserModal}
          hideSubmit
          justify="flex-end"
          pt={0}
        />
      }
    >
      {u ? (
        <VStack align="stretch" spacing={4}>
          <InstitutionUserForm mode="view" tm={tm} />
          <Box>
            <FieldLabel variant="inline">User ID</FieldLabel>
            <Text fontFamily="mono">{u.user_id}</Text>
          </Box>
          <Box>
            <FieldLabel variant="inline">Status</FieldLabel>
            <Badge
              colorScheme={getTenantStatusColorScheme(resolveUserDisplayStatus(u))}
            >
              {formatTenantUserStatusLabel(resolveUserDisplayStatus(u))}
            </Badge>
          </Box>
        </VStack>
      ) : (
        <Text>No user selected.</Text>
      )}
    </StandardModal>
  );
}
