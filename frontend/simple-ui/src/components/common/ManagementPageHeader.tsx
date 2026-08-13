import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { formatInstitutionCopy } from "../../utils/institutionCopy";

interface ManagementPageHeaderProps {
  title: string;
  description?: string;
}

const ManagementPageHeader: React.FC<ManagementPageHeaderProps> = ({ title, description }) => {
  return (
    <VStack spacing={2} w="full" mb={2}>
      <Box textAlign="center">
        <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
          {formatInstitutionCopy(title)}
        </Heading>
        {description ? (
          <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
            {formatInstitutionCopy(description)}
          </Text>
        ) : null}
      </Box>
    </VStack>
  );
};

export default ManagementPageHeader;
