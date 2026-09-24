import { Box, Text, VStack } from "@chakra-ui/react";
import React from "react";
import FieldLabel from "../common/FieldLabel";

type Dataset = {
  description?: string;
  datasetId?: string;
};

/** View-only model information that is not part of the create/edit field list. */
export default function ModelDetails({
  trainingDataset,
  adapterConfig,
  schema,
}: {
  trainingDataset?: Dataset | null;
  adapterConfig?: unknown;
  schema?: unknown;
}) {
  if (!trainingDataset && !adapterConfig && !schema) return null;

  return (
    <VStack spacing={6} align="stretch">
      {trainingDataset ? (
        <Box>
          <FieldLabel variant="inline">Training dataset</FieldLabel>
          <Text fontSize="md">{trainingDataset.description || "—"}</Text>
          {trainingDataset.datasetId ? (
            <Text fontSize="sm" color="ink.500" mt={1}>
              ID: {trainingDataset.datasetId}
            </Text>
          ) : null}
        </Box>
      ) : null}
      {adapterConfig ? (
        <Box>
          <FieldLabel variant="inline">Adapter config</FieldLabel>
          <Text fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap">
            {JSON.stringify(adapterConfig, null, 2)}
          </Text>
        </Box>
      ) : null}
      {schema ? (
        <Box>
          <FieldLabel variant="inline">Schema</FieldLabel>
          <Text fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap">
            {JSON.stringify(schema, null, 2)}
          </Text>
        </Box>
      ) : null}
    </VStack>
  );
}
