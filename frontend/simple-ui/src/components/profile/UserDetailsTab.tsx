import React from "react";
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  Input,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Button,
  Select,
} from "@chakra-ui/react";
import { FiEdit2, FiCheck, FiX } from "react-icons/fi";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import { useUserDetails } from "./hooks/useUserDetails";
import { TIMEZONES } from "./types";
import { maskPhoneForDisplay } from "../../utils/helpers";

export default function UserDetailsTab() {
  const { user, updateUser } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");
  const sectionBg = useColorModeValue("gray.50", "gray.900");
  const sectionBorder = useColorModeValue("gray.100", "gray.700");

  const ud = useUserDetails({
    user: user ?? null,
    updateUser,
    checkSessionExpiry,
  });

  if (!user) return null;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader pb={3}>
        <HStack justify="space-between" align="flex-start">
          <Box>
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              User Details
            </Heading>
            <Text fontSize="sm" color="gray.500" mt={1}>
              Manage your profile information and preferences.
            </Text>
          </Box>
          {!ud.isEditingUser ? (
            <Button
              leftIcon={<FiEdit2 />}
              size="sm"
              colorScheme="blue"
              variant="outline"
              onClick={ud.handleEditUser}
            >
              Edit
            </Button>
          ) : (
            <HStack>
              <Button
                leftIcon={<FiCheck />}
                size="sm"
                colorScheme="green"
                onClick={ud.handleSaveUser}
                isLoading={ud.isSaving}
                loadingText="Saving..."
              >
                Save
              </Button>
              <Button
                leftIcon={<FiX />}
                size="sm"
                variant="outline"
                onClick={ud.handleCancelEdit}
                isDisabled={ud.isSaving}
              >
                Cancel
              </Button>
            </HStack>
          )}
        </HStack>
      </CardHeader>
      <CardBody pt={2}>
        <VStack spacing={5} align="stretch">
          <Box bg={sectionBg} borderWidth="1px" borderColor={sectionBorder} borderRadius="md" p={4}>
            <VStack spacing={4} align="stretch">
          <FormControl>
            <FormLabel fontWeight="semibold">Full Name</FormLabel>
            <Input
              value={ud.isEditingUser ? (ud.userFormData.full_name || "") : (user.full_name || user.username || "N/A")}
              isReadOnly={!ud.isEditingUser}
              onChange={(e) => ud.handleInputChange("full_name", e.target.value)}
              bg={ud.isEditingUser ? "white" : inputReadOnlyBg}
              placeholder="Enter your full name"
            />
          </FormControl>

          <FormControl>
            <FormLabel fontWeight="semibold">Username</FormLabel>
            <Text fontSize="md" color="gray.700" py={1}>
              {user.username || "N/A"}
            </Text>
            <Text fontSize="xs" color="gray.500" mt={1}>
              Username cannot be changed
            </Text>
          </FormControl>

          <FormControl>
            <FormLabel fontWeight="semibold">Email</FormLabel>
            <Text fontSize="md" color="gray.700" py={1}>
              {user.email || "N/A"}
            </Text>
            <Text fontSize="xs" color="gray.500" mt={1}>
              Email cannot be changed
            </Text>
          </FormControl>

          <FormControl isInvalid={!!ud.errors.phone_number}>
            <FormLabel fontWeight="semibold">Phone Number</FormLabel>
            <Input
              value={ud.isEditingUser ? (ud.userFormData.phone_number || "") : maskPhoneForDisplay(user.phone_number)}
              isReadOnly={!ud.isEditingUser}
              onChange={(e) => ud.handleInputChange("phone_number", e.target.value)}
              bg={ud.isEditingUser ? "white" : inputReadOnlyBg}
              placeholder="+91XXXXXXXXXX or XXXXXXXXXX"
              type="tel"
            />
            {ud.isEditingUser && !ud.errors.phone_number && (
              <Text fontSize="xs" color="gray.500" mt={1}>
                Enter a valid Indian mobile number (10 digits starting with 6-9)
              </Text>
            )}
            {ud.errors.phone_number && (
              <Text color="red.500" fontSize="sm" mt={1}>
                {ud.errors.phone_number}
              </Text>
            )}
          </FormControl>

          <HStack spacing={4}>
            <FormControl flex={1}>
              <FormLabel fontWeight="semibold">Timezone</FormLabel>
              {ud.isEditingUser ? (
                <Select
                  value={ud.userFormData.timezone || "UTC"}
                  onChange={(e) => ud.handleInputChange("timezone", e.target.value)}
                  bg="white"
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input value={user.timezone || "N/A"} isReadOnly bg={inputReadOnlyBg} />
              )}
            </FormControl>
          </HStack>
            </VStack>
          </Box>

          {user.created_at && (
            <FormControl>
              <FormLabel fontWeight="semibold">Account Created On</FormLabel>
              <Text fontSize="md" color="gray.700" py={1}>
                {new Date(user.created_at).toLocaleDateString()}
              </Text>
            </FormControl>
          )}
        </VStack>
      </CardBody>
    </Card>
  );
}
