import {
  Alert,
  AlertDescription,
  AlertIcon,
  Card,
  CardBody,
  Flex,
  Text,
  useColorModeValue,
} from "@chakra-ui/react";

interface TraceDetailStatesProps {
  variant: "loading" | "error" | "empty";
  error?: unknown;
}

export default function TraceDetailStates({ variant, error }: TraceDetailStatesProps) {
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");

  return (
    <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
      <CardBody>
        {variant === "loading" && (
          <Flex justify="center" align="center" py={12}>
            <Text ml={4}>Loading trace details...</Text>
          </Flex>
        )}
        {variant === "error" && (
          <Alert status="error">
            <AlertIcon />
            <AlertDescription>
              Failed to load trace.{" "}
              {(error as { message?: string })?.message || "Trace not found or not accessible."}
            </AlertDescription>
          </Alert>
        )}
        {variant === "empty" && (
          <Flex direction="column" align="center" justify="center" py={12}>
            <Text fontSize="lg" color="gray.500" fontWeight="medium" mb={2}>
              No Trace Loaded
            </Text>
            <Text fontSize="sm" color="gray.400" textAlign="center">
              Enter a trace ID above to view trace details
            </Text>
          </Flex>
        )}
      </CardBody>
    </Card>
  );
}
