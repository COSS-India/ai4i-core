import { Button, Card, CardBody, CardHeader, Heading, HStack } from "@chakra-ui/react";
import { FiPlus } from "react-icons/fi";
import AdminDataTable, { TableSearchField, TableSelectField } from "../../common/AdminDataTable";
import {
  TENANT_STATUS_LIST,
  formatTenantStatusLabel,
} from "../../../config/constants";
import type { UseTenantManagementTabReturn } from "../hooks/useTenantManagementTab";

type Props = UseTenantManagementTabReturn;

export default function TenantAdopterView({ tm, tenantColumns }: Props) {
  return (
    <Card>
      <CardHeader>
        <HStack justify="space-between" align="center">
          <Heading size="md">Tenants</Heading>
          <HStack>
            <Button
              leftIcon={<FiPlus />}
              size="sm"
              colorScheme="blue"
              onClick={tm.openTenantModal}
            >
              Create Tenant
            </Button>
          </HStack>
        </HStack>
      </CardHeader>
      <CardBody>
        <AdminDataTable
          items={tm.filteredTenants}
          columns={tenantColumns}
          getRowKey={(t) => t.tenant_id}
          onRowClick={tm.handleViewTenant}
          isLoading={tm.isLoadingTenants}
          emptyMessage="No tenants found."
          noResultsMessage="No tenants match the current filters."
          unfilteredCount={tm.tenants.length}
          hasActiveFilters={
            tm.tenantFilterStatus !== "all" || tm.tenantSearch.trim() !== ""
          }
          onClearFilters={() => {
            tm.setTenantFilterStatus("all");
            tm.setTenantSearch("");
          }}
          filters={
            <>
              <TableSearchField
                placeholder="Search by organisation or tenant ID"
                value={tm.tenantSearch}
                onChange={tm.setTenantSearch}
              />
              <TableSelectField
                label="Status"
                value={tm.tenantFilterStatus}
                onChange={tm.setTenantFilterStatus}
                formControlProps={{ w: { base: "full", sm: "200px" } }}
              >
                <option value="all">All statuses</option>
                {TENANT_STATUS_LIST.map((s) => (
                  <option key={s} value={s}>
                    {formatTenantStatusLabel(s)}
                  </option>
                ))}
              </TableSelectField>
            </>
          }
        />
      </CardBody>
    </Card>
  );
}
