import { useRef } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  ButtonGroup,
  FormControl,
  HStack,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react";
import { CopyIcon } from "@chakra-ui/icons";
import { FiCalendar, FiCheck } from "react-icons/fi";
import ConfirmDialog from "../common/ConfirmDialog";
import FieldHint from "../common/FieldHint";
import StandardModal from "../common/StandardModal";
import { FieldLabel } from "../common/table";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import {
  formatExtension,
  formatTimeUntil,
  GRACE_EXTENSION_OPTIONS,
  isGraceWithinExpiry,
  ROTATION_GRACE_OPTIONS,
} from "../../utils/apiKeyUtils";
import type { useApiKeyManagementTab } from "./hooks/useApiKeyManagementTab";

/** "24 Oct 2026, 6:00 PM IST" in the viewer's own time zone. */
function formatGraceTime(value: string | Date): string {
  // dateStyle/timeStyle can't be combined with timeZoneName (TypeError).
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

type DialogProps = { mgmt: ReturnType<typeof useApiKeyManagementTab> };

/** Pick a grace period and rotate. */
function RotateDialog({ mgmt }: DialogProps) {
  const rotateCancelRef = useRef<HTMLButtonElement>(null);

  return (
    <ConfirmDialog
      isOpen={Boolean(mgmt.keyToRotate)}
      onClose={mgmt.handleCloseRotateModal}
      onConfirm={mgmt.handleRotateApiKey}
      title={
        mgmt.keyToRotate?.key_name
          ? `Rotate ${mgmt.keyToRotate.key_name}`
          : "Rotate API Key"
      }
      body={
        <VStack align="stretch" spacing={3}>
          <Text fontSize="sm" color="ink.700" lineHeight="1.5">
            A new key is issued for <Text as="b">{mgmt.keyToRotate?.key_name}</Text> and shown
            once. The current key keeps working for the grace period so you can switch your
            applications over, then stops. Budget, permissions and expiry stay the same.
          </Text>
          <FormControl isRequired>
            <FieldLabel>Grace period</FieldLabel>
            <ButtonGroup size="sm" isAttached w="100%" role="radiogroup" aria-label="Grace period">
              {ROTATION_GRACE_OPTIONS.map((days) => {
                const selected = mgmt.rotateGraceDays === days;
                return (
                  <Button
                    key={days}
                    flex={1}
                    role="radio"
                    aria-checked={selected}
                    variant="outline"
                    colorScheme={selected ? "blue" : "gray"}
                    bg={selected ? "blue.50" : undefined}
                    onClick={() => mgmt.setRotateGraceDays(days)}
                    isDisabled={
                      mgmt.isRotating || !isGraceWithinExpiry(days, mgmt.keyToRotate?.expires_at)
                    }
                  >
                    {days} {days === 1 ? "day" : "days"}
                  </Button>
                );
              })}
            </ButtonGroup>
            {mgmt.keyToRotate?.expires_at &&
            ROTATION_GRACE_OPTIONS.some(
              (days) => !isGraceWithinExpiry(days, mgmt.keyToRotate?.expires_at),
            ) ? (
              <FieldHint>
                Grace period can&apos;t go beyond the API key&apos;s expiry (
                {new Date(mgmt.keyToRotate.expires_at).toLocaleDateString()}).
              </FieldHint>
            ) : null}
          </FormControl>
        </VStack>
      }
      confirmLabel="Rotate API Key"
      cancelLabel="Cancel"
      isConfirmDisabled={mgmt.rotateGraceDays === null}
      isConfirmLoading={mgmt.isRotating}
      confirmLoadingText="Rotating..."
      leastDestructiveRef={rotateCancelRef}
    />
  );
}

/** Stop the previous key before its grace period ends. */
function RevokePreviousDialog({ mgmt }: DialogProps) {
  const stopPreviousCancelRef = useRef<HTMLButtonElement>(null);

  return (
    <ConfirmDialog
      isOpen={Boolean(mgmt.keyToStopPrevious)}
      onClose={mgmt.handleCloseStopPreviousModal}
      onConfirm={mgmt.handleStopPreviousKeyValue}
      title={
        mgmt.keyToStopPrevious?.key_name
          ? `Revoke previous key of ${mgmt.keyToStopPrevious.key_name}`
          : "Revoke previous key"
      }
      body={
        <Text fontSize="sm" color="ink.700" lineHeight="1.5">
          The previous key of <Text as="b">{mgmt.keyToStopPrevious?.key_name}</Text> stops working
          immediately instead of at the end of its grace period
          {mgmt.keyToStopPrevious?.rotated_key_expires_at
            ? ` (${new Date(mgmt.keyToStopPrevious.rotated_key_expires_at).toLocaleString()})`
            : ""}
          . The current key keeps working.
        </Text>
      }
      confirmLabel="Revoke Previous Key"
      cancelLabel="Cancel"
      isConfirmLoading={mgmt.isStoppingPrevious}
      confirmLoadingText="Revoking..."
      leastDestructiveRef={stopPreviousCancelRef}
    />
  );
}

/** Move the previous key's grace end later. */
function ExtendGraceModal({ mgmt }: DialogProps) {
  const previousKeySuffix = mgmt.keyToExtend?.rotated_key ? ` (${mgmt.keyToExtend.rotated_key})` : "";
  const showExtendError =
    Boolean(mgmt.extendError) && (mgmt.extendOption !== "custom" || Boolean(mgmt.extendCustomUntil));

  return (
    <StandardModal
      isOpen={Boolean(mgmt.keyToExtend)}
      onClose={mgmt.handleCloseExtendModal}
      title="Extend grace period"
      description={
        mgmt.keyToExtend
          ? `${mgmt.keyToExtend.key_name} • previous key${previousKeySuffix}`
          : undefined
      }
      lockDismiss={mgmt.isExtending}
      footer={
        <HStack spacing={3}>
          <Button variant="ghost" onClick={mgmt.handleCloseExtendModal} isDisabled={mgmt.isExtending}>
            Cancel
          </Button>
          <Button
            colorScheme="blue"
            onClick={() => void mgmt.handleExtendPreviousKeyValue()}
            isLoading={mgmt.isExtending}
            loadingText="Extending..."
            isDisabled={Boolean(mgmt.extendError)}
          >
            Extend grace period
          </Button>
        </HStack>
      }
    >
      {mgmt.keyToExtend?.rotated_key_expires_at ? (
        <VStack align="stretch" spacing={4}>
          <Alert status="warning" borderRadius="md" alignItems="flex-start">
            <Box as={FiCalendar} mt={0.5} mr={3} flexShrink={0} />
            <AlertDescription fontSize="sm">
              Current grace period ends on {formatGraceTime(mgmt.keyToExtend.rotated_key_expires_at)}{" "}
              (in {formatTimeUntil(mgmt.keyToExtend.rotated_key_expires_at)})
            </AlertDescription>
          </Alert>
          <FormControl>
            <FieldLabel>Select extension duration</FieldLabel>
            <ButtonGroup size="sm" isAttached w="100%" role="radiogroup" aria-label="Extension duration">
              {[...GRACE_EXTENSION_OPTIONS, { id: "custom" as const, label: "Custom..." }].map((option) => {
                const selected = mgmt.extendOption === option.id;
                return (
                  <Button
                    key={option.id}
                    flex={1}
                    role="radio"
                    aria-checked={selected}
                    leftIcon={selected ? <FiCheck /> : undefined}
                    variant="outline"
                    colorScheme={selected ? "blue" : "gray"}
                    bg={selected ? "blue.50" : undefined}
                    onClick={() => mgmt.setExtendOption(option.id)}
                    isDisabled={mgmt.isExtending}
                  >
                    {option.label}
                  </Button>
                );
              })}
            </ButtonGroup>
          </FormControl>
          {mgmt.extendOption === "custom" ? (
            <FormControl isRequired>
              <FieldLabel>Works until</FieldLabel>
              <Input
                type="datetime-local"
                value={mgmt.extendCustomUntil}
                onChange={(e) => mgmt.setExtendCustomUntil(e.target.value)}
                isDisabled={mgmt.isExtending}
              />
            </FormControl>
          ) : null}
          {mgmt.extendNewEnd && !mgmt.extendError ? (
            <Alert status="info" borderRadius="md">
              <AlertDescription fontSize="sm">
                New grace period will end on {formatGraceTime(mgmt.extendNewEnd)} (extended by{" "}
                {formatExtension(mgmt.keyToExtend.rotated_key_expires_at, mgmt.extendNewEnd)})
              </AlertDescription>
            </Alert>
          ) : null}
          {showExtendError ? (
            <Alert status="error" borderRadius="md">
              <AlertDescription fontSize="sm">{mgmt.extendError}</AlertDescription>
            </Alert>
          ) : null}
          <Text fontSize="xs" color="ink.500">
            This extends only the previous key. The current key is not affected.
          </Text>
        </VStack>
      ) : null}
    </StandardModal>
  );
}

/** Shows the new key once after a rotation. */
function NewKeyModal({ mgmt }: DialogProps) {
  const { copy } = useCopyToClipboard();

  return (
    <StandardModal
      isOpen={Boolean(mgmt.rotatedKey)}
      onClose={mgmt.handleCloseRotatedKey}
      title="API Key Rotated"
      lockDismiss
      footer={
        <Button colorScheme="blue" onClick={mgmt.handleCloseRotatedKey}>
          I&apos;ve saved the new key
        </Button>
      }
    >
      {mgmt.rotatedKey ? (
        <VStack align="stretch" spacing={4}>
          <Alert status="warning" borderRadius="md" variant="left-accent">
            <AlertIcon />
            <AlertDescription fontSize="sm">
              Copy the new key now. It will not be shown again.
            </AlertDescription>
          </Alert>
          <HStack align="stretch" spacing={2}>
            <Input
              value={mgmt.rotatedKey.api_key}
              isReadOnly
              fontFamily="mono"
              fontSize="xs"
              aria-label="New API key"
            />
            <Button
              size="sm"
              flexShrink={0}
              leftIcon={<CopyIcon />}
              onClick={() => {
                void copy(mgmt.rotatedKey!.api_key, "API key copied to clipboard");
              }}
            >
              Copy
            </Button>
          </HStack>
          <Text fontSize="sm" color="ink.700">
            The previous key for <Text as="b">{mgmt.rotatedKey.key_name}</Text> keeps working
            until{" "}
            <Text as="b">{new Date(mgmt.rotatedKey.rotated_key_expires_at).toLocaleString()}</Text>
            . Revoking the key stops both immediately.
          </Text>
        </VStack>
      ) : null}
    </StandardModal>
  );
}

/** Rotate, revoke-previous, extend-grace and new-key dialogs of the API key table. */
export default function ApiKeyRotationDialogs({ mgmt }: DialogProps) {
  return (
    <>
      <RotateDialog mgmt={mgmt} />
      <RevokePreviousDialog mgmt={mgmt} />
      <ExtendGraceModal mgmt={mgmt} />
      <NewKeyModal mgmt={mgmt} />
    </>
  );
}
