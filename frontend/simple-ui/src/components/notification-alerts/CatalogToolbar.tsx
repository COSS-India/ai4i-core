import { Box, Checkbox, Text } from "@chakra-ui/react";
import React from "react";
import { RECIPIENT_ROLE_LABELS } from "../../types/notificationAlerts";

interface RecipientRoleCheckboxesProps {
  tenantChecked: boolean;
  adopterChecked: boolean;
  onTenantChange: (checked: boolean) => void;
  onAdopterChange: (checked: boolean) => void;
}

export const RecipientRoleCheckboxes: React.FC<RecipientRoleCheckboxesProps> = ({
  tenantChecked,
  adopterChecked,
  onTenantChange,
  onAdopterChange,
}) => {
  return (
    <Box>
      <Checkbox
        isChecked={tenantChecked}
        onChange={(e) => onTenantChange(e.target.checked)}
        mb={1}
        display="flex"
      >
        <Text fontSize="sm">{RECIPIENT_ROLE_LABELS["TENANT ADMIN"]}</Text>
      </Checkbox>
      <Checkbox
        isChecked={adopterChecked}
        onChange={(e) => onAdopterChange(e.target.checked)}
        display="flex"
      >
        <Text fontSize="sm">{RECIPIENT_ROLE_LABELS.ADMIN}</Text>
      </Checkbox>
    </Box>
  );
};
