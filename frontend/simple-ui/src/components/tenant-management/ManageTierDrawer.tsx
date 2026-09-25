import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  HStack,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FIELD_HINTS } from "../../config/fieldHints";
import type { TenantView } from "../../types/tenant";
import type { Tier } from "../../types/tierManagement";
import {
  budgetWindowToMinDate,
  todayDateInputValue,
} from "../../utils/helpers";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import TierSelect from "../profile/TierSelect";

type ManageTierDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  manageTenant: TenantView | null;
  managePlanError: string | null;
  isEditingTier: boolean;
  setIsEditingTier: (editing: boolean) => void;
  originalTierId: string;
  manageTierId: string;
  setManageTierId: (tierId: string) => void;
  tierOptions: Tier[];
  serviceMappingsReady: boolean;
  tierIdsWithServices: Set<string>;
  onCancelTierEdit: () => void;
  noServicesMessage: string;
  manageBudget: number;
  manageEffectiveFrom: string;
  manageEffectiveTo: string;
  setManageEffectiveTo: (value: string) => void;
  setWindowError: (value: string | null) => void;
  windowError: string | null;
  budgetAction: "topup" | "topdown";
  setBudgetAction: (action: "topup" | "topdown") => void;
  budgetAmount: string;
  setBudgetAmount: (value: string) => void;
  onApplyBudget: () => void;
  originalEffectiveTo: string;
  onSave: () => void;
  isSavingPlan: boolean;
  servicesLoading: boolean;
  servicesError: boolean;
  planExpired: boolean;
};

export default function ManageTierDrawer({
  isOpen,
  onClose,
  manageTenant,
  managePlanError,
  isEditingTier,
  setIsEditingTier,
  originalTierId,
  manageTierId,
  setManageTierId,
  tierOptions,
  serviceMappingsReady,
  tierIdsWithServices,
  onCancelTierEdit,
  noServicesMessage,
  manageBudget,
  manageEffectiveFrom,
  manageEffectiveTo,
  setManageEffectiveTo,
  setWindowError,
  windowError,
  budgetAction,
  setBudgetAction,
  budgetAmount,
  setBudgetAmount,
  onApplyBudget,
  originalEffectiveTo,
  onSave,
  isSavingPlan,
  servicesLoading,
  servicesError,
  planExpired,
}: ManageTierDrawerProps) {
  const hasTierChanged = manageTierId !== originalTierId;
  const manageTierHasNoServices =
    !!manageTierId &&
    serviceMappingsReady &&
    !tierIdsWithServices.has(String(manageTierId));

  // PATCH /tenants/{id}/tier accepts tier_id only — Save when the tier changes.
  const showSaveButton = isEditingTier && hasTierChanged && !!manageTierId;

  const selectedTierName =
    tierOptions.find((t) => t.id === manageTierId)?.name ?? "";
  const planDrawerTitle = manageTenant?.tier_id ? "Manage Tier" : "Assign Tier";
  // From is read-only throughout Manage Tier, so manageEffectiveFrom is
  // always the From in effect and Effective To is the only lever.
  const effectiveToMin = manageEffectiveFrom
    ? budgetWindowToMinDate(manageEffectiveFrom, todayDateInputValue())
    : undefined;
  // Until To clears that floor the window is still lapsed, and a budget
  // revision has no live window to attach to.
  const windowNeedsExtension =
    planExpired &&
    (!manageEffectiveTo ||
      !effectiveToMin ||
      manageEffectiveTo < effectiveToMin);

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      placement="right"
      size="md"
    >
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton />
        <DrawerHeader borderBottomWidth="1px" borderColor="ink.200">
          <VStack align="flex-start" spacing={1}>
            <Text fontSize="md" fontWeight="semibold">
              {`${planDrawerTitle}${manageTenant ? ` — ${manageTenant.organisation}` : ""}`}
            </Text>
            {planExpired && (
              <Badge colorScheme="red" textTransform="none" fontSize="xs">
                Budget expired
              </Badge>
            )}
          </VStack>
        </DrawerHeader>
        <DrawerBody py={6}>
          {manageTenant ? (
            <VStack align="stretch" spacing={5}>
              {managePlanError && (
                <Alert status="error" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    {managePlanError}
                  </AlertDescription>
                </Alert>
              )}
              <FormControl>
                <FieldLabel>Tier</FieldLabel>
                {!isEditingTier && originalTierId ? (
                  <HStack>
                    <Input
                      value={selectedTierName || originalTierId}
                      isReadOnly
                      bg="ink.50"
                      flex={1}
                    />

                    <Button size="sm" onClick={() => setIsEditingTier(true)}>
                      Change Tier
                    </Button>
                  </HStack>
                ) : (
                  <HStack align="flex-start">
                    <TierSelect
                      value={manageTierId}
                      onChange={setManageTierId}
                      tierOptions={tierOptions}
                      serviceMappingsReady={serviceMappingsReady}
                      tierIdsWithServices={tierIdsWithServices}
                      fallbackName={selectedTierName || manageTierId}
                      isInvalid={manageTierHasNoServices}
                      flex={1}
                    />

                    {originalTierId && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={onCancelTierEdit}
                      >
                        Cancel
                      </Button>
                    )}
                  </HStack>
                )}
                {isEditingTier && manageTierHasNoServices && (
                  <FieldHint tone="error">{noServicesMessage}</FieldHint>
                )}
              </FormControl>

              <FormControl>
                <FieldLabel formLabelProps={{ fontWeight: "semibold", fontSize: "sm" }}>
                  Current budget (₹)
                </FieldLabel>
                <Input
                  size="sm"
                  value={manageBudget.toLocaleString("en-IN")}
                  isReadOnly
                  bg="ink.50"
                  cursor="default"
                />
              </FormControl>

              <HStack spacing={4} align="flex-start">
                <FormControl>
                  <FieldLabel formLabelProps={{ fontWeight: "semibold", fontSize: "sm" }}>
                    Budget Effective From
                  </FieldLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={manageEffectiveFrom}
                    isReadOnly
                    bg="ink.50"
                    cursor="default"
                    sx={{
                      "&::-webkit-calendar-picker-indicator": {
                        display: "none",
                      },
                    }}
                  />
                </FormControl>

                <FormControl>
                  <FieldLabel formLabelProps={{ fontWeight: "semibold", fontSize: "sm" }}>
                    Budget Effective To
                  </FieldLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={manageEffectiveTo}
                    min={effectiveToMin}
                    onChange={(e) => {
                      setManageEffectiveTo(e.target.value);
                      setWindowError(null);
                    }}
                  />
                </FormControl>
              </HStack>

              {windowError && (
                <Alert status="error" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    {windowError}
                  </AlertDescription>
                </Alert>
              )}
              <FormControl>
                <Box
                  borderWidth="1px"
                  borderRadius="md"
                  borderColor="ink.200"
                  p={3}
                  bg="ink.50"
                >
                  <HStack justify="space-between" mb={3}>
                    <Text
                      fontSize="sm"
                      fontWeight="medium"
                      color={windowNeedsExtension ? "ink.400" : undefined}
                    >
                      Adjust Budget
                    </Text>

                    <HStack spacing={0}>
                      <Button
                        size="xs"
                        variant={
                          budgetAction === "topup" ? "solid" : "outline"
                        }
                        colorScheme="green"
                        borderRightRadius={0}
                        isDisabled={windowNeedsExtension}
                        onClick={() => setBudgetAction("topup")}
                      >
                        + Top-up
                      </Button>

                      <Button
                        size="xs"
                        variant={
                          budgetAction === "topdown" ? "solid" : "outline"
                        }
                        colorScheme="red"
                        borderLeftRadius={0}
                        isDisabled={windowNeedsExtension}
                        onClick={() => setBudgetAction("topdown")}
                      >
                        - Top-down
                      </Button>
                    </HStack>
                  </HStack>

                  <HStack>
                    <Input
                      placeholder="Amount in ₹"
                      type="number"
                      value={budgetAmount}
                      isDisabled={windowNeedsExtension}
                      onChange={(e) => setBudgetAmount(e.target.value)}
                    />

                    <Button
                      colorScheme="blue"
                      onClick={onApplyBudget}
                      isDisabled={
                        windowNeedsExtension ||
                        (!budgetAmount &&
                          manageEffectiveTo === originalEffectiveTo)
                      }
                    >
                      Apply
                    </Button>
                  </HStack>
                </Box>

                <FieldHint mt={3}>
                  {FIELD_HINTS.tenant.planAppliesImmediately}
                </FieldHint>
              </FormControl>
            </VStack>
          ) : (
            <Text>Select an institution to manage its tier.</Text>
          )}
        </DrawerBody>
        <DrawerFooter
          justifyContent="space-between"
          borderTopWidth="1px"
          borderColor="ink.200"
        >
          {showSaveButton && (
            <Button
              colorScheme="blue"
              onClick={onSave}
              isLoading={isSavingPlan}
              loadingText="Saving..."
              isDisabled={
                !manageTierId ||
                manageTierHasNoServices ||
                servicesLoading ||
                servicesError
              }
            >
              {originalTierId ? "Change Tier" : "Assign Tier"}
            </Button>
          )}
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
