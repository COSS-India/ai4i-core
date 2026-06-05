// Audio input slot for service pages (wraps recorder/upload UI)

import React from "react";
import { Box, FormLabel, Text, VStack } from "@chakra-ui/react";
import type { ServiceAudioInputProps } from "../../../types/servicePage";

/**
 * Container for audio capture/upload. Pass children (e.g. AudioRecorder + AudioInputPreview)
 * from the service page or hook layer.
 */
const AudioInput: React.FC<ServiceAudioInputProps> = ({
  children,
  label = "Audio Input",
  required = true,
  helperSlot,
}) => {
  return (
    <VStack spacing={4} align="stretch" w="full">
      <Box>
        <FormLabel className="dview-service-try-option-title" mb={2} fontSize="sm" fontWeight="semibold">
          {label}{" "}
          {required && (
            <Text as="span" color="red.500">
              *
            </Text>
          )}
        </FormLabel>
        {children}
      </Box>
      {helperSlot}
    </VStack>
  );
};

export default AudioInput;
