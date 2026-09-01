import React from "react";
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  Input,
  InputGroup,
  InputRightElement,
  IconButton,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Button,
  Alert,
  AlertIcon,
  AlertDescription,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
  Center,
  Spinner,
  Select,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
} from "@chakra-ui/react";
import { CopyIcon, CloseIcon } from "@chakra-ui/icons";
import { useCreateApiKeyTab } from "./hooks/useCreateApiKeyTab";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";

function PercentageStepper({
  value,
  onChange,
  min = 0,
  max = 100,
}: {
  value: string;
  onChange: (next: string) => void;
  min?: number;
  max?: number;
}) {
  const numeric = value.trim() === "" ? null : Number(value);
  const atMin = numeric != null && Number.isFinite(numeric) && numeric <= min + 1e-6;
  const atMax = numeric != null && Number.isFinite(numeric) && numeric >= max - 1e-6;

  return (
    <HStack maxW="180px" spacing={2} align="center">
      <NumberInput
        value={value}
        onChange={(next) => onChange(next)}
        min={min}
        max={max}
        step={1}
        precision={2}
        clampValueOnBlur
        bg="white"
        w="120px"
      >
        <NumberInputField placeholder={FIELD_HINTS.apiKey.budget.placeholder} />
        <NumberInputStepper>
          <NumberIncrementStepper cursor={atMax ? "not-allowed" : undefined} />
          <NumberDecrementStepper cursor={atMin || numeric == null ? "not-allowed" : undefined} />
        </NumberInputStepper>
      </NumberInput>
      <Text color="gray.500" fontWeight="semibold">%</Text>
    </HStack>
  );
}

export interface CreateApiKeyTabProps {
  tenantId?: string | null;
  onApiKeyCreated?: () => void;
}

export default function CreateApiKeyTab({
  tenantId,
  onApiKeyCreated,
}: CreateApiKeyTabProps) {
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const create = useCreateApiKeyTab({ tenantId, onApiKeyCreated });
  const { copy } = useCopyToClipboard();

  const isLoading = create.isLoadingPermissions || create.isLoadingApplications;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Create API Key
        </Heading>
      </CardHeader>
      <CardBody>
        {isLoading ? (
          <Center py={8}>
            <Spinner size="lg" color="blue.500" />
          </Center>
        ) : (
          <VStack spacing={6} align="stretch">
            {create.formBannerError && (
              <Alert status="error" borderRadius="md" variant="left-accent">
                <AlertIcon />
                <AlertDescription>{create.formBannerError}</AlertDescription>
              </Alert>
            )}

            {create.createdApiKeyToken && (
              <Alert status="warning" borderRadius="md" variant="left-accent">
                <AlertIcon />
                <Box flex="1">
                  <Text fontWeight="bold" mb={2}>
                    API Key Created — Copy it now!
                  </Text>
                  <Text fontSize="xs" color="gray.600" mb={2}>
                    This token will not be shown again. Store it securely.
                  </Text>
                  <InputGroup size="sm">
                    <Input
                      value={create.createdApiKeyToken}
                      isReadOnly
                      fontFamily="mono"
                      fontSize="xs"
                      pr="4rem"
                    />
                    <InputRightElement width="4rem">
                      <HStack spacing={0}>
                        <IconButton
                          aria-label="Copy API key"
                          icon={<CopyIcon />}
                          size="xs"
                          onClick={() => {
                            void copy(
                              create.createdApiKeyToken!,
                              "API key copied to clipboard",
                            );
                          }}
                        />
                        <IconButton
                          aria-label="Dismiss"
                          icon={<CloseIcon />}
                          size="xs"
                          variant="ghost"
                          onClick={create.clearCreatedApiKeyToken}
                        />
                      </HStack>
                    </InputRightElement>
                  </InputGroup>
                </Box>
              </Alert>
            )}

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Key Name</FormLabel>
              <Input
                value={create.apiKeyForm.key_name}
                onChange={(e) =>
                  create.setApiKeyForm({ ...create.apiKeyForm, key_name: e.target.value })
                }
                placeholder="Enter a name for this API key"
                bg="white"
              />
            </FormControl>

            <FormControl isRequired isInvalid={Boolean(create.fieldErrors.application_id)}>
              <FormLabel fontWeight="semibold">Application</FormLabel>
              <Select
                value={create.apiKeyForm.application_id}
                onChange={(e) =>
                  create.setApiKeyForm({
                    ...create.apiKeyForm,
                    application_id: e.target.value,
                    allocated_percentage: "",
                  })
                }
                placeholder="Select Application"
                bg="white"
              >
                {create.applications.map((app) => (
                  <option key={app.application_id} value={app.application_id}>
                    {app.name}
                  </option>
                ))}
              </Select>
              <FieldHint>{FIELD_HINTS.apiKey.application.helper}</FieldHint>
              {create.fieldErrors.application_id && (
                <FormErrorMessage>{create.fieldErrors.application_id}</FormErrorMessage>
              )}
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Permissions</FormLabel>
              <FieldHint mb={3} mt={0} fontSize="sm">
                {FIELD_HINTS.apiKey.permissions.helper}
              </FieldHint>
              <Box borderWidth="1px" borderRadius="md" p={4} bg="white" maxH="300px" overflowY="auto">
                <CheckboxGroup
                  value={create.selectedPermissions}
                  onChange={(values) => create.setSelectedPermissions(values as string[])}
                >
                  <Box mb={3} pb={3} borderBottomWidth="1px">
                    <HStack justify="space-between" align="center">
                      <Checkbox
                        isChecked={
                          create.selectedPermissions.length === create.permissions.length &&
                          create.permissions.length > 0
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            create.setSelectedPermissions(create.permissions.map((p) => p.name));
                          } else {
                            create.setSelectedPermissions([]);
                          }
                        }}
                        colorScheme="blue"
                      >
                        <Text fontSize="sm" fontWeight="semibold">
                          Select All
                        </Text>
                      </Checkbox>
                      <Text fontSize="xs" color="gray.500">
                        {create.selectedPermissions.length}/{create.permissions.length} selected
                      </Text>
                    </HStack>
                  </Box>
                  <SimpleGrid columns={2} spacing={3}>
                    {create.permissions.map((p) => (
                      <Checkbox key={p.name} value={p.name} colorScheme="blue">
                        <Text fontSize="sm">{p.label}</Text>
                      </Checkbox>
                    ))}
                  </SimpleGrid>
                </CheckboxGroup>
              </Box>
            </FormControl>

            <FormControl isInvalid={Boolean(create.fieldErrors.budget)}>
              <FormLabel fontWeight="semibold">
                Budget Allocation{" "}
                <Text as="span" fontWeight="normal" color="gray.500" fontSize="sm">
                  (optional — % of the Application&apos;s Budget)
                </Text>
              </FormLabel>
              <PercentageStepper
                value={create.apiKeyForm.allocated_percentage}
                onChange={(next) =>
                  create.setApiKeyForm({
                    ...create.apiKeyForm,
                    allocated_percentage: next,
                  })
                }
                max={create.availablePct}
              />
              <FieldHint>
                {FIELD_HINTS.apiKey.budget.helper}
                {create.apiKeyForm.application_id
                  ? ` Up to ${create.formatAvailablePct()}% available within this Application.`
                  : ""}
              </FieldHint>
              {create.budgetPreview && (
                <Text fontSize="sm" color="blue.600" mt={2} fontWeight="semibold">
                  ≈ {create.budgetPreview} of Application budget
                </Text>
              )}
              {create.fieldErrors.budget && (
                <FormErrorMessage>{create.fieldErrors.budget}</FormErrorMessage>
              )}
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Expiry (Days)</FormLabel>
              <Input
                type="number"
                value={create.apiKeyForm.expires_days === "" ? "" : create.apiKeyForm.expires_days}
                onChange={(e) => {
                  const raw = e.target.value;
                  const next =
                    raw === ""
                      ? ""
                      : (() => {
                          const n = Number.parseInt(raw, 10);
                          return Number.isNaN(n) ? "" : n;
                        })();
                  create.setApiKeyForm({ ...create.apiKeyForm, expires_days: next });
                }}
                min={1}
                max={365}
                bg="white"
                placeholder={FIELD_HINTS.apiKey.expiry.placeholder}
                maxW="160px"
              />
              <FieldHint>{FIELD_HINTS.apiKey.expiry.helper}</FieldHint>
            </FormControl>

            <Button
              colorScheme="blue"
              alignSelf="flex-start"
              onClick={create.handleCreateApiKey}
              isLoading={create.isCreating}
              loadingText="Creating..."
            >
              Create API Key
            </Button>
          </VStack>
        )}
      </CardBody>
    </Card>
  );
}
