import React from "react";
import { Card, HStack, Tab, TabList, TabPanel, TabPanels, Tabs } from "@chakra-ui/react";
import { INSTITUTION } from "../../config/constants";
import CreateButton from "../common/CreateButton";
import ApplicationManagementTab from "./ApplicationManagementTab";
import InstitutionDetailsPanel from "./InstitutionDetailsPanel";
import { useOwnInstitutionDetails } from "./hooks/useOwnInstitutionDetails";

type OwnInstitution = ReturnType<typeof useOwnInstitutionDetails>;

export function InstitutionAdminHome({
  tabCardBg,
  tabCardBorder,
  ownInstitution,
  tenantId,
  onAddUser,
  usersTable,
}: {
  tabCardBg: string;
  tabCardBorder: string;
  ownInstitution: OwnInstitution;
  tenantId: string;
  onAddUser: () => void;
  usersTable: React.ReactNode;
}) {
  return (
    <Card bg={tabCardBg} borderColor={tabCardBorder} borderWidth="1px">
      <Tabs colorScheme="blue" variant="enclosed">
        <TabList>
          <Tab fontWeight="semibold">{`My ${INSTITUTION}`}</Tab>
          <Tab fontWeight="semibold">Users</Tab>
          <Tab fontWeight="semibold">Applications</Tab>
        </TabList>
        <TabPanels>
          <TabPanel px={6} pt={6} pb={6}>
            <InstitutionDetailsPanel
              institution={ownInstitution.institution}
              tierName={ownInstitution.tierName}
              budgetLimit={ownInstitution.budgetLimit}
              currency={ownInstitution.currency}
              isLoading={ownInstitution.isLoading}
              errorMessage={ownInstitution.errorMessage}
              tierBudgetErrorMessage={ownInstitution.tierBudgetErrorMessage}
            />
          </TabPanel>
          <TabPanel px={6} pt={6} pb={6}>
            <HStack justify="flex-end" mb={4}>
              <CreateButton onClick={onAddUser}>Add User</CreateButton>
            </HStack>
            {usersTable}
          </TabPanel>
          <TabPanel px={6} pt={6} pb={6}>
            <ApplicationManagementTab
              tenantId={tenantId}
              institutionBudget={ownInstitution.budgetLimit}
              currency={ownInstitution.currency}
            />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Card>
  );
}
