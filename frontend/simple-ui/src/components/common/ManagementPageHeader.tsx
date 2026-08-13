import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";

interface ManagementPageHeaderProps {
  title: string;
  description?: string;
}

const ManagementPageHeader: React.FC<ManagementPageHeaderProps> = ({ title, description }) => {
  return (
    <VStack spacing={2} w="full" mb={2}>
      <Box textAlign="center">
        <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
          {title}
        </Heading>
        {description ? (
          <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
            {description}
          </Text>
        ) : null}
      </Box>
    </VStack>
  );
};

export default ManagementPageHeader;
