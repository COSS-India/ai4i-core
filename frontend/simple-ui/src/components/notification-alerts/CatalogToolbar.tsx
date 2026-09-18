import {
  Box,
  Checkbox,
  FormControl,
  HStack,
  Input,
  Text,
} from "@chakra-ui/react";
import React from "react";
import { RECIPIENT_ROLE_LABELS } from "../../types/notificationAlerts";

interface CatalogToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  hint: string;
}

const CatalogToolbar: React.FC<CatalogToolbarProps> = ({
  search,
  onSearchChange,
  hint,
}) => {
  return (
    <Box mb={4}>
      <HStack spacing={3} mb={3} align="stretch" flexWrap="wrap">
        <FormControl maxW={{ base: "full", md: "280px" }}>
          <Input
            placeholder="Search by name"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            bg="white"
            size="md"
          />
        </FormControl>
      </HStack>
      <Text fontSize="sm" color="gray.600">
        {hint}
      </Text>
    </Box>
  );
};

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

export default CatalogToolbar;
