// Trace step component with context layers

import React from 'react';
import {
  Box,
  VStack,
  Text,
  HStack,
  Badge,
  Collapse,
  useColorModeValue,
} from '@chakra-ui/react';
import { TraceStep } from '../../types/tracing';

interface TraceStepProps {
  step: TraceStep;
  isActive: boolean;
  isComplete: boolean;
  isPending: boolean;
}

const TraceStepComponent: React.FC<TraceStepProps> = ({
  step,
  isActive,
  isComplete,
  isPending,
}) => {
  const bgColor = useColorModeValue('white', 'gray.800');
  const activeBg = useColorModeValue('blue.50', 'blue.900');
  const completeBg = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  const activeBorder = useColorModeValue('blue.400', 'blue.500');
  
  const badgeColors = {
    auth: { bg: 'blue.100', color: 'blue.800' },
    contract: { bg: 'yellow.100', color: 'yellow.800' },
    inference: { bg: 'purple.100', color: 'purple.800' },
    metadata: { bg: 'gray.100', color: 'gray.800' },
  };

  const getStatusIcon = () => {
    if (isComplete) return '✓';
    if (isActive) return '⚡';
    return '';
  };

  const getBgColor = () => {
    if (isActive) return activeBg;
    if (isComplete) return completeBg;
    return bgColor;
  };

  const getBorderColor = () => {
    if (isActive) return activeBorder;
    return borderColor;
  };

  const getOpacity = () => {
    if (isPending) return 0.4;
    if (isComplete) return 0.7;
    return 1;
  };

  return (
    <Box
      border="2px solid"
      borderColor={getBorderColor()}
      borderRadius="lg"
      p={4}
      mb={3}
      bg={getBgColor()}
      opacity={getOpacity()}
      transform={isActive ? 'scale(1.02)' : 'scale(1)'}
      boxShadow={isActive ? 'md' : 'sm'}
      transition="all 0.3s"
    >
      <HStack spacing={3} align="start">
        <Box fontSize="2xl" flexShrink={0}>
          {step.icon}
        </Box>
        <VStack align="start" flex={1} spacing={2}>
          <HStack>
            <Text fontWeight="bold" fontSize="sm" color="gray.800">
              {step.title}
            </Text>
            {getStatusIcon() && (
              <Text fontSize="sm">{getStatusIcon()}</Text>
            )}
          </HStack>
          <Text fontSize="xs" color="gray.600" lineHeight="1.5">
            {step.description}
          </Text>

          {/* Context Layers */}
          {step.hasContextLayers && step.contextLayers && (
            <Collapse in={isActive} animateOpacity>
              <VStack align="stretch" spacing={2} mt={2}>
                {step.contextLayers.map((layer, idx) => (
                  <Box
                    key={idx}
                    bg="white"
                    border="1px solid"
                    borderColor="gray.200"
                    borderRadius="md"
                    p={3}
                  >
                    <HStack mb={2}>
                      <Badge
                        bg={badgeColors[layer.type]?.bg || 'gray.100'}
                        color={badgeColors[layer.type]?.color || 'gray.800'}
                        fontSize="xs"
                        fontWeight="bold"
                        textTransform="uppercase"
                        px={2}
                        py={1}
                      >
                        {layer.badge}
                      </Badge>
                    </HStack>
                    <Text fontSize="xs" fontWeight="600" color="gray.700" mb={2}>
                      {layer.title}
                    </Text>
                    <HStack flexWrap="wrap" gap={2} mb={2}>
                      {layer.items.map((item, itemIdx) => (
                        <Badge
                          key={itemIdx}
                          bg="gray.50"
                          color="gray.700"
                          fontSize="xs"
                          px={2}
                          py={1}
                          borderRadius="sm"
                        >
                          {item}
                        </Badge>
                      ))}
                    </HStack>
                    {layer.note && (
                      <Text fontSize="xs" color="gray.500" fontStyle="italic" mt={1}>
                        {layer.note}
                      </Text>
                    )}
                  </Box>
                ))}
              </VStack>
            </Collapse>
          )}
        </VStack>
      </HStack>
    </Box>
  );
};

export default TraceStepComponent;

