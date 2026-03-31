import React, { useRef } from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
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
  Select,
  Badge,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useRolesTab } from "./hooks/useRolesTab";
import UserSearchableSelect from "../common/UserSearchableSelect";

export interface RolesTabProps {
  users: import("../../types/auth").User[];
  isLoadingUsers: boolean;
}

export default function RolesTab({ users, isLoadingUsers }: RolesTabProps) {
  const { user } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  const rt = useRolesTab({
    user: user ?? null,
    users,
    isLoadingUsers,
  });
  const cancelRef = useRef<HTMLButtonElement>(null);

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
          <HStack justify="space-between">
            <Text fontSize="sm" color="gray.600">
              Manage user roles and permissions
            </Text>
            <Button
              size="sm"
              colorScheme="blue"
              onClick={rt.handleLoadRoles}
              isLoading={rt.isLoadingRoles}
              loadingText="Loading..."
            >
              Load Roles
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
                Current Roles for {rt.selectedUser.username}
              </Heading>
              {rt.isLoadingUserRoles ? (
                <Center py={4}>
                  <Spinner size="md" color="blue.500" />
                </Center>
              ) : rt.selectedUserRoles.length > 0 ? (
                <VStack spacing={2} align="stretch">
                  {rt.selectedUserRoles.map((roleName) => (
                    <HStack
                      key={roleName}
                      justify="space-between"
                      p={3}
                      bg={inputReadOnlyBg}
                      borderRadius="md"
                    >
                      <Badge colorScheme="green" fontSize="sm" p={1}>
                        {roleName}
                      </Badge>
                    </HStack>
                  ))}
                </VStack>
              ) : (
                <Alert status="info" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>This user has no roles assigned.</AlertDescription>
                </Alert>
              )}
            </Box>
          )}

          {rt.selectedUser && rt.roles.length > 0 && rt.isAdmin && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Assign Role to {rt.selectedUser.username}
              </Heading>
              <VStack spacing={4} align="stretch">
                <FormControl>
                  <FormLabel fontWeight="semibold">Select Role</FormLabel>
                  <Select
                    value={rt.selectedRole}
                    onChange={(e) => rt.setSelectedRole(e.target.value)}
                    placeholder="Select a role to assign to this user"
                    bg="white"
                  >
                    {rt.roles
                      .filter((role) => !rt.selectedUserRoles.includes(role.name))
                      .map((role) => (
                        <option key={role.id} value={role.name}>
                          {role.name} - {role.description || "No description"}
                        </option>
                      ))}
                  </Select>
                  {rt.selectedUserRoles.length > 0 && (
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      Only showing roles not already assigned to this user
                    </Text>
                  )}
                </FormControl>
                <Button
                  colorScheme="green"
                  onClick={rt.openAssignConfirm}
                  isLoading={rt.isAssigningRole}
                  loadingText="Assigning..."
                  isDisabled={!rt.selectedRole || rt.isModeratorOnly}
                >
                  Assign Role
                </Button>
              </VStack>
            </Box>
          )}

          {rt.roles.length > 0 && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Available Roles
              </Heading>
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>Role Name</Th>
                      <Th>Description</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {rt.roles.map((role) => (
                      <Tr key={role.id}>
                        <Td>
                          <Badge colorScheme="blue" fontSize="sm" p={1}>
                            {role.name}
                          </Badge>
                        </Td>
                        <Td>
                          <Text fontSize="sm" color="gray.600">
                            {role.description || "No description"}
                          </Text>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
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

      <AlertDialog
        isOpen={rt.isAssignConfirmOpen}
        leastDestructiveRef={cancelRef}
        onClose={rt.closeAssignConfirm}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Assign role to user
            </AlertDialogHeader>
            <AlertDialogBody>
              <Text>
                Are you sure you want to assign the role <strong>{rt.selectedRole}</strong> to{" "}
                <strong>{rt.selectedUser?.username}</strong>? This will update the user&apos;s permissions.
              </Text>
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={cancelRef}
                onClick={rt.closeAssignConfirm}
                isDisabled={rt.isAssigningRole}
              >
                Cancel
              </Button>
              <Button
                colorScheme="green"
                onClick={rt.handleConfirmAssignRole}
                ml={3}
                isLoading={rt.isAssigningRole}
                loadingText="Assigning..."
              >
                Confirm
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Card>
  );
}
