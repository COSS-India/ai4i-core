// Response stats: time, word count, confidence, etc.

import React from "react";
import {
  SimpleGrid,
  Stat,
  StatHelpText,
  StatLabel,
  StatNumber,
} from "@chakra-ui/react";
import type { ResponseMetadataItem } from "../../../types/servicePage";

export interface ResponseMetadataProps {
  items: ResponseMetadataItem[];
}

const ResponseMetadata: React.FC<ResponseMetadataProps> = ({ items }) => {
  if (!items.length) return null;

  return (
    <SimpleGrid
      columns={{ base: 1, md: Math.min(2, items.length) }}
      spacing={{ base: 4, md: 8 }}
      w="full"
      p="1rem"
      bg="orange.100"
      borderRadius="15px"
    >
      {items.map((item) => (
        <Stat key={item.label} textAlign="center">
          <StatLabel>{item.label}</StatLabel>
          <StatNumber color="orange.600">{item.value}</StatNumber>
          {item.helpText && <StatHelpText>{item.helpText}</StatHelpText>}
        </Stat>
      ))}
    </SimpleGrid>
  );
};

export default ResponseMetadata;
