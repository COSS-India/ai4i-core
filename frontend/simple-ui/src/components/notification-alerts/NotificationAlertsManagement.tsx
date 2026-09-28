import {
  Box,
  Heading,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
} from "@chakra-ui/react";
import React, { useState } from "react";
import { INSTITUTION } from "../../config/constants";
import AlertsCatalogTab from "./AlertsCatalogTab";
import InstitutionCatalogTab from "./InstitutionCatalogTab";
import NotificationsCatalogTab from "./NotificationsCatalogTab";

export type NotificationAlertsView = "adopter" | "institution";

const ADOPTER_TABS = [
  {
    id: "notifications" as const,
    label: "Notifications Catalog",
    description:
      "Set the scope for each notification — Global notifications reach every Institution Admin automatically with no opt-out; Institution notifications are subscribable. Choose whether a copy should also reach the Adopter Admin, then submit.",
  },
  {
    id: "alerts" as const,
    label: "Alerts Catalog",
    description:
      "Set the scope and threshold values for each alert. Global alerts always reach every Institution Admin; Institution alerts are subscribable. Edit threshold values, select which ones should trigger an email, then submit.",
  },
] as const;

const INSTITUTION_TABS = [
  {
    id: "notifications" as const,
    label: "Notifications Catalog",
    description: `Mandatory notifications always reach you and can't be turned off. For the rest, subscribe or unsubscribe, and choose who else in your ${INSTITUTION.toLowerCase()} should also receive them.`,
  },
  {
    id: "alerts" as const,
    label: "Alerts Catalog",
    description: `Mandatory alerts always reach you and can't be turned off. For the rest, subscribe or unsubscribe, and choose who else in your ${INSTITUTION.toLowerCase()} should also receive them, alongside the threshold values your Adopter Admin has configured.`,
  },
] as const;

interface NotificationAlertsManagementProps {
  /** "adopter" edits the catalog; "institution" manages its own subscriptions. */
  view?: NotificationAlertsView;
}

const NotificationAlertsManagement: React.FC<NotificationAlertsManagementProps> = ({
  view = "adopter",
}) => {
  const [tabIndex, setTabIndex] = useState(0);
  const tabs = view === "institution" ? INSTITUTION_TABS : ADOPTER_TABS;
  const activeTab = tabs[tabIndex];

  return (
    <Box
      bg="white"
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius="14px"
      pt={5}
    >
      <Box px={6} mb={4}>
        <Heading as="h2" size="sm" mb={1}>
          {activeTab.label}
        </Heading>
        <Text color="ink.600" fontSize="sm" maxW="4xl">
          {activeTab.description}
        </Text>
      </Box>
      <Tabs colorScheme="blue" isLazy index={tabIndex} onChange={setTabIndex}>
        <TabList px={6}>
          {tabs.map((tab) => (
            <Tab key={tab.id} fontWeight="semibold">
              {tab.label}
            </Tab>
          ))}
        </TabList>
        <TabPanels>
          <TabPanel px={6} pt={5} pb={6}>
            {view === "institution" ? (
              <InstitutionCatalogTab
                type="NOTIFICATION"
                entityLabel="notification"
                nameColumnHeader="Notification"
                emptyMessage="No notifications match your filters."
              />
            ) : (
              <NotificationsCatalogTab />
            )}
          </TabPanel>
          <TabPanel px={6} pt={5} pb={6}>
            {view === "institution" ? (
              <InstitutionCatalogTab
                type="ALERT"
                entityLabel="alert"
                nameColumnHeader="Alert"
                emptyMessage="No alerts match your filters."
                showThresholds
              />
            ) : (
              <AlertsCatalogTab />
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default NotificationAlertsManagement;
