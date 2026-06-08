// ViewDefinitionDrawer

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
  SimpleGrid,
  Text,
  VStack,
} from "@chakra-ui/react";
import { SIGNAL_METRICS_BY_SIGNAL, TARGET_SERVICES } from "../../../../types/alerting";
import { normalizeServiceValue } from "../utils";
import type { DefinitionSectionProps } from "./types";

export default function ViewDefinitionDrawer(tab: DefinitionSectionProps) {
  const {
    defs,
    alertTypeLabel,
    formatThreshold,
    titleCase,
    severityColor,
  } = tab;

  return (
      <Drawer isOpen={defs.isViewOpen} onClose={defs.closeView} placement="right" size="md">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
            <Text fontSize="lg" fontWeight="bold">Alert Definition Details</Text>
          </DrawerHeader>
          <DrawerBody py={6}>
            {defs.viewItem && (() => {
              const v = defs.viewItem;
              const signalMetricLabel = v.signal_metric
                ? (SIGNAL_METRICS_BY_SIGNAL[v.signal ?? ""]?.find((m) => m.value === v.signal_metric)?.label
                    ?? titleCase(v.signal_metric.replace(/_/g, " ")))
                : "—";
              const signalLabel = v.signal
                ? titleCase(v.signal.replace(/_/g, " "))
                : v.alert_type ? alertTypeLabel(v.alert_type) : "—";
              const targetLabel = v.service && v.service.length > 0
                ? v.service.map((s) => TARGET_SERVICES.find((t) => t.value === normalizeServiceValue(s))?.label ?? s).join(", ")
                : "All services";
              const conditionThreshold = v.condition_operator && v.threshold_value != null
                ? `${v.condition_operator} ${v.threshold_value} ${v.threshold_unit ?? ""}`.trim()
                : formatThreshold(v);
              const DetailRow = ({ label, children }: { label: string; children: React.ReactNode }) => (
                <Box borderBottomWidth="1px" borderColor="gray.100" pb={3}>
                  <Text fontWeight="semibold" color="gray.500" fontSize="xs" textTransform="uppercase" letterSpacing="wider" mb={1}>{label}</Text>
                  {children}
                </Box>
              );
              return (
                <VStack spacing={4} align="stretch">
                  <DetailRow label="Alert Name">
                    <Text fontWeight="semibold" fontSize="md">{v.name}</Text>
                  </DetailRow>
                  <DetailRow label="Description">
                    <Text color={v.description ? "gray.800" : "gray.400"}>{v.description || "—"}</Text>
                  </DetailRow>
                  <DetailRow label="Category">
                    <Text>{titleCase(v.category)}</Text>
                  </DetailRow>
                  <DetailRow label="Severity">
                    <Badge colorScheme={severityColor(v.severity)} textTransform="capitalize" px={3} py={1} borderRadius="full" fontSize="sm">{v.severity}</Badge>
                  </DetailRow>
                  <DetailRow label="Signal">
                    <Text>{signalLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Signal Metric">
                    <Text>{signalMetricLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Target">
                    <Text>{targetLabel}</Text>
                  </DetailRow>
                  <DetailRow label="Condition & Threshold">
                    <Text fontFamily="mono" fontWeight="semibold" fontSize="md">{conditionThreshold}</Text>
                  </DetailRow>
                  <DetailRow label="Evaluation Interval">
                    <Text fontFamily="mono">{v.evaluation_interval}</Text>
                  </DetailRow>
                  <DetailRow label="For Duration">
                    <Text fontFamily="mono">{v.for_duration}</Text>
                  </DetailRow>
                  <DetailRow label="Status">
                    <Badge
                      colorScheme={v.enabled ? "green" : "gray"}
                      variant="subtle"
                      fontSize="sm"
                      px={3}
                      py={1}
                      borderRadius="full"
                    >
                      {v.enabled ? "Active" : "Inactive"}
                    </Badge>
                  </DetailRow>
                </VStack>
              );
            })()}
          </DrawerBody>
          <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
            <Button variant="outline" mr={3} onClick={() => { defs.closeView(); if (defs.viewItem) defs.openUpdate(defs.viewItem); }}>Edit</Button>
            <Button onClick={defs.closeView}>Close</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
  );
}
