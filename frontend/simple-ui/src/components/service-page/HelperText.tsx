// Usage instructions and limits for service request panels

import React from "react";
import { List, ListItem, Text, VStack } from "@chakra-ui/react";

export interface HelperTextProps {
  text?: React.ReactNode;
  items?: string[];
}

const HelperText: React.FC<HelperTextProps> = ({ text, items }) => {
  if (!text && (!items || items.length === 0)) return null;

  return (
    <VStack align="stretch" spacing={2}>
      {text && (
        <Text fontSize="sm" color="gray.600">
          {text}
        </Text>
      )}
      {items && items.length > 0 && (
        <List spacing={1} fontSize="sm" color="gray.600" styleType="disc" pl={4}>
          {items.map((item, i) => (
            <ListItem key={i}>{item}</ListItem>
          ))}
        </List>
      )}
    </VStack>
  );
};

export default HelperText;
