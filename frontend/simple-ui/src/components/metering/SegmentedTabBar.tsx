import { Button, ButtonGroup, HStack } from "@chakra-ui/react";
import React from "react";
import { formatInstitutionCopy } from "../../utils/institutionCopy";

export interface SegmentedTabOption<T extends string> {
  id: T;
  label: string;
}

interface SegmentedTabBarProps<T extends string> {
  readonly options: ReadonlyArray<SegmentedTabOption<T>>;
  readonly activeId: T;
  readonly onChange: (id: T) => void;
  readonly justify?: "flex-start" | "flex-end" | "center";
  readonly mb?: number;
}

function SegmentedTabBar<T extends string>({
  options,
  activeId,
  onChange,
  justify = "flex-start",
  mb = 0,
}: Readonly<SegmentedTabBarProps<T>>) {
  return (
    <HStack justify={justify} spacing={3} mb={mb} flexWrap="wrap">
      <ButtonGroup
        size="sm"
        isAttached
        variant="outline"
        bg="gray.100"
        borderRadius="md"
        p={0.5}
        borderWidth="1px"
        borderColor="gray.200"
      >
        {options.map((option) => (
          <Button
            key={option.id}
            onClick={() => onChange(option.id)}
            bg={activeId === option.id ? "white" : "transparent"}
            color="gray.800"
            fontWeight={activeId === option.id ? "bold" : "medium"}
            boxShadow={activeId === option.id ? "sm" : "none"}
            border="none"
            _hover={{ bg: activeId === option.id ? "white" : "gray.50" }}
            px={4}
          >
            {formatInstitutionCopy(option.label)}
          </Button>
        ))}
      </ButtonGroup>
    </HStack>
  );
}

export default SegmentedTabBar;
