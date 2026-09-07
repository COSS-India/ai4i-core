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


export type PercentageBound = "min" | "max" | "floor" | "ceiling";

type PercentageStepperProps = {
  value: string;
  onChange: (next: string) => void;
  /** Stepper / HTML floor (e.g. consumed %). Typing filter is hard 0–100 only. */
  min?: number;
  /** Stepper / HTML ceiling (e.g. available %). Typing filter is hard 0–100 only. */
  max?: number;
  onBoundHit?: (bound: PercentageBound) => void;
  isDisabled?: boolean;
  onFocus?: () => void;
  placeholder?: string;
  /** Compact table input vs NumberInput with steppers. */
  variant?: "stepper" | "inline";
};

/** Reject values outside 0–100; leave consumed/available floors to field errors. */
function acceptPercentageInput(
  raw: string,
  onChange: (next: string) => void,
  onBoundHit?: (bound: PercentageBound) => void,
): void {
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

/**
 * Shared budget % field (AI4IDS-3048).
 * Typing is hard-capped to 0–100; `min`/`max` only drive steppers / HTML hints.
 */
export default function PercentageStepper({
  value,
  onChange,
  min = 0,
  max = 100,
  onBoundHit,
  isDisabled = false,
  onFocus,
  placeholder,
  variant = "stepper",
}: PercentageStepperProps) {
  const stepLo = Math.max(0, min);
  const stepHi = Math.min(100, max);
  const numeric = value.trim() === "" ? null : Number(value);
  const atMin = numeric != null && Number.isFinite(numeric) && numeric <= stepLo + 1e-6;
  const atMax = numeric != null && Number.isFinite(numeric) && numeric >= stepHi - 1e-6;

  if (variant === "inline") {
    return (
      <HStack spacing={1} align="center">
        <Input
          type="number"
          value={value}
          onChange={(e) => acceptPercentageInput(e.target.value, onChange, onBoundHit)}
          onFocus={onFocus}
          min={stepLo}
          max={stepHi}
          step={0.01}
          size="sm"
          w="88px"
          bg="white"
          isDisabled={isDisabled}
          placeholder={placeholder}
        />
        <Text color="gray.500" fontSize="sm" fontWeight="semibold">
          %
        </Text>
      </HStack>
    );
  }

  return (
    <HStack maxW="180px" spacing={2} align="center">
      <NumberInput
        value={value}
        onChange={(next) => acceptPercentageInput(next, onChange, onBoundHit)}
        min={stepLo}
        max={stepHi}
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
          <NumberIncrementStepper
            cursor={atMax ? "not-allowed" : undefined}
            onClick={() => {
              if (atMax) onBoundHit?.("ceiling");
            }}
          />
          <NumberDecrementStepper
            cursor={atMin || numeric == null ? "not-allowed" : undefined}
            onClick={() => {
              if (atMin || numeric == null) onBoundHit?.("floor");
            }}
          />
        </NumberInputStepper>
      </NumberInput>
      <Text color="gray.500" fontWeight="semibold">
        %
      </Text>
    </HStack>
  );
}
