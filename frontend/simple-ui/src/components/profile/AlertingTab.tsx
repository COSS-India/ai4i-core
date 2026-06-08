// Alerting tab — definitions, routing rules, and history

import { Box, Tab, TabList, TabPanel, TabPanels, Tabs, VStack } from "@chakra-ui/react";
import AlertDefinitionsSection from "./alerting/AlertDefinitionsSection";
import AlertHistorySection from "./alerting/AlertHistorySection";
import AlertRoutingSection from "./alerting/AlertRoutingSection";
import { useAlertingTab } from "./hooks/useAlertingTab";

export interface AlertingTabProps {
  isActive?: boolean;
}

export default function AlertingTab({ isActive = false }: AlertingTabProps) {
  const tab = useAlertingTab({ isActive });
  const { subTabIndex, setSubTabIndex } = tab;

  return (
    <Box>
      <Tabs variant="unstyled" index={subTabIndex} onChange={setSubTabIndex} mb={6}>
        <TabList borderBottom="2px solid" borderColor="gray.200">
          {["Alert Definitions", "Alert Routing", "Alert History"].map((label, idx) => (
            <Tab
              key={label}
              fontWeight="semibold"
              fontSize="md"
              color={subTabIndex === idx ? "gray.800" : "gray.500"}
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
                bg: subTabIndex === idx ? "orange.500" : "transparent",
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
            <AlertDefinitionsSection {...tab} />
          </TabPanel>
          <TabPanel px={0} pt={6}>
            <VStack spacing={8} align="stretch">
              <AlertRoutingSection {...tab} />
            </VStack>
          </TabPanel>
          <TabPanel px={0} pt={6}>
            <AlertHistorySection {...tab} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
