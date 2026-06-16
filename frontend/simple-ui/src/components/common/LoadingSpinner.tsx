// Loading spinner component for async operations

import React from 'react';
import { Spinner, Flex, VStack, Text, Box } from '@chakra-ui/react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  label?: string;
  fullScreen?: boolean;
  color?: string;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'md',
  label,
  fullScreen = false,
  color = 'orange.500',
}) => {
  const spinner = (
    <VStack spacing={4}>
      <Spinner
        size={size}
        color={color}
        thickness="4px"
        speed="0.65s"
        emptyColor="gray.200"
      />
      {label && (
        <Text fontSize="sm" color="gray.600" textAlign="center">
          {label}
        </Text>
      )}
    </VStack>
  );

  if (fullScreen) {
    return (
      <Flex
        position="fixed"
        top={0}
        left={0}
        right={0}
        bottom={0}
        bg="blackAlpha.600"
        justify="center"
        align="center"
        zIndex={9999}
      >
        {spinner}
      </Flex>
    );
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" p={4}>
      {spinner}
    </Box>
  );
};

export default LoadingSpinner;