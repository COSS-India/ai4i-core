import {
  Button,
  Flex,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  Spinner,
  Stack,
  Textarea,
} from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import type { MaskFormat, PiiTypeOut } from "../../services/policyService";
import { MASK_OPTIONS } from "./constants";

interface PiiTypeFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  editing: PiiTypeOut | null;
  label: string;
  setLabel: (v: string) => void;
  regex: string;
  setRegex: (v: string) => void;
  examples: string;
  setExamples: (v: string) => void;
  mask: MaskFormat;
  setMask: (v: MaskFormat) => void;
  saving: boolean;
  piiDetailLoading: boolean;
  onSave: () => void;
}

export default function PiiTypeFormModal({
  isOpen,
  onClose,
  editing,
  label,
  setLabel,
  regex,
  setRegex,
  examples,
  setExamples,
  mask,
  setMask,
  saving,
  piiDetailLoading,
  onSave,
}: PiiTypeFormModalProps) {
  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={editing ? "PII type configuration" : "New PII type (library)"}
      size="lg"
      footer={
        <HStack justify="flex-end" w="full">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            colorScheme="blue"
            onClick={onSave}
            isLoading={saving}
            isDisabled={Boolean(editing) && piiDetailLoading}
          >
            Save
          </Button>
        </HStack>
      }
    >
      {editing && piiDetailLoading ? (
        <Flex justify="center" py={8}>
          <Spinner />
        </Flex>
      ) : (
        <Stack spacing={4}>
          <FormControl isRequired>
            <FormLabel>Label</FormLabel>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </FormControl>
          <FormControl isRequired>
            <FormLabel>Regex pattern</FormLabel>
            <Textarea value={regex} onChange={(e) => setRegex(e.target.value)} fontFamily="mono" rows={3} />
          </FormControl>
          <FormControl isRequired={!editing}>
            <FormLabel>
              {editing
                ? "Example values (comma or newline, optional validation)"
                : "Example values (comma or newline, min 3)"}
            </FormLabel>
            <Textarea
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              placeholder="a@b.com, test@example.org, user@mail.co"
              rows={3}
            />
          </FormControl>
          <FormControl>
            <FormLabel>Mask format</FormLabel>
            <Select value={mask} onChange={(e) => setMask(e.target.value as MaskFormat)}>
              {MASK_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </FormControl>
        </Stack>
      )}
    </StandardModal>
  );
}
