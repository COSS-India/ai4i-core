import {
  Box,
  Checkbox,
  FormControl,
  HStack,
  Input,
  Select,
  Text,
} from "@chakra-ui/react";
import React from "react";
import type { CatalogStatusFilter } from "../../types/notificationAlerts";

interface CatalogToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  statusFilter: CatalogStatusFilter;
  onStatusFilterChange: (value: CatalogStatusFilter) => void;
  hint: string;
}

const CatalogToolbar: React.FC<CatalogToolbarProps> = ({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
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
        <FormControl maxW={{ base: "full", md: "180px" }}>
          <Select
            value={statusFilter}
            onChange={(e) =>
              onStatusFilterChange(e.target.value as CatalogStatusFilter)
            }
            bg="white"
            size="md"
          >
            <option value="all">All statuses</option>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </Select>
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
  tenantDisabled?: boolean;
  onTenantChange: (checked: boolean) => void;
  onAdopterChange: (checked: boolean) => void;
}

export const RecipientRoleCheckboxes: React.FC<RecipientRoleCheckboxesProps> = ({
  tenantChecked,
  adopterChecked,
  tenantDisabled = false,
  onTenantChange,
  onAdopterChange,
}) => {
  return (
    <Box>
      <Checkbox
        isChecked={tenantChecked}
        isDisabled={tenantDisabled}
        onChange={(e) => onTenantChange(e.target.checked)}
        title={
          tenantDisabled
            ? "Tenant Admin is only configurable on Tier Assigned and Tier Changed right now"
            : undefined
        }
        opacity={tenantDisabled ? 0.45 : 1}
        mb={1}
        display="flex"
      >
        <Text fontSize="sm">Tenant Admin</Text>
      </Checkbox>
      <Checkbox
        isChecked={adopterChecked}
        onChange={(e) => onAdopterChange(e.target.checked)}
        display="flex"
      >
        <Text fontSize="sm">Adopter Admin</Text>
      </Checkbox>
    </Box>
  );
};

export default CatalogToolbar;
