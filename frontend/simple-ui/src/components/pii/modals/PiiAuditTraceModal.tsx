import { Button, FormControl, FormLabel, HStack, Textarea } from "@chakra-ui/react";
import StandardModal from "../../common/StandardModal";

interface PiiAuditTraceModalProps {
  isOpen: boolean;
  onClose: () => void;
  auditDetailJson: string;
}

export default function PiiAuditTraceModal({
  isOpen,
  onClose,
  auditDetailJson,
}: PiiAuditTraceModalProps) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Audit trace"
      size="4xl"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </HStack>
      }
    >
      <FormControl>
        <FormLabel fontSize="sm">Trace JSON</FormLabel>
        <Textarea value={auditDetailJson} readOnly fontFamily="mono" fontSize="xs" rows={18} />
      </FormControl>
    </StandardModal>
  );
}
