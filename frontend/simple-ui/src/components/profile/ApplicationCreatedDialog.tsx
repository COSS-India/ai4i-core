import React from "react";
import { Flex, HStack, Icon, Text, VStack } from "@chakra-ui/react";
import { FiCheck, FiInfo } from "react-icons/fi";
import StandardModal from "../common/StandardModal";
import FormActions from "../common/FormActions";
import {
  applicationCreatedTitle,
  SERVICE_FALLBACK_COPY,
} from "../../config/serviceFallbackMessages";
import type { Application } from "../../types/application";

const COPY = SERVICE_FALLBACK_COPY.createdPrompt;

/** Shown right after an Application is created: offer to set up fallbacks, or skip. */
export default function ApplicationCreatedDialog({
  application,
  onSkip,
  onConfigure,
}: {
  application: Application | null;
  onSkip: () => void;
  onConfigure: (application: Application) => void;
}) {
  return (
    <StandardModal
      isOpen={Boolean(application)}
      onClose={onSkip}
      size="lg"
      title={
        <VStack align="flex-start" spacing={4}>
          <Flex
            w="44px"
            h="44px"
            borderRadius="full"
            bg="teal.50"
            color="teal.600"
            align="center"
            justify="center"
            aria-hidden
          >
            <Icon as={FiCheck} boxSize={5} />
          </Flex>
          <Text as="span" fontSize="xl" fontWeight="700" color="ink.800" letterSpacing="-0.02em">
            {applicationCreatedTitle(application?.name)}
          </Text>
        </VStack>
      }
      headerProps={{ px: 6, pt: 6, pb: 2 }}
      bodyProps={{ px: 6, pt: 0, pb: 5 }}
      footerProps={{ px: 6, py: 4, borderTopWidth: "1px", borderColor: "ink.200" }}
      footer={
        <FormActions
          cancelLabel={COPY.skip}
          submitLabel={COPY.configure}
          onCancel={onSkip}
          onSubmit={() => {
            if (application) onConfigure(application);
          }}
          pt={0}
        />
      }
    >
      <VStack align="stretch" spacing={4}>
        <Text fontSize="sm" color="ink.600">
          {COPY.body}
        </Text>
        <HStack
          align="flex-start"
          spacing={3}
          px={4}
          py={3}
          borderWidth="1px"
          borderColor="ink.200"
          borderRadius="md"
          bg="ink.50"
        >
          <Icon as={FiInfo} boxSize={4} color="teal.600" mt="2px" flexShrink={0} aria-hidden />
          <Text fontSize="sm" color="ink.700">
            {COPY.optionalNote}
          </Text>
        </HStack>
      </VStack>
    </StandardModal>
  );
}
