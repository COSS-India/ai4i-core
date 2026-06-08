import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  IconButton,
  SimpleGrid,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
} from "@chakra-ui/react";
import { FiArrowLeft, FiEdit2, FiMail, FiUserPlus, FiUsers } from "react-icons/fi";
import {
  TENANT,
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
  isTenantStatus,
} from "../../../config/constants";
import type { UseTenantManagementTabReturn } from "../hooks/useTenantManagementTab";
import { dash, fmtDate } from "./utils";
import TenantUsersTable from "./TenantUsersTable";

type Props = UseTenantManagementTabReturn;

export default function TenantDetailView(props: Props) {
  const { tm } = props;
  const t = tm.tenantDetailView!;
  return (
    <Card mt={4}>
      <CardHeader>
        <HStack justify="space-between" align="center">
          <HStack>
            <IconButton
              aria-label="Back"
              icon={<FiArrowLeft />}
              size="sm"
              variant="ghost"
              onClick={tm.closeTenantDetailView}
            />
            <Heading size="md">{t.organisation}</Heading>
            <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
              {formatTenantStatusLabel(t.status)}
            </Badge>
          </HStack>
          <HStack>
            {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
              <Button
                leftIcon={<FiMail />}
                size="sm"
                variant="outline"
                colorScheme="blue"
                isLoading={tm.resendVerificationTenantId === t.tenant_id}
                loadingText="Sending..."
                onClick={() => void tm.handleResendTenantVerificationEmail(t)}
              >
                Resend Verification Email
              </Button>
            )}
            <Button leftIcon={<FiEdit2 />} size="sm" onClick={() => tm.handleOpenEditTenant(t)}>
              Edit
            </Button>
            <Button
              leftIcon={<FiUserPlus />}
              size="sm"
              colorScheme="blue"
              onClick={() => tm.openAddUserForTenant(t.tenant_id)}
            >
              Add User
            </Button>
          </HStack>
        </HStack>
      </CardHeader>
      <CardBody>
        <Tabs
          index={tm.tenantDetailSubTab === "overview" ? 0 : 1}
          onChange={(idx) => tm.setTenantDetailSubTab(idx === 0 ? "overview" : "users")}
        >
          <TabList>
            <Tab>Overview</Tab>
            <Tab>
              <FiUsers style={{ marginRight: 6 }} />
              Users
            </Tab>
          </TabList>
          <TabPanels>
            <TabPanel px={0}>
              {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
                <Alert status="info" variant="left-accent" borderRadius="md" mb={4}>
                  <AlertIcon />
                  <Box flex="1">
                    <AlertDescription fontSize="sm">
                      This tenant is awaiting activation. The contact must complete the email
                      verification link. If the link expired or was not received, resend it below.
                    </AlertDescription>
                    <Button
                      mt={3}
                      size="sm"
                      leftIcon={<FiMail />}
                      colorScheme="blue"
                      variant="outline"
                      isLoading={tm.resendVerificationTenantId === t.tenant_id}
                      loadingText="Sending..."
                      onClick={() => void tm.handleResendTenantVerificationEmail(t)}
                    >
                      Resend Verification Email
                    </Button>
                  </Box>
                </Alert>
              )}
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
                <Box>
                  <Text fontWeight="semibold">Tenant ID</Text>
                  <Text fontFamily="mono">{t.tenant_id}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Status</Text>
                  <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
                    {formatTenantStatusLabel(t.status)}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Contact Name</Text>
                  <Text>{dash(t.contact_name)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Email</Text>
                  <Text>{dash(t.email)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Phone</Text>
                  <Text>{dash(t.phone_number)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Created</Text>
                  <Text>{fmtDate(t.created_at)}</Text>
                </Box>
              </SimpleGrid>
            </TabPanel>
            <TabPanel px={0}>
              <TenantUsersTable {...props} />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </CardBody>
    </Card>
  );
}
