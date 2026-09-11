import { Box, Tab, TabList, TabPanel, TabPanels, Tabs, Text } from "@chakra-ui/react";
import React from "react";
import AlertsCatalogTab from "./AlertsCatalogTab";
import NotificationsCatalogTab from "./NotificationsCatalogTab";

const TAB_CONFIG = [
  { id: "notifications" as const, label: "Notifications Catalog" },
  { id: "alerts" as const, label: "Alerts Catalog" },
] as const;

const NotificationAlertsManagement: React.FC = () => {
  return (
    <Box>
      <Tabs colorScheme="blue" isLazy>
        <TabList>
          {TAB_CONFIG.map((tab) => (
            <Tab key={tab.id}>{tab.label}</Tab>
          ))}
        </TabList>
        <TabPanels>
          <TabPanel px={0} pt={5}>
            <Text color="gray.600" fontSize="sm" mb={4}>
              The standard, event-driven notification types available on the platform.
              Set recipient roles and enablement, then Submit.
            </Text>
            <NotificationsCatalogTab />
          </TabPanel>
          <TabPanel px={0} pt={5}>
            <Text color="gray.600" fontSize="sm" mb={4}>
              The standard, threshold-based alert types available on the platform.
              Set recipient roles and thresholds, then Submit.
            </Text>
            <AlertsCatalogTab />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default NotificationAlertsManagement;
