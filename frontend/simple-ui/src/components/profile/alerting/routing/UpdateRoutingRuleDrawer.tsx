// UpdateRoutingRuleDrawer

import React from "react";
import {
  Badge,
  Box,
  Button,
  Checkbox,
  Divider,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Input,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  Radio,
  RadioGroup,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  Textarea,
  Tooltip,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { LockIcon } from "@chakra-ui/icons";
import {
  CATEGORIES,
  CONDITION_OPERATORS,
  LATENCY_THRESHOLD_UNITS,
  PERCENTAGE_UNIT,
  RBAC_ROLES,
  SEVERITIES,
  SIGNAL_METRICS_BY_SIGNAL,
  SIGNALS_BY_SUB_CATEGORY,
  SUB_CATEGORIES_BY_CATEGORY,
  TARGET_SERVICES,
  URGENCIES,
} from "../../../../types/alerting";
import {
  ALERT_TYPES_BY_CATEGORY,
  EVAL_INTERVALS,
  FOR_DURATIONS,
  FORM_REQUIRED_ASTERISK,
} from "../constants";
import { getAllowedForDurations } from "../utils";
import OptionSelector from "../OptionSelector";
import type { RoutingSectionProps } from "./types";

export default function UpdateRoutingRuleDrawer(tab: RoutingSectionProps) {
  const {
    cardBg,
    cardBorder,
    defs,
    rules,
    ruleDeleteRef,
    sortedRules,
    routingRuleColumns,
    createRuleScope,
    setCreateRuleScope,
    createRuleTenant,
    setCreateRuleTenant,
    createRuleErrors,
    setCreateRuleErrors,
    tenants,
    isLoadingTenants,
    editRuleCategory,
    setEditRuleCategory,
    editRuleSeverity,
    setEditRuleSeverity,
    editRuleDef,
    setEditRuleDef,
    editRuleScope,
    setEditRuleScope,
    editRuleErrors,
    setEditRuleErrors,
    resetCreateRuleExtras,
    resetEditRuleExtras,
    fetchTenants,
    validateAndCreate,
    activeAlertDefinitions,
    titleCase,
    categoryColor,
    severityColor,
  } = tab;

  return (
      <Drawer isOpen={rules.isUpdateOpen} onClose={() => { rules.closeUpdate(); resetEditRuleExtras(); }} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Edit Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={0} align="stretch">

              {/* ── Rule Name ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!editRuleErrors.ruleName}>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Rule Name
                  </FormLabel>
                  <Input
                    value={rules.updateForm.rule_name ?? ""}
                    onChange={(e) => {
                      rules.setUpdateForm({ ...rules.updateForm, rule_name: e.target.value });
                      if (e.target.value.trim()) setEditRuleErrors((prev) => { const n = { ...prev }; delete n.ruleName; return n; });
                    }}
                    bg="white"
                    placeholder="e.g. Route Critical ASR Alerts"
                  />
                  <FormErrorMessage>{editRuleErrors.ruleName}</FormErrorMessage>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Category + Severity + Alert Definition ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Category
                  </FormLabel>
                  <OptionSelector
                    options={CATEGORIES}
                    value={editRuleCategory}
                    onChange={(v) => {
                      setEditRuleCategory(v);
                      setEditRuleDef("");
                      if (v === "infrastructure") {
                        setEditRuleScope("global");
                        rules.setUpdateForm({
                          ...rules.updateForm,
                          category: v || null,
                          alert_names: null,
                          tenant: null,
                        });
                        setEditRuleErrors((prev) => {
                          const n = { ...prev };
                          delete n.tenant;
                          return n;
                        });
                      } else {
                        rules.setUpdateForm({ ...rules.updateForm, category: v || null, alert_names: null });
                      }
                    }}
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Severity
                  </FormLabel>
                  <HStack spacing={2}>
                    {SEVERITIES.map((s) => {
                      const isActive = editRuleSeverity === s;
                      const colors = s === "critical"
                        ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
                        : s === "warning"
                        ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
                        : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };
                      return (
                        <Box
                          key={s}
                          as="button"
                          type="button"
                          flex="1"
                          py={2}
                          px={3}
                          fontSize="sm"
                          fontWeight="semibold"
                          textAlign="center"
                          cursor="pointer"
                          borderRadius="full"
                          borderWidth="2px"
                          borderColor={isActive ? colors.activeBorder : "gray.200"}
                          bg={isActive ? colors.activeBg : "white"}
                          color={isActive ? colors.activeText : "gray.500"}
                          _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
                          transition="all 0.15s"
                          onClick={() => {
                            setEditRuleSeverity(s);
                            setEditRuleDef("");
                            rules.setUpdateForm({ ...rules.updateForm, severity: s, alert_names: null });
                          }}
                          textTransform="capitalize"
                        >
                          {s}
                        </Box>
                      );
                    })}
                  </HStack>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Alert Definition</FormLabel>
                  {(() => {
                    const cat = editRuleCategory;
                    const sev = editRuleSeverity;
                    const filtered = activeAlertDefinitions.filter((d) =>
                      (!cat || d.category === cat) && (!sev || d.severity === sev)
                    );
                    const displayDefs = cat || sev ? filtered : activeAlertDefinitions;
                    return (
                      <Select
                        bg="white"
                        value={editRuleDef}
                        onChange={(e) => {
                          setEditRuleDef(e.target.value);
                          const chosen = activeAlertDefinitions.find((d) => String(d.id) === e.target.value);
                          rules.setUpdateForm({
                            ...rules.updateForm,
                            alert_names: chosen ? [chosen.name] : null,
                            category: chosen ? chosen.category : (rules.updateForm.category ?? null),
                            severity: chosen ? chosen.severity : (rules.updateForm.severity ?? null),
                          });
                        }}
                        placeholder={displayDefs.length === 0 ? "No definitions match" : `${displayDefs.length} alert definition${displayDefs.length !== 1 ? "s" : ""} affected`}
                      >
                        {displayDefs.map((d) => (
                          <option key={d.id} value={String(d.id)}>{d.name}</option>
                        ))}
                      </Select>
                    );
                  })()}
                  <Text fontSize="xs" color="gray.500" mt={1}>Filter by category/severity, then select a specific definition (optional).</Text>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Scope ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Scope
                  </FormLabel>
                  {editRuleCategory === "infrastructure" ? (
                    <>
                      <Select value="global" isDisabled bg="gray.50">
                        <option value="global">Global</option>
                      </Select>

                    </>
                  ) : (
                    <Select
                      value={editRuleScope}
                      onChange={(e) => {
                        const v = e.target.value as "global" | "specific_tenant";
                        setEditRuleScope(v);
                        if (v === "global") {
                          // Backend expects global scope to be expressed as tenant="" + rbac_role=ADMIN.
                          rules.setUpdateForm({ ...rules.updateForm, tenant: "", rbac_role: "ADMIN" });
                          setEditRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; });
                        } else {
                          rules.setUpdateForm({
                            ...rules.updateForm,
                            tenant: rules.updateItem?.tenant ?? "",
                            // Routing rules always use RBAC delivery with ADMIN.
                            rbac_role: "ADMIN",
                          });
                        }
                      }}
                      bg="white"
                    >
                      <option value="global">Global</option>
                      <option value="specific_tenant">Specific Tenant</option>
                    </Select>
                  )}
                </FormControl>
                {editRuleCategory !== "infrastructure" && editRuleScope === "specific_tenant" && (
                  <FormControl isRequired isInvalid={!!editRuleErrors.tenant}>
                    <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                      Target Tenant
                    </FormLabel>
                    <Select
                      value={
                        tenants.find(
                          (t) =>
                            t.tenant_id === rules.updateForm.tenant || t.organisation === rules.updateForm.tenant
                        )?.tenant_id ?? rules.updateForm.tenant ?? ""
                      }
                      onChange={(e) => {
                        const selectedName =
                          tenants.find((t) => t.tenant_id === e.target.value)?.organisation ?? e.target.value;
                        rules.setUpdateForm({ ...rules.updateForm, tenant: e.target.value ? selectedName : null });
                        if (e.target.value) setEditRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; });
                      }}
                      bg="white"
                      placeholder="Select tenant"
                      isDisabled={isLoadingTenants}
                    >
                      {tenants.map((t) => (
                        <option key={t.tenant_id} value={t.tenant_id}>{t.organisation || t.tenant_id}</option>
                      ))}
                    </Select>
                    <FormErrorMessage>{editRuleErrors.tenant}</FormErrorMessage>
                  </FormControl>
                )}
              </VStack>

              <Divider mb={6} />

              {/* ── Delivery Channel ── */}
              <VStack spacing={2} align="stretch" pb={6}>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Delivery Channel</FormLabel>
                  <Box
                    bg="gray.50"
                    border="1px solid"
                    borderColor="gray.200"
                    borderRadius="md"
                    px={4}
                    py={3}
                    cursor="not-allowed"
                  >
                    <HStack spacing={2}>
                      <LockIcon color="gray.400" boxSize={3} />
                      <Text fontSize="sm" color="gray.400" fontWeight="medium">Email</Text>
                    </HStack>
                  </Box>
                  <Text fontSize="xs" color="gray.500" mt={1}>Email delivery is automatically configured. Additional channels coming soon.</Text>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Status ── */}
              <VStack spacing={2} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Status
                  </FormLabel>
                  <HStack>
                    <Switch
                      isChecked={rules.updateForm.enabled ?? true}
                      onChange={(e) => rules.setUpdateForm({ ...rules.updateForm, enabled: e.target.checked })}
                      colorScheme="green"
                    />
                    <Text fontSize="sm">Enable this rule</Text>
                  </HStack>
                </FormControl>
              </VStack>

            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button
              variant="outline"
              mr={3}
              onClick={() => { rules.closeUpdate(); resetEditRuleExtras(); }}
              isDisabled={rules.isUpdating}
            >
              Cancel
            </Button>
            <Button
              colorScheme="orange"
              isLoading={rules.isUpdating}
              loadingText="Saving..."
              onClick={() => {
                const errors: Record<string, string> = {};
                const isInfrastructure = editRuleCategory === "infrastructure";
                if (!rules.updateForm.rule_name?.trim()) errors.ruleName = "Rule name is required.";
                if (!isInfrastructure && editRuleScope === "specific_tenant" && !rules.updateForm.tenant) {
                  errors.tenant = "Please select a target tenant.";
                }
                setEditRuleErrors(errors);
                if (Object.keys(errors).length > 0) return;
                rules.handleUpdate(
                  isInfrastructure
                    ? { tenant: null }
                    : undefined
                );
              }}
            >
              Save Changes
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
  );
}
