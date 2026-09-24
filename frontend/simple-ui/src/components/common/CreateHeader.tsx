import { Box, Heading, Text } from "@chakra-ui/react";
import React from "react";

type CreateHeaderProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
};

/** Title + short purpose line for Create/Edit overlays and form chrome. */
export default function CreateHeader({ title, description }: CreateHeaderProps) {
  return (
    <Box pr={8}>
      <Heading
        as="h2"
        size="md"
        color="ink.800"
        fontWeight="700"
        letterSpacing="-0.03em"
        userSelect="none"
      >
        {title}
      </Heading>
      {description ? (
        <Text mt={1} color="ink.600" fontSize="sm" fontWeight="500" lineHeight="1.5">
          {description}
        </Text>
      ) : null}
    </Box>
  );
}
