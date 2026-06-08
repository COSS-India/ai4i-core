// PII guardrail admin — domains, rules, tenant mappings, audit logs

import {
  Badge,
  Box,
  Card,
  CardBody,
  Heading,
  HStack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
} from "@chakra-ui/react";
import { usePiiManagement } from "./hooks/usePiiManagement";
import PiiAdminTab from "./PiiAdminTab";
import PiiAuditTab from "./PiiAuditTab";
import PiiAuditTraceModal from "./modals/PiiAuditTraceModal";
import PiiDomainDetailModal from "./modals/PiiDomainDetailModal";
import PiiMappingDetailModal from "./modals/PiiMappingDetailModal";
import PiiRuleDetailModal from "./modals/PiiRuleDetailModal";
import type { PiiManagementProps } from "./types";

export type { PiiManagementProps } from "./types";

export default function PiiManagement({ isAdmin = false }: PiiManagementProps) {
  const p = usePiiManagement(isAdmin);
  const {
    pageBg,
    cardBg,
    borderColor,
    mutedText,
    headingColor,
    tabIndex,
    setActiveTab,
    domainDetail,
    ruleDetail,
    mappingDetail,
    auditTraceDetail,
    viewDomain,
    viewRule,
    viewMapping,
    auditDetailJson,
    checkedDomains,
    editingDomainId,
    closeDomainDetail,
    closeRuleDetail,
    closeMappingDetail,
    closeAuditTraceDetail,
    loadDomainConfig,
    removeRuleForRow,
    handleDeleteTenantMapping,
  } = p;

  if (!isAdmin) {
    return (
      <Box bg={pageBg} minH="100vh" p={6}>
        <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
          <CardBody>
            <Heading size="sm" mb={2}>
              PII Management
            </Heading>
            <Text fontSize="sm" color={mutedText}>
              You do not have access to this page. Admin permissions are required.
            </Text>
          </CardBody>
        </Card>
      </Box>
    );
  }

  return (
    <Box bg={pageBg} minH="100vh" p={6}>
      <HStack justify="space-between" mb={2} flexWrap="wrap" gap={2}>
        <Box>
          <Heading size="lg" color={headingColor}>
            PII Management
          </Heading>
          <Badge colorScheme="blue" mt={2} fontSize="xs">
            Admin Console
          </Badge>
        </Box>
      </HStack>

      <Tabs
        index={tabIndex}
        onChange={(i) => setActiveTab(i === 0 ? "admin" : "audit")}
        colorScheme="blue"
        variant="enclosed"
        mt={6}
      >
        <TabList>
          <Tab fontWeight="semibold">Admin</Tab>
          <Tab fontWeight="semibold">Audit Logs</Tab>
        </TabList>
        <TabPanels>
          <TabPanel px={0} pt={6}>
            <PiiAdminTab {...p} />
          </TabPanel>
          <TabPanel px={0} pt={6}>
            <PiiAuditTab {...p} />
          </TabPanel>
        </TabPanels>
      </Tabs>

      <PiiDomainDetailModal
        isOpen={domainDetail.isOpen}
        onClose={closeDomainDetail}
        domain={viewDomain}
        isPendingActivation={viewDomain ? checkedDomains.has(viewDomain.domain_id) : false}
        onEditRules={(id) => {
          closeDomainDetail();
          void loadDomainConfig(id);
        }}
      />

      <PiiRuleDetailModal
        isOpen={ruleDetail.isOpen}
        onClose={closeRuleDetail}
        rule={viewRule}
        editingDomainId={editingDomainId}
        onRemove={(rule) => {
          removeRuleForRow(rule);
          closeRuleDetail();
        }}
      />

      <PiiMappingDetailModal
        isOpen={mappingDetail.isOpen}
        onClose={closeMappingDetail}
        mapping={viewMapping}
        onRemove={(tenantId) => void handleDeleteTenantMapping(tenantId, closeMappingDetail)}
      />

      <PiiAuditTraceModal
        isOpen={auditTraceDetail.isOpen}
        onClose={closeAuditTraceDetail}
        auditDetailJson={auditDetailJson}
      />
    </Box>
  );
}
