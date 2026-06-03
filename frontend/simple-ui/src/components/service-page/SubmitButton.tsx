// Primary inference trigger for service request panels

import React from "react";
import { Button } from "@chakra-ui/react";
import type { SubmitButtonProps } from "../../types/servicePage";

const SubmitButton: React.FC<SubmitButtonProps> = ({
  label,
  loadingLabel,
  onClick,
  isLoading = false,
  isDisabled = false,
  icon,
}) => (
  <Button
    leftIcon={icon as React.ReactElement | undefined}
    colorScheme="orange"
    size="lg"
    onClick={onClick}
    isLoading={isLoading}
    loadingText={loadingLabel ?? `${label}...`}
    isDisabled={isDisabled || isLoading}
    w="full"
  >
    {label}
  </Button>
);

export default SubmitButton;
