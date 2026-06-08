import {
  Badge,
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Stack,
  Text,
  Textarea,
} from "@chakra-ui/react";
import StandardModal from "../../common/StandardModal";
import type { Rule } from "../types";
import { actionBadgeColorScheme } from "../utils";

export default function PiiRuleDetailModal({
  isOpen,
  onClose,
  rule,
  editingDomainId,
  onRemove,
}: {
  isOpen: boolean;
  onClose: () => void;
  rule: Rule | null;
  editingDomainId: string | null;
  onRemove: (rule: Rule) => void;
}) {
  const configStr = rule ? JSON.stringify(rule.config ?? {}, null, 2) : "";
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Rule details"
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {rule ? (
            <Button
              colorScheme="red"
              variant="outline"
              onClick={() => {
                onRemove(rule);
              }}
            >
              Remove rule
            </Button>
          ) : null}
        </HStack>
      }
    >
      {rule ? (
        <Stack spacing={4}>
          <Text fontSize="sm" color="gray.600">
            Domain: {editingDomainId ?? "—"}
          </Text>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Entity type
            </Text>
            <Text fontSize="sm">{rule.entity_type}</Text>
          </Box>
          <Box>
            <Text fontSize="sm" fontWeight="semibold" mb={1}>
              Action
            </Text>
            <Badge colorScheme={actionBadgeColorScheme(rule.action)}>{rule.action}</Badge>
          </Box>
          {rule.custom_regex ? (
            <FormControl>
              <FormLabel fontSize="sm">Custom regex</FormLabel>
              <Textarea readOnly fontFamily="mono" fontSize="sm" value={rule.custom_regex} rows={3} />
            </FormControl>
          ) : null}
          <FormControl>
            <FormLabel fontSize="sm">Config</FormLabel>
            <Textarea readOnly fontFamily="mono" fontSize="xs" value={configStr} rows={6} />
          </FormControl>
        </Stack>
      ) : null}
    </StandardModal>
  );
}
