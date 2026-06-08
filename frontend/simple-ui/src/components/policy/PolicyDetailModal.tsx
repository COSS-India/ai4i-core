import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  Checkbox,
  CheckboxGroup,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  Select,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
  Tooltip,
  useDisclosure,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import { useAdminTableSurface } from "../common/TableControls";
import {
  policyService,
  type AuditLogOut,
  type MaskFormat,
  type PiiTypeOut,
  type PolicyOut,
} from "../../services/policyService";
import { isTenantStatus, TENANT } from "../../config/constants";
import { listTenants } from "../../services/tenantService";
import type { TenantView } from "../../types/tenant";
import { AUDIT_PAGE_SIZE_OPTIONS, LANGUAGE_OPTIONS, MASK_OPTIONS } from "./constants";
import { formatDt, getPolicyApiErrorMessage, parseDelimitedValues, useDebouncedValue } from "./utils";

export default function PolicyDetailModal({
  isOpen,
  onClose,
  policyId,
  onEdit,
  onDelete,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  policyId: string | null;
  onEdit: (id: string) => void;
  onDelete: (policy: PolicyOut) => void;
  onError: (msg: string) => void;
}) {
  const [policy, setPolicy] = useState<PolicyOut | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !policyId) {
      setPolicy(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPolicy(policyId);
        if (!cancelled) setPolicy(res.data);
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load policy"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, policyId, onError]);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Policy details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {policyId ? (
            <>
              {policy ? (
                <Button colorScheme="red" variant="outline" onClick={() => onDelete(policy)}>
                  Delete
                </Button>
              ) : null}
              <Button
                colorScheme="blue"
                onClick={() => {
                  onEdit(policyId);
                }}
              >
                Edit
              </Button>
            </>
          ) : null}
        </HStack>
      }
    >
      {loading ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : policy ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {policy.policy_id}
          </Text>
          <Heading size="md">{policy.name}</Heading>
          {policy.description ? (
            <Text fontSize="sm" color="gray.700">
              {policy.description}
            </Text>
          ) : (
            <Text fontSize="sm" color="gray.500">
              No description
            </Text>
          )}
          <HStack spacing={2} flexWrap="wrap">
            <Badge colorScheme={policy.is_active ? "green" : "gray"}>
              {policy.is_active ? "Active" : "Inactive"}
            </Badge>
            <Badge colorScheme={policy.is_global ? "blue" : "purple"}>
              {policy.is_global ? "Global" : "Tenant-scoped"}
            </Badge>
          </HStack>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Tenants
            </Text>
            <Text fontSize="sm">
              {policy.is_global
                ? "All tenants"
                : (policy.tenant_ids?.length ?? 0) > 0
                  ? policy.tenant_ids!.join(", ")
                  : "—"}
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              PII types ({policy.pii_types?.length ?? 0})
            </Text>
            <Stack spacing={1}>
              {(policy.pii_types ?? []).map((p) => (
                <Text key={p.pii_type_id} fontSize="sm">
                  {p.pii_type_label}{" "}
                  <Text as="span" color="gray.500">
                    ({p.mask_format})
                  </Text>
                </Text>
              ))}
              {!policy.pii_types?.length && (
                <Text fontSize="sm" color="gray.500">
                  None linked
                </Text>
              )}
            </Stack>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Languages
            </Text>
            <Text fontSize="sm">{policy.supported_languages?.join(", ") || "—"}</Text>
          </Box>
          <Text fontSize="sm" color="gray.600">
            Created {formatDt(policy.created_at)}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}
