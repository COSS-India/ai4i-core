import React from "react";
import {
  Box,
  FormControl,
  Heading,
  HStack,
  Text,
  VStack,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Button,
  Badge,
  Select,
  Tooltip,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useRolesTab } from "./hooks/useRolesTab";
import UserSearchableSelect from "../common/UserSearchableSelect";
import StandardModal from "../common/StandardModal";
import { formatDefaultTenantAssignableRoleLabel } from "../../utils/defaultTenant";
import { INSTITUTION } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldLabel from "../common/FieldLabel";

export interface RolesTabProps {
  users: import("../../types/auth").User[];
  isLoadingUsers: boolean;
  /** Default-tenant scope for platform role assignment (Profile → Roles). */
  defaultTenantId?: string | null;
}

export default function RolesTab({ users, isLoadingUsers, defaultTenantId }: RolesTabProps) {
  const { user } = useAuth();
  const rt = useRolesTab({
    user: user ?? null,
    users,
    isLoadingUsers,
  });
  return (
    <Box>
      <HStack justify="space-between" mb={4}>
        <Heading size="md" color="ink.800" userSelect="none" cursor="default">
          Role-Based Access Control (RBAC)
        </Heading>
        {rt.isModeratorOnly && (
          <Badge colorScheme="orange" fontSize="sm" p={2}>
            View Only
          </Badge>
        )}
      </HStack>
      <VStack spacing={6} align="stretch">
        <HStack justify="space-between" align="flex-start">
          <Text fontSize="sm" color="ink.600">
            Manage user roles and permissions
          </Text>
            <Tooltip
              label={FIELD_HINTS.tenantUser.selfRegisteredRoleLocked}
              placement="top"
              hasArrow
              openDelay={300}
              isDisabled={!rt.isSelectedUserSelfRegistered}
            >
              <Box as="span" tabIndex={rt.isSelectedUserSelfRegistered ? 0 : undefined} display="inline-flex">
                <Button
                  size="sm"
                  colorScheme="blue"
                  onClick={rt.openManageRoles}
                  isDisabled={
                    !rt.selectedUser ||
                    !rt.isAdmin ||
                    rt.isModeratorOnly ||
                    rt.isLoadingUserRoles ||
                    rt.isSelectedUserSelfRegistered
                  }
                >
                  Manage Roles
                </Button>
              </Box>
            </Tooltip>
          </HStack>

          <Box>

            <FormControl>
              <FieldLabel hint={FIELD_HINTS.profile.roleUser.tip}>User</FieldLabel>
              <UserSearchableSelect
                key={`${defaultTenantId ?? "pending"}-${users.length}`}
                variant="pick"
                value={rt.selectedUser?.user_id ?? null}
                onChange={(id, picked) => rt.handleUserSelect(id, picked)}
                seedUsers={isLoadingUsers ? [] : users}
                usersFromSeedOnly={true}
                isLoading={isLoadingUsers}
                isDisabled={isLoadingUsers || !defaultTenantId}
                placeholder={
                  isLoadingUsers
                    ? "Loading users..."
                    : defaultTenantId
                      ? "Select a user"
                      : `Default ${INSTITUTION.toLowerCase()} not found`
                }
                selectedPreview={rt.selectedUser}
                allowClear
              />
            </FormControl>
          </Box>

          {rt.selectedUser && (
            <Box>
              <Heading size="sm" mb={4} color="ink.800" userSelect="none" cursor="default">
                Current Role for {rt.selectedUser.username}
              </Heading>
              {rt.isLoadingUserRoles ? (
                <Center py={4}>
                  <Spinner size="md" />
                </Center>
              ) : rt.selectedUserRoles.length > 0 ? (
                <Wrap spacing={2}>
                  {rt.selectedUserRoles.map((roleName) => (
                    <WrapItem key={roleName}>
                      <Badge colorScheme="green" fontSize="sm" px={2} py={1}>
                        {formatDefaultTenantAssignableRoleLabel(roleName)}
                      </Badge>
                    </WrapItem>
                  ))}
                </Wrap>
              ) : (
                <Alert status="info" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>This user has no roles assigned.</AlertDescription>
                </Alert>
              )}
            </Box>
          )}

          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              Only administrators can manage roles. Select a user to view and manage their roles.
            </AlertDescription>
          </Alert>
        </VStack>

      <StandardModal
        isOpen={rt.isManageRolesOpen}
        onClose={rt.closeManageRoles}
        size="lg"
        title={`Manage Roles ${rt.selectedUser ? `for ${rt.selectedUser.username}` : ""}`}
        footer={
          <>
            <Button variant="ghost" onClick={rt.closeManageRoles} isDisabled={rt.isSavingRoles}>
              Cancel
            </Button>
            <Button
              ml={3}
              colorScheme="blue"
              onClick={rt.saveManageRoles}
              isLoading={rt.isSavingRoles}
              loadingText="Saving..."
              isDisabled={!rt.hasDraftChanges || !rt.isAdmin || rt.isModeratorOnly}
            >
              Save Changes
            </Button>
          </>
        }
      >
        {rt.availableRoles.length === 0 ? (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>No roles are available to assign.</AlertDescription>
          </Alert>
        ) : (
          <VStack align="stretch" spacing={3}>
            <Text fontSize="sm" color="ink.600">
              Select a role to assign to this user.
            </Text>
            <FormControl>
              <FieldLabel>Role</FieldLabel>
              <Select
                value={rt.draftRole}
                onChange={(e) => rt.setDraftRole(e.target.value)}
                isDisabled={rt.isSavingRoles || !rt.isAdmin || rt.isModeratorOnly}
                bg="white"
                size="sm"
              >
                <option value="">Select a role</option>
                {rt.availableRoles.map((roleName) => (
                  <option key={roleName} value={roleName}>
                    {formatDefaultTenantAssignableRoleLabel(roleName)}
                  </option>
                ))}
              </Select>
            </FormControl>
          </VStack>
        )}
      </StandardModal>
    </Box>
  );
}
