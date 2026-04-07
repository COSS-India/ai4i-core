import React from "react";
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Button,
  Badge,
  Select,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useRolesTab } from "./hooks/useRolesTab";
import UserSearchableSelect from "../common/UserSearchableSelect";
import StandardModal from "../common/StandardModal";

export interface RolesTabProps {
  users: import("../../types/auth").User[];
  isLoadingUsers: boolean;
}

export default function RolesTab({ users, isLoadingUsers }: RolesTabProps) {
  const { user } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const rt = useRolesTab({
    user: user ?? null,
    users,
    isLoadingUsers,
  });
  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            Role-Based Access Control (RBAC)
          </Heading>
          {rt.isModeratorOnly && (
            <Badge colorScheme="orange" fontSize="sm" p={2}>
              View Only
            </Badge>
          )}
        </HStack>
      </CardHeader>
      <CardBody>
        <VStack spacing={6} align="stretch">
          <HStack justify="space-between" align="flex-start">
            <Text fontSize="sm" color="gray.600">
              Manage user roles and permissions
            </Text>
            <Button
              size="sm"
              colorScheme="blue"
              onClick={rt.openManageRoles}
              isDisabled={!rt.selectedUser || !rt.isAdmin || rt.isModeratorOnly || rt.isLoadingUserRoles}
            >
              Manage Roles
            </Button>
          </HStack>

          <Box>
           
            <FormControl>
              <FormLabel fontWeight="semibold">User</FormLabel>
              <UserSearchableSelect
                variant="pick"
                value={rt.selectedUser?.id ?? null}
                onChange={(id, picked) => rt.handleUserSelect(id, picked)}
                seedUsers={users}
                isLoading={isLoadingUsers}
                isDisabled={isLoadingUsers}
                placeholder={isLoadingUsers ? "Loading users..." : "Select a user"}
                selectedPreview={rt.selectedUser}
                allowClear
              />
            
            </FormControl>
          </Box>

          {rt.selectedUser && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Current Role for {rt.selectedUser.username}
              </Heading>
              {rt.isLoadingUserRoles ? (
                <Center py={4}>
                  <Spinner size="md" color="blue.500" />
                </Center>
              ) : rt.selectedUserRoles.length > 0 ? (
                <Wrap spacing={2}>
                  {rt.selectedUserRoles.map((roleName) => (
                    <WrapItem key={roleName}>
                      <Badge colorScheme="green" fontSize="sm" px={2} py={1}>
                        {roleName}
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
      </CardBody>

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
            <Text fontSize="sm" color="gray.600">
              Select role for this user.
            </Text>
            <FormControl>
              <FormLabel fontWeight="semibold" fontSize="sm">Role</FormLabel>
              <Select
                value={rt.draftRole}
                onChange={(e) => rt.setDraftRole(e.target.value)}
                isDisabled={rt.isSavingRoles || !rt.isAdmin || rt.isModeratorOnly}
                bg="white"
                size="sm"
              >
                <option value="">Select role</option>
                {rt.availableRoles.map((roleName) => (
                  <option key={roleName} value={roleName}>
                    {roleName}
                  </option>
                ))}
              </Select>
            </FormControl>
          </VStack>
        )}
      </StandardModal>
    </Card>
  );
}
