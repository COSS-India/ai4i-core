// Primary result content display for service responses

import React from "react";
import { Box, Text, Textarea } from "@chakra-ui/react";

export interface ResultDisplayProps {
  title?: string;
  content: string;
  /** When true, renders a read-only textarea instead of plain text */
  multiline?: boolean;
  minHeight?: string;
}

const ResultDisplay: React.FC<ResultDisplayProps> = ({
  title = "Result",
  content,
  multiline = false,
  minHeight = "200px",
}) => {
  if (!content?.trim()) return null;

  return (
    <Box
      p={4}
      bg="gray.50"
      borderRadius="md"
      borderWidth="1px"
      borderColor="gray.200"
      w="full"
    >
      <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={2}>
        {title}
      </Text>
      {multiline ? (
        <Textarea
          value={content}
          readOnly
          resize="none"
          minH={minHeight}
          fontSize="sm"
          _focus={{ boxShadow: "none", borderColor: "orange.300" }}
        />
      ) : (
        <Text fontSize="sm" color="gray.800" whiteSpace="pre-wrap">
          {content}
        </Text>
      )}
    </Box>
  );
};

export default ResultDisplay;
