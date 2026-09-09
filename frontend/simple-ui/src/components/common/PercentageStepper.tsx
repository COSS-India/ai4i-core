import React from "react";
import {
  HStack,
  Input,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  Text,
} from "@chakra-ui/react";

/** Hard 0–100 typing bounds (AI4IDS-3048). Soft floors stay on field errors. */
export type PercentageBound = "min" | "max";

type Props = {
  value: string;
  onChange: (next: string) => void;
  onBoundHit?: (bound: PercentageBound) => void;
  isDisabled?: boolean;
  onFocus?: () => void;
  placeholder?: string;
  variant?: "stepper" | "inline";
};

function accept(
  raw: string,
  onChange: (next: string) => void,
  onBoundHit?: (bound: PercentageBound) => void,
) {
  if (raw.trim() === "") {
    onChange("");
    return;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) return;
  if (n > 100) {
    onBoundHit?.("max");
    return;
  }
  if (n < 0) {
    onBoundHit?.("min");
    return;
  }
  onChange(raw);
}

/** Shared budget % input — rejects outside 0–100, leaves the field unchanged. */
export default function PercentageStepper({
  value,
  onChange,
  onBoundHit,
  isDisabled = false,
  onFocus,
  placeholder,
  variant = "stepper",
}: Props) {
  const pct = (
    <Text color="gray.500" fontSize={variant === "inline" ? "sm" : undefined} fontWeight="semibold">
      %
    </Text>
  );

  if (variant === "inline") {
    return (
      <HStack spacing={1} align="center">
        <Input
          type="number"
          value={value}
          onChange={(e) => accept(e.target.value, onChange, onBoundHit)}
          onFocus={onFocus}
          min={0}
          max={100}
          step={0.01}
          size="sm"
          w="88px"
          bg="white"
          isDisabled={isDisabled}
          placeholder={placeholder}
        />
        {pct}
      </HStack>
    );
  }

  return (
    <HStack maxW="180px" spacing={2} align="center">
      <NumberInput
        value={value}
        onChange={(next) => accept(next, onChange, onBoundHit)}
        min={0}
        max={100}
        step={1}
        precision={2}
        clampValueOnBlur={false}
        keepWithinRange
        bg="white"
        w="120px"
        isDisabled={isDisabled}
      >
        <NumberInputField placeholder={placeholder} onFocus={onFocus} />
        <NumberInputStepper>
          <NumberIncrementStepper />
          <NumberDecrementStepper />
        </NumberInputStepper>
      </NumberInput>
      {pct}
    </HStack>
  );
}
