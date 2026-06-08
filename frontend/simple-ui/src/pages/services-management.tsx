// Services Management page with list, create, view, and delete functionality

import {
  Card,
  Grid,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import ServicesTable from "../components/services-management/ServicesTable";
import ServiceCreateForm from "../components/services-management/ServiceCreateForm";
import ServiceViewDrawer from "../components/services-management/ServiceViewDrawer";
import ServicesConfirmDialogs from "../components/services-management/ServicesConfirmDialogs";
import { useServicesManagement } from "../hooks/useServicesManagement";

const ServicesManagementPage: React.FC = () => {
  const sm = useServicesManagement();

  return (
    <>
      <Head>
        <title>Services Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure services" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          <ManagementPageHeader
            title="Services Management"
            description={
              sm.isRegistryReadOnly
                ? "View services in the registry (read-only)"
                : "Manage and configure services"
            }
          />

          <Grid gap={8} w="full" mx="auto">
            <Card bg={sm.cardBg} borderColor={sm.cardBorder} borderWidth="1px">
              <Tabs
                colorScheme="blue"
                variant="enclosed"
                index={sm.activeTab}
                onChange={(index) => {
                  if (sm.isRegistryReadOnly && index === 1) return;
                  sm.setActiveTab(index);
                  if (index !== sm.viewTabIndex) {
                    sm.setIsViewingService(false);
                    sm.setSelectedService(null);
                    sm.setSelectedServiceModelDeprecated(null);
                  }
                  const q = { ...sm.router.query } as Record<string, string>;
                  if (index === 0) delete q.tab;
                  else q.tab = String(index);
                  sm.router.replace({ pathname: "/services-management", query: q }, undefined, { shallow: true });
                }}
              >
                <TabList>
                  <Tab fontWeight="semibold">Service Registry</Tab>
                  {!sm.isRegistryReadOnly && (
                    <Tab fontWeight="semibold">Create Service</Tab>
                  )}
                  {sm.isViewingService && (
                    <Tab fontWeight="semibold">View Service</Tab>
                  )}
                </TabList>

                <TabPanels>
                  <TabPanel px={0} pt={6}>
                    <ServicesTable {...sm} />
                  </TabPanel>

                  {!sm.isRegistryReadOnly && (
                    <TabPanel px={0} pt={6}>
                      <ServiceCreateForm {...sm} />
                    </TabPanel>
                  )}

                  {sm.isViewingService && sm.selectedService ? (
                    <TabPanel px={0} pt={6}>
                      <ServiceViewDrawer {...sm} />
                    </TabPanel>
                  ) : null}
                </TabPanels>
              </Tabs>
            </Card>
          </Grid>
        </VStack>
      </ContentLayout>

      <ServicesConfirmDialogs {...sm} />
    </>
  );
};

export default ServicesManagementPage;
