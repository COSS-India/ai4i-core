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

export default function PiiTypeDetailModal({
  isOpen,
  onClose,
  piiTypeId,
  onEdit,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  piiTypeId: string | null;
  onEdit: (row: PiiTypeOut) => void;
  onError: (msg: string) => void;
}) {
  const [detail, setDetail] = useState<PiiTypeOut | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !piiTypeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const run = async () => {
      try {
        const res = await policyService.getPiiType(piiTypeId);
        if (!cancelled) setDetail(res.data);
      } catch (e: unknown) {
        if (!cancelled) onError(getPolicyApiErrorMessage(e, "Failed to load PII type"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, piiTypeId, onError]);

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="PII type details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {detail ? (
            <Button
              colorScheme="blue"
              onClick={() => {
                onEdit(detail);
              }}
            >
              Edit
            </Button>
          ) : null}
        </HStack>
      }
    >
      {loading ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : detail ? (
        <Stack spacing={4}>
          <Text fontSize="xs" color="gray.500" fontFamily="mono">
            {detail.pii_type_id}
          </Text>
          <Heading size="md">{detail.pii_type_label}</Heading>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Mask format
            </Text>
            <Badge>{detail.mask_format}</Badge>
          </Box>
          <FormControl>
            <FormLabel fontSize="sm">Regex pattern</FormLabel>
            <Textarea value={detail.regex_pattern} readOnly fontFamily="mono" rows={4} />
          </FormControl>
          <Text fontSize="sm" color="gray.600">
            Created {formatDt(detail.created_at)}
          </Text>
        </Stack>
      ) : null}
    </StandardModal>
  );
}
