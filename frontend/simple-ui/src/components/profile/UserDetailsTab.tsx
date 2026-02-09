import React from "react";
import {
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
import { TIMEZONES, LANGUAGES } from "./types";

export default function UserDetailsTab() {
  const { user, updateUser } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  const ud = useUserDetails({
    user: user ?? null,
    updateUser,
    checkSessionExpiry,
  });

  if (!user) return null;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            User Details
          </Heading>
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
      <CardBody>
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
            <Input value={user.username || "N/A"} isReadOnly bg={inputReadOnlyBg} />
            <Text fontSize="xs" color="gray.500" mt={1}>
              Username cannot be changed
            </Text>
          </FormControl>

          <FormControl>
            <FormLabel fontWeight="semibold">Email</FormLabel>
            <Input value={user.email || "N/A"} isReadOnly bg={inputReadOnlyBg} />
            <Text fontSize="xs" color="gray.500" mt={1}>
              Email cannot be changed
            </Text>
          </FormControl>

          <FormControl isInvalid={!!ud.errors.phone_number}>
            <FormLabel fontWeight="semibold">Phone Number</FormLabel>
            <Input
              value={ud.isEditingUser ? (ud.userFormData.phone_number || "") : (user.phone_number || "")}
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
            <FormControl flex={1}>
              <FormLabel fontWeight="semibold">Language</FormLabel>
              {ud.isEditingUser ? (
                <Select
                  value={ud.userFormData.language || "en"}
                  onChange={(e) => ud.handleInputChange("language", e.target.value)}
                  bg="white"
                >
                  {LANGUAGES.map((lang) => (
                    <option key={lang.value} value={lang.value}>
                      {lang.label}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  value={LANGUAGES.find((l) => l.value === user.language)?.label || user.language || "N/A"}
                  isReadOnly
                  bg={inputReadOnlyBg}
                />
              )}
            </FormControl>
          </HStack>

          <HStack spacing={4}>
            <FormControl flex={1}>
              <FormLabel fontWeight="semibold">Status</FormLabel>
              <Input value={user.is_active ? "Active" : "Inactive"} isReadOnly bg={inputReadOnlyBg} />
            </FormControl>
            <FormControl flex={1}>
              <FormLabel fontWeight="semibold">Verified</FormLabel>
              <Input value={user.is_verified ? "Yes" : "No"} isReadOnly bg={inputReadOnlyBg} />
            </FormControl>
          </HStack>

          {user.created_at && (
            <FormControl>
              <FormLabel fontWeight="semibold">Member Since</FormLabel>
              <Input
                value={new Date(user.created_at).toLocaleDateString()}
                isReadOnly
                bg={inputReadOnlyBg}
              />
            </FormControl>
          )}
        </VStack>
      </CardBody>
    </Card>
  );
}
