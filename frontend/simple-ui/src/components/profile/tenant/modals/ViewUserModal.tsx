import {
  Badge,
  Box,
  Button,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Text,
  VStack,
} from "@chakra-ui/react";
import TenantUserRoleBadges from "../../../common/TenantUserRoleBadges";
import {
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  resolveTenantUserDisplayStatus,
} from "../../../../config/constants";
import type { TenantTabContext } from "../types";
import { dash } from "../utils";

type Props = TenantTabContext & { userListTenantStatus: string | null };

export default function ViewUserModal({ tm, userListTenantStatus }: Props) {
  const u = tm.viewUserDetail;
  return (
    <Modal isOpen={tm.isViewUserModalOpen} onClose={tm.closeViewUserModal} size="md">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>User Details</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          {u ? (
            <VStack align="stretch" spacing={3}>
              <Box>
                <Text fontWeight="semibold">Username</Text>
                <Text>{u.username}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold">User ID</Text>
                <Text fontFamily="mono">{u.user_id}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold">Email</Text>
                <Text>{dash(u.email)}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold">Full Name</Text>
                <Text>{dash(u.full_name)}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold">Phone</Text>
                <Text>{dash(u.phone_number)}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold">Status</Text>
                <Badge
                  colorScheme={getTenantStatusColorScheme(
                    resolveTenantUserDisplayStatus(u, userListTenantStatus),
                  )}
                >
                  {formatTenantUserStatusLabel(
                    resolveTenantUserDisplayStatus(u, userListTenantStatus),
                  )}
                </Badge>
              </Box>
              <Box>
                <Text fontWeight="semibold">Roles</Text>
                <TenantUserRoleBadges role={u.role} roles={u.roles} badgeFontSize="sm" />
              </Box>
            </VStack>
          ) : (
            <Text>No user selected.</Text>
          )}
        </ModalBody>
        <ModalFooter>
          <Button onClick={tm.closeViewUserModal}>Close</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
