import { useEffect, useState } from "react";
import {
  Alert,
  AlertIcon,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
} from "@chakra-ui/react";
import { INSTITUTION } from "../../config/constants";
import { AuditPanel } from "./AuditPanel";
import { PiiTypesPanel } from "./PiiTypesPanel";
import { PoliciesPanel } from "./PoliciesPanel";

/** Set to `true` to show the Audit log tab again. */
const SHOW_POLICY_AUDIT_TAB = false;

const POLICY_TAB_CONFIG = SHOW_POLICY_AUDIT_TAB
  ? ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
      { id: "audit" as const, label: "Audit log" },
    ] as const)
  : ([
      { id: "pii" as const, label: "PII type library" },
      { id: "policies" as const, label: "Policy definitions" },
    ] as const);

type PolicySectionId = (typeof POLICY_TAB_CONFIG)[number]["id"];

export interface PolicyManagementProps {
  /** Platform admin (ADMIN role or superuser); required to call policy APIs. */
  canManage: boolean;
  onRegisterCreatePolicy?: (open: () => void) => void;
}

export default function PolicyManagement({
  canManage,
  onRegisterCreatePolicy,
}: PolicyManagementProps) {
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
        Policy Management requires adopter admin access (ADMIN role). {INSTITUTION} users cannot
        change policies here.
      </Alert>
    );
  }

  const policySubTabIndex = Math.max(
    0,
    POLICY_TAB_CONFIG.findIndex((t) => t.id === tab)
  );

  return (
    <Tabs
          variant="enclosed"
          colorScheme="blue"
          index={policySubTabIndex}
          onChange={(idx) => {
            const next = POLICY_TAB_CONFIG[idx];
            if (next) setTab(next.id);
          }}
        >
          <TabList aria-label="Policy Management sections">
            {POLICY_TAB_CONFIG.map(({ id, label }) => (
              <Tab key={id} fontWeight="semibold">
                {label}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
            <TabPanel px={0} pt={6}>
              <PiiTypesPanel />
            </TabPanel>
            <TabPanel px={0} pt={6}>
              <PoliciesPanel
                onRegisterCreate={onRegisterCreatePolicy}
              />
            </TabPanel>
            {SHOW_POLICY_AUDIT_TAB ? (
              <TabPanel px={0} pt={6}>
                <AuditPanel />
              </TabPanel>
            ) : null}
          </TabPanels>
        </Tabs>
  );
}
