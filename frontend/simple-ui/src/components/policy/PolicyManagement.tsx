import React, { useEffect, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  useToast,
  VStack,
} from "@chakra-ui/react";
import AuditPanel from "./AuditPanel";
import PiiTypesPanel from "./PiiTypesPanel";
import PoliciesPanel from "./PoliciesPanel";
import { POLICY_TAB_CONFIG, SHOW_POLICY_AUDIT_TAB, type PolicySectionId } from "./constants";
import type { PolicyManagementProps } from "./types";

export type { PolicyManagementProps } from "./types";

export default function PolicyManagement({ canManage }: PolicyManagementProps) {
  const toast = useToast();
  const [tab, setTab] = useState<PolicySectionId>("pii");

  useEffect(() => {
    if (!SHOW_POLICY_AUDIT_TAB && tab === "audit") {
      setTab("policies");
    }
  }, [tab]);

  if (!canManage) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Policy Management requires adopter admin access (ADMIN role). Tenant users cannot
        change policies here.
      </Alert>
    );
  }

  const policySubTabIndex = Math.max(
    0,
    POLICY_TAB_CONFIG.findIndex((t) => t.id === tab)
  );

  return (
    <VStack align="stretch" spacing={6}>
      <Box>
        <Tabs
          variant="unstyled"
          index={policySubTabIndex}
          onChange={(idx) => {
            const next = POLICY_TAB_CONFIG[idx];
            if (next) setTab(next.id);
          }}
          mb={6}
        >
          <TabList borderBottom="2px solid" borderColor="gray.200" aria-label="Policy Management sections">
            {POLICY_TAB_CONFIG.map(({ id, label }, idx) => (
              <Tab
                key={id}
                fontWeight="semibold"
                fontSize="md"
                color={policySubTabIndex === idx ? "gray.800" : "gray.500"}
                pb={3}
                px={5}
                position="relative"
                _after={{
                  content: '""',
                  position: "absolute",
                  bottom: "-2px",
                  left: 0,
                  right: 0,
                  height: "3px",
                  borderRadius: "3px 3px 0 0",
                  bg: policySubTabIndex === idx ? "orange.500" : "transparent",
                  transition: "background 0.2s",
                }}
                _hover={{ color: "gray.700" }}
                _focus={{ boxShadow: "none" }}
                transition="color 0.2s"
              >
                {label}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
            <TabPanel px={0} pt={6}>
              <PiiTypesPanel toast={toast} />
            </TabPanel>
            <TabPanel px={0} pt={6}>
              <PoliciesPanel toast={toast} />
            </TabPanel>
            {SHOW_POLICY_AUDIT_TAB ? (
              <TabPanel px={0} pt={6}>
                <AuditPanel toast={toast} />
              </TabPanel>
            ) : null}
          </TabPanels>
        </Tabs>
      </Box>
    </VStack>
  );
}
