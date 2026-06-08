// ViewRoutingRuleDrawer

import React from "react";
import {
  Badge,
  Box,
  Button,
  Divider,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  HStack,
  SimpleGrid,
  Text,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { LockIcon } from "@chakra-ui/icons";
import type { RoutingSectionProps } from "./types";

export default function ViewRoutingRuleDrawer(tab: RoutingSectionProps) {
  const {
    rules,
    defs,
    activeAlertDefinitions,
    titleCase,
    categoryColor,
    severityColor,
    fetchTenants,
    resetEditRuleExtras,
    initEditRuleExtras,
  } = tab;

  return (
      <Drawer isOpen={rules.isViewOpen} onClose={rules.closeView} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">View Routing Rule</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            {rules.viewItem && (() => {
              const item = rules.viewItem;
              const firstName = item.alert_names?.[0];
              const linkedDef = firstName
                ? (defs.definitions.find((d) => d.name === firstName) ?? null)
                : null;
              const category = item.category ?? linkedDef?.category ?? null;
              const severity = item.severity ?? linkedDef?.severity ?? null;
              const sevColors =
                severity === "critical" ? { bg: "red.100", color: "red.700", border: "red.300" }
                : severity === "warning" ? { bg: "yellow.100", color: "yellow.700", border: "yellow.300" }
                : severity === "info" ? { bg: "blue.100", color: "blue.700", border: "blue.300" }
                : { bg: "gray.100", color: "gray.600", border: "gray.300" };
              const catColor = category === "application" ? "orange" : category === "infrastructure" ? "purple" : "gray";
              return (
                <VStack spacing={0} align="stretch">

                  {/* Rule Name */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={1}>Rule Name</Text>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.800">{item.rule_name ?? item.receiver_name}</Text>
                  </Box>

                  <Divider mb={5} />

                  {/* Category + Severity */}
                  <SimpleGrid columns={2} spacing={5} pb={5}>
                    <Box>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Category</Text>
                      {category ? (
                        <Badge colorScheme={catColor} variant="subtle" textTransform="capitalize" fontSize="xs" px={2} py={0.5} borderRadius="full">{category}</Badge>
                      ) : (
                        <Text fontSize="sm" color="gray.400">—</Text>
                      )}
                    </Box>
                    <Box>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Severity</Text>
                      {severity ? (
                        <Box
                          display="inline-block"
                          bg={sevColors.bg}
                          color={sevColors.color}
                          fontSize="xs"
                          fontWeight="semibold"
                          px={2}
                          py={0.5}
                          borderRadius="full"
                          textTransform="capitalize"
                          border="1px solid"
                          borderColor={sevColors.border}
                        >{severity}</Box>
                      ) : (
                        <Text fontSize="sm" color="gray.400">—</Text>
                      )}
                    </Box>
                  </SimpleGrid>

                  {/* Alert Definition */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Alert Definition</Text>
                    {item.alert_names && item.alert_names.length > 0 ? (
                      <VStack spacing={1} align="stretch">
                        {item.alert_names.map((name) => (
                          <Text key={name} fontSize="sm" color="gray.700">{name}</Text>
                        ))}
                      </VStack>
                    ) : (() => {
                      const matchCount = defs.definitions.filter(
                        (d) => (!category || d.category === category) && (!severity || d.severity === severity)
                      ).length;
                      const hasFilter = category || severity;
                      return (
                        <HStack spacing={2}>
                          <Text fontSize="sm" color="gray.500">
                            {hasFilter
                              ? `All matching definitions`
                              : "All definitions"}
                          </Text>
                          {matchCount > 0 && (
                            <Badge colorScheme="gray" variant="subtle" fontSize="xs">{matchCount}</Badge>
                          )}
                        </HStack>
                      );
                    })()}
                  </Box>

                  <Divider mb={5} />

                  {/* Scope */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Scope</Text>
                    {item.tenant ? (
                      <HStack spacing={1.5}>
                        <Text fontSize="sm" color="gray.700" fontWeight="medium">Specific Tenant</Text>
                        <Text fontSize="sm" color="gray.400">—</Text>
                        <Badge colorScheme="purple" variant="subtle" textTransform="none" fontSize="xs">{item.tenant}</Badge>
                      </HStack>
                    ) : (
                      <HStack spacing={1.5}>
                        <Badge colorScheme="gray" variant="subtle" fontSize="xs" textTransform="none">Global</Badge>
                        <Text fontSize="xs" color="gray.400">All tenants</Text>
                      </HStack>
                    )}
                  </Box>

                  {/* Notify — only show when there is meaningful recipient info */}
                  {((item.rbac_role && item.tenant) || (item.email_to && item.email_to.length > 0)) && (
                    <Box pb={5}>
                      <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Notify</Text>
                      {item.rbac_role && item.tenant ? (
                        <HStack spacing={1.5}>
                          <Badge colorScheme="blue" variant="subtle" fontSize="xs" textTransform="capitalize">{item.rbac_role}</Badge>
                          <Text fontSize="sm" color="gray.400">—</Text>
                          <Text fontSize="sm" color="gray.600" fontWeight="medium">{item.tenant}</Text>
                        </HStack>
                      ) : (
                        <Wrap spacing={1}>
                          {(item.email_to ?? []).map((e) => (
                            <WrapItem key={e}><Badge colorScheme="blue" variant="subtle" fontSize="xs">{e}</Badge></WrapItem>
                          ))}
                        </Wrap>
                      )}
                    </Box>
                  )}

                  <Divider mb={5} />

                  {/* Delivery Channel */}
                  <Box pb={5}>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Delivery Channel</Text>
                    <HStack spacing={2}>
                      <LockIcon color="gray.400" boxSize={3} />
                      <Text fontSize="sm" color="gray.700" fontWeight="medium">Email</Text>
                    </HStack>
                  </Box>

                  {/* Status */}
                  <Box>
                    <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wide" mb={2}>Status</Text>
                    <Badge
                      colorScheme={item.enabled ? "green" : "gray"}
                      variant="subtle"
                      fontSize="xs"
                      px={2}
                      py={0.5}
                      borderRadius="full"
                    >{item.enabled ? "Active" : "Inactive"}</Badge>
                  </Box>

                </VStack>
              );
            })()}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => {
                rules.closeView();
                if (rules.viewItem) {
                  defs.fetchDefinitions();
                  fetchTenants();
                  resetEditRuleExtras();
                  initEditRuleExtras(rules.viewItem);
                  rules.openUpdate(rules.viewItem);
                }
              }}>Edit</Button>
            <Button onClick={rules.closeView}>Close</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
  );
}
