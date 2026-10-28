import React from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
  Flex,
  FormControl,
  Grid,
  HStack,
  Icon,
  Select,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FiPlus } from "react-icons/fi";
import { LuSplit } from "react-icons/lu";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import { CreateModal } from "../common/StandardModal";
import {
  fallbackEditorDescription,
  SERVICE_FALLBACK_COPY,
} from "../../config/serviceFallbackMessages";
import {
  canAddFallbackRow,
  fallbackOptionsFor,
  isRowComplete,
  isRowStale,
  modelMatchFor,
  primaryOptionsFor,
  tierHasNoAlternatives,
  type FallbackCatalogue,
  type FallbackRow,
  type FallbackServiceOption,
} from "./serviceFallbackDraft";
import type { FallbackCatalogueState, ServiceFallbackEditor } from "./hooks/useServiceFallbacks";

const COPY = SERVICE_FALLBACK_COPY.editor;

/** Options for one select, plus the saved value when it is no longer offered. */
function ServiceOptions({
  options,
  value,
}: Readonly<{
  options: FallbackServiceOption[];
  value: string;
}>) {
  const missing = value && !options.some((o) => o.serviceId === value);
  return (
    <>
      {missing ? (
        <option value={value} disabled>
          {COPY.unavailableOption(value)}
        </option>
      ) : null}
      {options.map((option) => (
        <option key={option.serviceId} value={option.serviceId}>
          {option.name}
        </option>
      ))}
    </>
  );
}

function FallbackRowCard({
  index,
  row,
  rows,
  catalogue,
  editor,
}: Readonly<{
  index: number;
  row: FallbackRow;
  rows: FallbackRow[];
  catalogue: FallbackCatalogue;
  editor: ServiceFallbackEditor;
}>) {
  const match = modelMatchFor(row, catalogue);
  const stale = isRowStale(row, catalogue);
  const title = COPY.rowTitle(index);
  let borderColor = "ink.200";
  if (stale) borderColor = "orange.300";
  else if (isRowComplete(row)) borderColor = "teal.500";

  return (
    <Box
      borderWidth="1px"
      borderColor={borderColor}
      borderRadius="lg"
      px={5}
      py={4}
      role="group"
      aria-label={title}
    >
      <Flex justify="space-between" align="center" mb={3}>
        <Text fontSize="md" fontWeight="700" color="ink.800">
          {title}
        </Text>
        <Button
          size="sm"
          variant="ghost"
          color="ink.600"
          onClick={() => editor.removeRow(row.key)}
          isDisabled={editor.isSaving}
          aria-label={`${COPY.remove} ${title}`}
        >
          {COPY.remove}
        </Button>
      </Flex>
      <Grid templateColumns={{ base: "1fr", md: "repeat(2, minmax(0, 1fr))" }} gap={3}>
        <FormControl>
          <FieldLabel>{COPY.primaryService}</FieldLabel>
          <Select
            value={row.primaryId}
            placeholder={COPY.selectPrimary}
            onChange={(e) => editor.setPrimary(row.key, e.target.value)}
            isDisabled={editor.isSaving}
          >
            <ServiceOptions options={primaryOptionsFor(row, rows, catalogue)} value={row.primaryId} />
          </Select>
        </FormControl>
        <FormControl>
          <FieldLabel>{COPY.fallbackService}</FieldLabel>
          <Select
            value={row.fallbackId}
            placeholder={COPY.selectFallback}
            onChange={(e) => editor.setFallback(row.key, e.target.value)}
            isDisabled={editor.isSaving || !row.primaryId}
          >
            <ServiceOptions options={fallbackOptionsFor(row, catalogue)} value={row.fallbackId} />
          </Select>
          {match ? (
            <Text
              mt={1.5}
              fontSize="xs"
              color={match === "same" ? "green.700" : "orange.700"}
              role="status"
            >
              {match === "same" ? COPY.sameModel : COPY.differentModel}
            </Text>
          ) : null}
        </FormControl>
      </Grid>
    </Box>
  );
}

function EmptyState({ canAdd, onAdd }: Readonly<{ canAdd: boolean; onAdd: () => void }>) {
  return (
    <VStack
      spacing={3}
      py={10}
      px={6}
      borderWidth="1px"
      borderStyle="dashed"
      borderColor="ink.300"
      borderRadius="lg"
      textAlign="center"
    >
      <Flex
        w="48px"
        h="48px"
        borderRadius="full"
        bg="teal.50"
        color="teal.600"
        align="center"
        justify="center"
        aria-hidden
      >
        <Icon as={LuSplit} boxSize={5} />
      </Flex>
      <Text fontSize="md" fontWeight="700" color="ink.800">
        {COPY.emptyTitle}
      </Text>
      <Text fontSize="sm" color="ink.600" maxW="420px">
        {COPY.emptyBody}
      </Text>
      <Button leftIcon={<FiPlus />} onClick={onAdd} isDisabled={!canAdd} mt={1}>
        {COPY.addFallback}
      </Button>
    </VStack>
  );
}

function CatalogueNotice({ state }: Readonly<{ state: FallbackCatalogueState }>) {
  if (state.status === "loading" || state.status === "idle") {
    return (
      <HStack spacing={3} py={6} justify="center" color="ink.500">
        <Spinner size="sm" />
        <Text fontSize="sm">{COPY.loading}</Text>
      </HStack>
    );
  }
  if (state.status === "error") {
    return (
      <Alert status="error" borderRadius="md">
        <AlertIcon />
        <Box flex="1">{COPY.loadFailed}</Box>
        <Button size="xs" variant="outline" colorScheme="red" ml={3} onClick={state.retry}>
          {COPY.retry}
        </Button>
      </Alert>
    );
  }
  return (
    <Alert status="warning" borderRadius="md">
      <AlertIcon />
      {COPY.noTier}
    </Alert>
  );
}

export default function ServiceFallbacksModal({
  editor,
  catalogueState,
}: Readonly<{
  editor: ServiceFallbackEditor;
  catalogueState: FallbackCatalogueState;
}>) {
  const { catalogue } = catalogueState;
  const ready = catalogueState.status === "ready" && editor.seeded;
  const canAdd = ready && canAddFallbackRow(editor.rows, catalogue) && !editor.isSaving;
  const inactive = editor.application?.status === "INACTIVE";

  return (
    <CreateModal
      isOpen={editor.isOpen}
      onClose={editor.close}
      lockDismiss={editor.isSaving}
      size="lg"
      title={COPY.title}
      description={fallbackEditorDescription(editor.application?.name)}
      footer={
        <Flex w="full" align="center" gap={4}>
          <Text fontSize="sm" color="ink.500" flexShrink={1} minW={0} role="status">
            {ready ? editor.statusText : ""}
          </Text>
          <FormActions
            cancelLabel={editor.isDirty ? COPY.cancel : COPY.close}
            submitLabel={COPY.save}
            onCancel={editor.close}
            onSubmit={() => {
              editor.save();
            }}
            isLoading={editor.isSaving}
            loadingText={COPY.saving}
            isDisabled={!editor.canSave}
            mutedWhenDisabled
            pt={0}
          />
        </Flex>
      }
    >
      <VStack align="stretch" spacing={4}>
        {editor.banner ? (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {editor.banner}
          </Alert>
        ) : null}

        {catalogueState.tierName ? (
          <Text fontSize="sm" color="ink.600">
            {COPY.tierLabel}:{" "}
            <Text as="span" fontWeight="600" color="ink.800">
              {catalogueState.tierName}
            </Text>
          </Text>
        ) : null}

        {inactive ? (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            {COPY.inactiveNote}
          </Alert>
        ) : null}

        {ready ? (
          <>
            {editor.hasStale ? (
              <Alert status="warning" borderRadius="md" alignItems="flex-start">
                <AlertIcon />
                <Box flex="1">
                  <AlertTitle fontSize="sm">{COPY.staleTitle}</AlertTitle>
                  <AlertDescription fontSize="sm">{COPY.staleBody}</AlertDescription>
                </Box>
                <Button
                  size="xs"
                  variant="outline"
                  colorScheme="orange"
                  ml={3}
                  onClick={editor.removeStaleRows}
                  isDisabled={editor.isSaving}
                >
                  {COPY.removeStale}
                </Button>
              </Alert>
            ) : null}

            {tierHasNoAlternatives(catalogue) ? (
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                {COPY.noAlternatives}
              </Alert>
            ) : null}

            {editor.rows.length === 0 ? (
              <EmptyState canAdd={canAdd} onAdd={editor.addRow} />
            ) : (
              <>
                {editor.rows.map((row, index) => (
                  <FallbackRowCard
                    key={row.key}
                    index={index}
                    row={row}
                    rows={editor.rows}
                    catalogue={catalogue}
                    editor={editor}
                  />
                ))}
                <Box>
                  <Button
                    leftIcon={<FiPlus />}
                    variant="outline"
                    onClick={editor.addRow}
                    isDisabled={!canAdd}
                  >
                    {COPY.addFallback}
                  </Button>
                </Box>
              </>
            )}
          </>
        ) : (
          <CatalogueNotice state={catalogueState} />
        )}
      </VStack>
    </CreateModal>
  );
}
