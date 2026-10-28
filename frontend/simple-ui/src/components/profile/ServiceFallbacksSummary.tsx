import React from "react";
import { Box, Button, HStack, Icon, Skeleton, Text, VStack } from "@chakra-ui/react";
import { FiArrowRight, FiEdit2 } from "react-icons/fi";
import FormSection from "../common/FormSection";
import { SERVICE_FALLBACK_COPY } from "../../config/serviceFallbackMessages";
import type { ServiceFallbackMap } from "../../types/application";
import type { FallbackCatalogue } from "./serviceFallbackDraft";

const COPY = SERVICE_FALLBACK_COPY.details;

function ServiceName({ id, catalogue }: Readonly<{ id: string; catalogue: FallbackCatalogue }>) {
  const option = catalogue.byId.get(id);
  if (option) {
    return (
      <Text as="span" fontWeight="600" color="ink.800">
        {option.name}
      </Text>
    );
  }
  return (
    <Text as="span" color="ink.500">
      {id} ({COPY.unavailable})
    </Text>
  );
}

/** Application details: configured fallbacks, read-only, with a way into the editor. */
export default function ServiceFallbacksSummary({
  fallbacks,
  catalogue,
  isLoading,
  onConfigure,
}: Readonly<{
  fallbacks: ServiceFallbackMap;
  catalogue: FallbackCatalogue;
  /** Names resolve from the Tier catalogue; ids show while it loads. */
  isLoading: boolean;
  onConfigure: () => void;
}>) {
  const entries = Object.entries(fallbacks).filter(([, ids]) => ids.length > 0);

  let body: React.ReactNode;
  if (entries.length === 0) {
    body = (
      <Text fontSize="sm" color="ink.500">
        {COPY.none}
      </Text>
    );
  } else if (isLoading) {
    body = (
      <VStack align="stretch" spacing={2}>
        {entries.map(([primary]) => (
          <Skeleton key={primary} h="18px" w="70%" />
        ))}
      </VStack>
    );
  } else {
    body = (
      <VStack as="ul" align="stretch" spacing={2} listStyleType="none" m={0}>
        {entries.map(([primary, ids]) => (
          <HStack as="li" key={primary} spacing={2} fontSize="sm" flexWrap="wrap">
            <ServiceName id={primary} catalogue={catalogue} />
            <Icon as={FiArrowRight} color="ink.400" aria-label="falls back to" />
            {ids.map((id, index) => (
              <React.Fragment key={id}>
                {index > 0 ? <Text as="span" color="ink.400">,</Text> : null}
                <ServiceName id={id} catalogue={catalogue} />
              </React.Fragment>
            ))}
          </HStack>
        ))}
      </VStack>
    );
  }

  return (
    <FormSection title={SERVICE_FALLBACK_COPY.editor.title}>
      {body}
      <Box>
        <Button size="sm" variant="outline" leftIcon={<FiEdit2 />} onClick={onConfigure}>
          {entries.length === 0 ? COPY.configure : COPY.edit}
        </Button>
      </Box>
    </FormSection>
  );
}
