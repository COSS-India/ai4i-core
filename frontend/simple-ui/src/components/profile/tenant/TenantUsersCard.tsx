import { Button, Card, CardBody, CardHeader, Heading, HStack } from "@chakra-ui/react";
import { FiUserPlus } from "react-icons/fi";
import type { UseTenantManagementTabReturn } from "../hooks/useTenantManagementTab";
import TenantUsersTable from "./TenantUsersTable";

type Props = UseTenantManagementTabReturn;

export default function TenantUsersCard(props: Props) {
  const { tm } = props;
  return (
    <Card>
      <CardHeader>
        <HStack justify="space-between" align="center">
          <Heading size="md">Tenant Users</Heading>
          <HStack>
            <Button
              leftIcon={<FiUserPlus />}
              size="sm"
              colorScheme="blue"
              onClick={tm.openUserModal}
            >
              Add User
            </Button>
          </HStack>
        </HStack>
      </CardHeader>
      <CardBody>
        <TenantUsersTable {...props} />
      </CardBody>
    </Card>
  );
}
