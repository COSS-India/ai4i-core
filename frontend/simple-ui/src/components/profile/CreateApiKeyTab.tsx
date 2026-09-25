import React from "react";
import {
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  Input,
  IconButton,
  HStack,
  Text,
  VStack,
  Alert,
  AlertIcon,
  AlertDescription,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
  Center,
  Spinner,
  Select,
} from "@chakra-ui/react";
import { CopyIcon, CloseIcon } from "@chakra-ui/icons";
import { useCreateApiKeyTab } from "./hooks/useCreateApiKeyTab";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { FIELD_HINTS } from "../../config/fieldHints";
import { percentageBoundMessage } from "../../config/budgetMessages";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import PercentageStepper from "../common/PercentageStepper";
import { formatPermissionLabel } from "../../utils/apiKeyUtils";

export interface CreateApiKeyTabProps {
  tenantId?: string | null;
  onApiKeyCreated?: () => void;
  onCancel?: () => void;
  hideActions?: boolean;
  formId?: string;
  onCreatingChange?: (creating: boolean) => void;
  /** True while the one-time API key token is on screen. */
  onCreatedTokenChange?: (visible: boolean) => void;
}

export default function CreateApiKeyTab({
  tenantId,
  onApiKeyCreated,
  onCancel,
  hideActions = false,
  formId,
  onCreatingChange,
  onCreatedTokenChange,
}: CreateApiKeyTabProps) {
  const create = useCreateApiKeyTab({ tenantId, onApiKeyCreated });
  const { copy } = useCopyToClipboard();
  const [budgetBoundHint, setBudgetBoundHint] = React.useState<string | null>(null);

  React.useEffect(() => {
    onCreatingChange?.(create.isCreating);
  }, [create.isCreating, onCreatingChange]);

  React.useEffect(() => {
    onCreatedTokenChange?.(Boolean(create.createdApiKeyToken));
  }, [create.createdApiKeyToken, onCreatedTokenChange]);

  const isLoading = create.isLoadingPermissions || create.isLoadingApplications;
  const budgetError = create.fieldErrors.budget || budgetBoundHint;

  return (
    <form
      id={formId}
      onSubmit={(e) => {
        e.preventDefault();
        void create.handleCreateApiKey();
      }}
    >
      {isLoading ? (
        <Center py={8}>
          <Spinner size="lg" />
        </Center>
      ) : (
          <VStack spacing={4} align="stretch">
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
                  <HStack justify="space-between" align="flex-start" mb={2}>
                    <Text fontWeight="bold">
                      API Key Created — Copy it now!
                    </Text>
                    <IconButton
                      aria-label="Dismiss"
                      icon={<CloseIcon />}
                      size="xs"
                      variant="ghost"
                      onClick={create.clearCreatedApiKeyToken}
                    />
                  </HStack>
                  <Text fontSize="xs" color="ink.600" mb={2}>
                    This token will not be shown again. Store it securely. The modal stays open until you close it.
                  </Text>
                  <HStack align="stretch" spacing={2}>
                    <Input
                      value={create.createdApiKeyToken}
                      isReadOnly
                      fontFamily="mono"
                      fontSize="xs"
                      bg="white"
                    />
                    <Button
                      size="sm"
                      flexShrink={0}
                      leftIcon={<CopyIcon />}
                      onClick={() => {
                        void copy(
                          create.createdApiKeyToken!,
                          "API key copied to clipboard",
                        );
                      }}
                    >
                      Copy
                    </Button>
                  </HStack>
                </Box>
              </Alert>
            )}

            <FormControl isRequired>
              <FieldLabel>Key Name</FieldLabel>
              <Input
                value={create.apiKeyForm.key_name}
                onChange={(e) =>
                  create.setApiKeyForm({ ...create.apiKeyForm, key_name: e.target.value })
                }
                placeholder={FIELD_HINTS.apiKey.keyName.placeholder}
                bg="white"
                maxLength={100}
              />
              <FieldHint>{FIELD_HINTS.apiKey.keyName.helper}</FieldHint>
            </FormControl>

            <FormControl isRequired isInvalid={Boolean(create.fieldErrors.application_id)}>
              <FieldLabel>Application</FieldLabel>
              <Select
                value={create.apiKeyForm.application_id}
                onChange={(e) => {
                  setBudgetBoundHint(null);
                  create.clearFieldError("application_id");
                  create.clearFieldError("budget");
                  create.setApiKeyForm({
                    ...create.apiKeyForm,
                    application_id: e.target.value,
                    allocated_percentage: "",
                  });
                }}
                placeholder="Select Application"
                bg="white"
              >
                {create.applications.map((app) => (
                  <option key={app.application_id} value={app.application_id}>
                    {app.name}
                  </option>
                ))}
              </Select>
              <FieldHint show={!create.fieldErrors.application_id}>
                {FIELD_HINTS.apiKey.application.helper}
              </FieldHint>
              <FormErrorMessage>{create.fieldErrors.application_id}</FormErrorMessage>
            </FormControl>

            <FormControl isRequired>
              <FieldLabel>Permissions</FieldLabel>
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
                        isRequired={false}
                      >
                        <Text fontSize="sm" fontWeight="semibold">
                          Select All
                        </Text>
                      </Checkbox>
                      <Text fontSize="xs" color="ink.500">
                        {create.selectedPermissions.length}/{create.permissions.length} selected
                      </Text>
                    </HStack>
                  </Box>
                  <SimpleGrid columns={2} spacing={3}>
                    {create.permissions.map((p) => (
                      <Checkbox key={p.name} value={p.name} colorScheme="blue" isRequired={false}>
                        <Text fontSize="sm">{formatPermissionLabel(p.label)}</Text>
                      </Checkbox>
                    ))}
                  </SimpleGrid>
                </CheckboxGroup>
              </Box>
              <FieldHint>{FIELD_HINTS.apiKey.permissions.helper}</FieldHint>
            </FormControl>

            <FormControl isRequired isInvalid={Boolean(budgetError)}>
              <FieldLabel>
                Budget Allocation{" "}
                <Text as="span" fontWeight="normal" color="ink.500" fontSize="sm">
                  (% of the Application&apos;s Budget)
                </Text>
              </FieldLabel>
              <PercentageStepper
                value={create.apiKeyForm.allocated_percentage}
                onChange={(next) => {
                  setBudgetBoundHint(null);
                  create.clearFieldError("budget");
                  create.setApiKeyForm({
                    ...create.apiKeyForm,
                    allocated_percentage: next,
                  });
                }}
                placeholder={FIELD_HINTS.apiKey.budget.placeholder}
                onBoundHit={(bound) => setBudgetBoundHint(percentageBoundMessage(bound))}
              />
              <FieldHint show={!budgetError}>
                {FIELD_HINTS.apiKey.budget.helper}
                {create.apiKeyForm.application_id &&
                create.selectedApplication?.allocated_budget != null
                  ? create.uncappedHoldsRemainder
                    ? " An existing key without a percentage allocation is holding this Application's remaining Budget — give that key an explicit Budget before creating another."
                    : ` Up to ${create.formatAvailablePct()}% available within this Application.`
                  : ""}
              </FieldHint>
              {create.budgetPreview && (
                <Text fontSize="sm" color="blue.600" mt={2} fontWeight="semibold">
                  ≈ {create.budgetPreview} of Application budget
                </Text>
              )}
              {budgetError && (
                <FormErrorMessage>{budgetError}</FormErrorMessage>
              )}
            </FormControl>

            <FormControl isRequired>
              <FieldLabel>Expiry (Days)</FieldLabel>
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

            {!hideActions && (
            <FormActions
              submitLabel="Create API Key"
              onCancel={onCancel}
              hideCancel={!onCancel}
              onSubmit={create.handleCreateApiKey}
              isLoading={create.isCreating}
              loadingText="Creating..."
              justify="space-between"
              pt={0}
            />
            )}
          </VStack>
      )}
    </form>
  );
}
