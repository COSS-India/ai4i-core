import { Box, Tab, TabList, TabPanel, TabPanels, Tabs } from "@chakra-ui/react";
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
      <Tabs colorScheme="blue" variant="enclosed" isLazy>
        <TabList>
          {TAB_CONFIG.map((tab) => (
            <Tab key={tab.id} fontWeight="semibold">
              {tab.label}
            </Tab>
          ))}
        </TabList>
        <TabPanels>
          <TabPanel px={0} pt={5}>
            <NotificationsCatalogTab />
          </TabPanel>
          <TabPanel px={0} pt={5}>
            <AlertsCatalogTab />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default NotificationAlertsManagement;
