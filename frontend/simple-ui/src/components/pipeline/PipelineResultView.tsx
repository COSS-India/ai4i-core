// Pipeline inference result display

import React from "react";
import {
  Box,
  FormLabel,
  SimpleGrid,
  Stat,
  StatHelpText,
  StatLabel,
  StatNumber,
  Textarea,
} from "@chakra-ui/react";
import type { PipelineResult } from "../../types/pipeline";

const getWordCount = (text: string): number =>
  text.trim().split(/\s+/).filter(Boolean).length;

export interface PipelineResultViewProps {
  result: PipelineResult;
}

const PipelineResultView: React.FC<PipelineResultViewProps> = ({ result }) => (
  <>
    <SimpleGrid
      p={4}
      bg="orange.50"
      borderRadius="md"
      border="1px"
      borderColor="orange.200"
      columns={2}
      spacingX="20px"
      spacingY="10px"
    >
      <Stat>
        <StatLabel>Source Text</StatLabel>
        <StatNumber>{getWordCount(result.sourceText)}</StatNumber>
        <StatHelpText>words</StatHelpText>
      </Stat>
      <Stat>
        <StatLabel>Translated Text</StatLabel>
        <StatNumber>{getWordCount(result.targetText)}</StatNumber>
        <StatHelpText>words</StatHelpText>
      </Stat>
    </SimpleGrid>

    <Box>
      <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
        Transcribed Text (Source)
      </FormLabel>
      <Textarea readOnly value={result.sourceText} rows={4} />
    </Box>

    <Box>
      <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
        Translated Text (Target)
      </FormLabel>
      <Textarea readOnly value={result.targetText} rows={4} />
    </Box>

    {result.audio && (
      <Box>
        <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
          Synthesized Audio (Target)
        </FormLabel>
        <audio controls src={result.audio} style={{ width: "100%" }} />
      </Box>
    )}
  </>
);

export default PipelineResultView;
