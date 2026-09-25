import React from "react";
import {
  Box,
  FormControl,
  FormErrorMessage,
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
import { canEditOwnProfile } from "../../utils/rbac";
import { useUserDetails } from "./hooks/useUserDetails";
import { TIMEZONES } from "./types";
import DeleteAccountSection from "./DeleteAccountSection";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";

export default function UserDetailsTab() {
  const { user, updateUser } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const inputReadOnlyBg = useColorModeValue("ink.50", "ink.700");
  const sectionBg = useColorModeValue("ink.50", "ink.900");
  const sectionBorder = useColorModeValue("ink.200", "ink.700");

  const ud = useUserDetails({
    user: user ?? null,
    updateUser,
    checkSessionExpiry,
  });

  if (!user) return null;

  const canEdit = canEditOwnProfile(user.roles);

  return (
    <Box>
      <HStack justify="space-between" align="flex-start" mb={4}>
        <Box>
          <Heading size="md" color="ink.800" userSelect="none" cursor="default">
            User Details
          </Heading>
          <Text fontSize="sm" color="ink.600" mt={1}>
            {canEdit
              ? "Manage your profile information and preferences."
              : "View your profile information."}
          </Text>
        </Box>
        {canEdit &&
          (!ud.isEditingUser ? (
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
                onClick={ud.handleSaveUser}
                isLoading={ud.isSaving}
                loadingText="Saving..."
                isDisabled={!ud.canSaveUser}
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
          ))}
      </HStack>
      <VStack spacing={5} align="stretch">
          <Box bg={sectionBg} borderWidth="1px" borderColor={sectionBorder} borderRadius="md" p={4}>
            <VStack spacing={4} align="stretch">
          <FormControl
            isRequired={ud.isEditingUser}
            isInvalid={ud.isEditingUser && !!ud.errors.full_name}
          >
            <FieldLabel>Full Name</FieldLabel>
            <Input
              value={ud.isEditingUser ? (ud.userFormData.full_name || "") : (user.full_name || user.username || "N/A")}
              isReadOnly={!ud.isEditingUser}
              onChange={(e) => ud.handleInputChange("full_name", e.target.value)}
              bg={ud.isEditingUser ? "white" : inputReadOnlyBg}
              placeholder={FIELD_HINTS.profile.fullName.placeholder}
            />
            <FieldHint show={ud.isEditingUser && !ud.errors.full_name}>
              {FIELD_HINTS.profile.fullName.helper}
            </FieldHint>
            <FormErrorMessage>{ud.errors.full_name}</FormErrorMessage>
          </FormControl>

          <FormControl>
            <FieldLabel>Username</FieldLabel>
            <Text fontSize="md" color="ink.700" py={1}>
              {user.username || "N/A"}
            </Text>
            <FieldHint>{FIELD_HINTS.profile.usernameLocked}</FieldHint>
          </FormControl>

          <FormControl>
            <FieldLabel>Email</FieldLabel>
            <Text fontSize="md" color="ink.700" py={1}>
              {user.email || "N/A"}
            </Text>
            <FieldHint>{FIELD_HINTS.profile.emailLocked}</FieldHint>
          </FormControl>

          <FormControl isInvalid={!!ud.errors.phone_number}>
            <FieldLabel>Phone Number</FieldLabel>
            <Input
              value={
                ud.isEditingUser
                  ? (ud.userFormData.phone_number || "")
                  : (user.phone_number || "")
              }
              isReadOnly={!ud.isEditingUser}
              onChange={(e) => ud.handleInputChange("phone_number", e.target.value)}
              bg={ud.isEditingUser ? "white" : inputReadOnlyBg}
              placeholder={FIELD_HINTS.profile.phone.placeholder}
              type="tel"
            />
            <FieldHint show={ud.isEditingUser && !ud.errors.phone_number}>
              {FIELD_HINTS.profile.phone.helper}
            </FieldHint>
            <FormErrorMessage>{ud.errors.phone_number}</FormErrorMessage>
          </FormControl>

          <HStack spacing={4}>
            <FormControl flex={1}>
              <FieldLabel>Timezone</FieldLabel>
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
              <FieldHint>{FIELD_HINTS.profile.timezone.helper}</FieldHint>
            </FormControl>
          </HStack>
            </VStack>
          </Box>

          {user.created_at && (
            <FormControl>
              <FieldLabel>Account Created On</FieldLabel>
              <Text fontSize="md" color="ink.700" py={1}>
                {new Date(user.created_at).toLocaleDateString()}
              </Text>
            </FormControl>
          )}

          <DeleteAccountSection user={user} />
        </VStack>
    </Box>
  );
}
