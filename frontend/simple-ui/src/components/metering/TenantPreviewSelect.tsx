import {
  Avatar,
  Badge,
  Box,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Text,
  VStack,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import React from "react";
import type { TenantPreviewOption } from "../../hooks/useMeteringDashboard";
import { INSTITUTION, INSTITUTION_ARTICLE } from "../../config/constants";

export type { TenantPreviewOption } from "../../hooks/useMeteringDashboard";

interface TenantPreviewSelectProps {
  tenants: TenantPreviewOption[];
  selectedTenantId: string;
  onSelect: (tenantId: string) => void;
}

const TenantPreviewSelect: React.FC<TenantPreviewSelectProps> = ({
  tenants,
  selectedTenantId,
  onSelect,
}) => {
  const selected = tenants.find((t) => t.id === selectedTenantId);

  return (
    <Box
      p={4}
      borderWidth="1px"
      borderColor="gray.200"
      borderRadius="md"
      bg="white"
      mb={4}
    >
      <Text fontSize="sm" color="gray.600" mb={2}>
        Select {INSTITUTION_ARTICLE} {INSTITUTION.toLowerCase()} to preview {INSTITUTION} Admin view
      </Text>
      <Menu matchWidth>
        <MenuButton
          as={Box}
          w="full"
          maxW="420px"
          borderWidth="1px"
          borderColor="gray.200"
          borderRadius="md"
          px={3}
          py={2}
          cursor="pointer"
          _hover={{ borderColor: "gray.300" }}
        >
          <HStack justify="space-between">
            {selected ? (
              <HStack spacing={3} minW={0}>
                <Avatar size="sm" name={selected.organisation} bg="orange.100" color="orange.700" />
                <VStack align="flex-start" spacing={0} minW={0}>
                  <Text fontSize="sm" fontWeight="medium" noOfLines={1}>
                    {selected.organisation}
                  </Text>
                </VStack>
                {selected.plan ? (
                  <Badge colorScheme="blue" fontSize="xs" borderRadius="md">
                    {selected.plan}
                  </Badge>
                ) : null}
              </HStack>
            ) : (
              <Text fontSize="sm" color="gray.500">
                Choose a tenant…
              </Text>
            )}
            <ChevronDownIcon color="gray.500" />
          </HStack>
        </MenuButton>
        <MenuList maxH="320px" overflowY="auto" zIndex={10}>
          {tenants.map((tenant) => (
            <MenuItem key={tenant.id} onClick={() => onSelect(tenant.id)} py={2}>
              <HStack spacing={3} w="full" justify="space-between">
                <HStack spacing={3} minW={0}>
                  <Avatar
                    size="sm"
                    name={tenant.organisation}
                    bg="orange.100"
                    color="orange.700"
                  />
                  <Text fontSize="sm" noOfLines={1}>
                    {tenant.organisation}
                  </Text>
                </HStack>
                {tenant.plan ? (
                  <Badge colorScheme="blue" fontSize="xs" borderRadius="md" flexShrink={0}>
                    {tenant.plan}
                  </Badge>
                ) : null}
              </HStack>
            </MenuItem>
          ))}
        </MenuList>
      </Menu>
    </Box>
  );
};

export default TenantPreviewSelect;
