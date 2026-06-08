import { Box, HStack } from "@chakra-ui/react";

export default function OptionSelector({
  options,
  value,
  onChange,
}: {
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <HStack spacing={2}>
      {options.map((opt) => {
        const isActive = value === opt;
        return (
          <Box
            key={opt}
            as="button"
            type="button"
            flex="1"
            py={2}
            px={3}
            fontSize="sm"
            fontWeight="semibold"
            textAlign="center"
            cursor="pointer"
            borderRadius="lg"
            borderWidth="2px"
            borderColor={isActive ? "gray.900" : "gray.200"}
            bg={isActive ? "gray.900" : "white"}
            color={isActive ? "white" : "gray.500"}
            _hover={{ bg: isActive ? "gray.800" : "gray.50", borderColor: isActive ? "gray.800" : "gray.300" }}
            transition="all 0.15s"
            onClick={() => onChange(opt)}
            textTransform="capitalize"
          >
            {opt}
          </Box>
        );
      })}
    </HStack>
  );
}
