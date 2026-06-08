// Model Management page with list and create functionality

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
import { ModelConfirmDialog } from "../components/model-management/ModelConfirmDialog";
import { ModelCreateForm } from "../components/model-management/ModelCreateForm";
import { ModelViewDrawer } from "../components/model-management/ModelViewDrawer";
import { ModelsTable } from "../components/model-management/ModelsTable";
import { useModelManagement } from "../hooks/useModelManagement";

const ModelManagementPage: React.FC = () => {
  const modelManagement = useModelManagement();
  const {
    isRegistryReadOnly,
    activeTab,
    setActiveTab,
    viewTabIndex,
    isViewingModel,
    selectedModel,
    setIsViewingModel,
    setSelectedModel,
    router,
    cardBg,
    cardBorder,
  } = modelManagement;

  return (
    <>
      <Head>
        <title>Model Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure AI models" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          <ManagementPageHeader
            title="Model Management"
            description={
              isRegistryReadOnly
                ? "View models in the registry (read-only)"
                : "Manage and configure AI models"
            }
          />

          <Grid gap={8} w="full" mx="auto">
            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
              <Tabs
                colorScheme="blue"
                variant="enclosed"
                index={activeTab}
                onChange={(index) => {
                  if (isRegistryReadOnly && index === 1) return;
                  setActiveTab(index);
                  if (index !== viewTabIndex) {
                    setIsViewingModel(false);
                    setSelectedModel(null);
                  }
                  const q = { ...router.query } as Record<string, string>;
                  if (index === 0) delete q.tab;
                  else q.tab = String(index);
                  router.replace({ pathname: "/model-management", query: q }, undefined, {
                    shallow: true,
                  });
                }}
              >
                <TabList>
                  <Tab fontWeight="semibold">Model Registry</Tab>
                  {!isRegistryReadOnly && <Tab fontWeight="semibold">Register Model</Tab>}
                  {isViewingModel && selectedModel && (
                    <Tab fontWeight="semibold">View Model</Tab>
                  )}
                </TabList>

                <TabPanels>
                  <TabPanel px={0} pt={6}>
                    <ModelsTable {...modelManagement} />
                  </TabPanel>

                  {!isRegistryReadOnly && (
                    <TabPanel px={0} pt={6}>
                      <ModelCreateForm {...modelManagement} />
                    </TabPanel>
                  )}

                  {isViewingModel && selectedModel && (
                    <TabPanel px={0} pt={6}>
                      <ModelViewDrawer {...modelManagement} />
                    </TabPanel>
                  )}
                </TabPanels>
              </Tabs>
            </Card>
          </Grid>
        </VStack>
      </ContentLayout>

      <ModelConfirmDialog {...modelManagement} />
    </>
  );
};

export default ModelManagementPage;
