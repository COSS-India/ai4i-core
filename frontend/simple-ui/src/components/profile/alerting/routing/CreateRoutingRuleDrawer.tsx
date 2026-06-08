// CreateRoutingRuleDrawer

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

export default function CreateRoutingRuleDrawer(tab: RoutingSectionProps) {
  const {
    cardBg,
    cardBorder,
    defs,
    rules,
    ruleDeleteRef,
    sortedRules,
    routingRuleColumns,
    createRuleDef,
    setCreateRuleDef,
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
      <Drawer isOpen={rules.isCreateOpen} onClose={() => { rules.closeCreate(); resetCreateRuleExtras(); }} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Create Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            <VStack spacing={0} align="stretch">

              {/* ── Rule Name + Description ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!createRuleErrors.ruleName}>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Rule Name
                  </FormLabel>
                  <Input
                    placeholder="e.g. Route Critical ASR Alerts"
                    value={rules.createForm.rule_name}
                    onChange={(e) => { rules.setCreateForm({ ...rules.createForm, rule_name: e.target.value }); if (e.target.value.trim()) setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.ruleName; return n; }); }}
                    bg="white"
                  />
                  <FormErrorMessage>{createRuleErrors.ruleName}</FormErrorMessage>
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Category + Severity + Alert Definition ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!createRuleErrors.category}>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Category
                  </FormLabel>
                  <OptionSelector
                    options={CATEGORIES}
                    value={rules.createForm.category ?? ""}
                    onChange={(v) => {
                      rules.setCreateForm({ ...rules.createForm, category: v });
                      if (v === "infrastructure") {
                        setCreateRuleScope("global");
                        setCreateRuleTenant("");
                        setCreateRuleErrors((prev) => {
                          const n = { ...prev };
                          delete n.category;
                          delete n.tenant;
                          return n;
                        });
                      } else {
                        setCreateRuleErrors((prev) => {
                          const n = { ...prev };
                          delete n.category;
                          return n;
                        });
                      }
                    }}
                  />
                  <FormErrorMessage>{createRuleErrors.category}</FormErrorMessage>
                </FormControl>
                <FormControl isRequired isInvalid={!!createRuleErrors.severity}>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Severity
                  </FormLabel>
                  <HStack spacing={2}>
                    {SEVERITIES.map((s) => {
                      const isActive = rules.createForm.severity === s;
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
                          onClick={() => { rules.setCreateForm({ ...rules.createForm, severity: s }); setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.severity; return n; }); }}
                          textTransform="capitalize"
                        >
                          {s}
                        </Box>
                      );
                    })}
                  </HStack>
                  <FormErrorMessage>{createRuleErrors.severity}</FormErrorMessage>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">Alert Definitions</FormLabel>
                  {(() => {
                    const cat = rules.createForm.category;
                    const sev = rules.createForm.severity;
                    const hasFilter = !!cat && !!sev;
                    const matchingDefs = activeAlertDefinitions.filter((d) =>
                      (!cat || d.category === cat) &&
                      (!sev || d.severity === sev)
                    );
                    return (
                      <Select
                        bg="white"
                        value={createRuleDef}
                        isDisabled={!hasFilter}
                        onChange={(e) => setCreateRuleDef(e.target.value)}
                        placeholder={!hasFilter ? "Select Category and Severity first" : matchingDefs.length === 0 ? "No definitions match" : `${matchingDefs.length} alert definition${matchingDefs.length !== 1 ? "s" : ""} affected`}
                      >
                        {matchingDefs.map((d) => (
                          <option key={d.id} value={String(d.id)}>{d.name}</option>
                        ))}
                      </Select>
                    );
                  })()}
                </FormControl>
              </VStack>

              <Divider mb={6} />

              {/* ── Scope ── */}
              <VStack spacing={4} align="stretch" pb={6}>
                <FormControl isRequired isInvalid={!!createRuleErrors.scope}>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Scope
                  </FormLabel>
                  {rules.createForm.category === "infrastructure" ? (
                    <>
                      <Select value="global" isDisabled bg="gray.50">
                        <option value="global">Global</option>
                      </Select>

                    </>
                  ) : (
                    <Select
                      value={createRuleScope}
                      onChange={(e) => {
                        setCreateRuleScope(e.target.value as "" | "global" | "specific_tenant");
                        setCreateRuleTenant("");
                        setCreateRuleErrors((prev) => {
                          const n = { ...prev };
                          delete n.scope;
                          delete n.tenant;
                          return n;
                        });
                      }}
                      bg="white"
                      placeholder="Select scope"
                    >
                      <option value="global">Global</option>
                      <option value="specific_tenant">Specific Tenant</option>
                    </Select>
                  )}
                  <FormErrorMessage>{createRuleErrors.scope}</FormErrorMessage>
                </FormControl>
                {rules.createForm.category !== "infrastructure" && createRuleScope === "specific_tenant" && (
                  <FormControl isRequired isInvalid={!!createRuleErrors.tenant}>
                    <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                      Target Tenant
                    </FormLabel>
                    <Select
                      value={createRuleTenant}
                      onChange={(e) => { setCreateRuleTenant(e.target.value); if (e.target.value) setCreateRuleErrors((prev) => { const n = { ...prev }; delete n.tenant; return n; }); }}
                      bg="white"
                      placeholder="Select tenant"
                      isDisabled={isLoadingTenants}
                    >
                      {tenants.map((t) => (
                        <option key={t.tenant_id} value={t.tenant_id}>{t.organisation || t.tenant_id}</option>
                      ))}
                    </Select>
                    <FormErrorMessage>{createRuleErrors.tenant}</FormErrorMessage>
                  </FormControl>
                )}
              </VStack>

              <Divider mb={6} />

              {/* ── Delivery Channel ── */}
              <VStack spacing={2} align="stretch" pb={6}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
                    Delivery Channel
                  </FormLabel>
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

            </VStack>
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => { rules.closeCreate(); resetCreateRuleExtras(); }} isDisabled={rules.isCreating}>Cancel</Button>
            <Button colorScheme="orange" onClick={validateAndCreate} isLoading={rules.isCreating} loadingText="Saving...">Save Routing Rule</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
  );
}
