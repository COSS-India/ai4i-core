import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";

type FormSectionProps = {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
};

/** Named group inside a Create/Edit form. Omit when the form is a short flat list. */
export default function FormSection({ title, description, children }: FormSectionProps) {
  return (
    <Box
      pt={5}
      mt={1}
      borderTopWidth="1px"
      borderColor="ink.200"
      sx={{
        "&:first-of-type": { pt: 0, mt: 0, borderTopWidth: 0 },
      }}
    >
      <Heading as="h3" size="sm" color="ink.800" mb={description ? 1 : 3}>
        {title}
      </Heading>
      {description ? (
        <Text fontSize="sm" color="ink.600" mb={3} lineHeight="1.5">
          {description}
        </Text>
      ) : null}
      <VStack align="stretch" spacing={4}>
        {children}
      </VStack>
    </Box>
  );
}
