import {
  Box,
  FormControl,
  FormErrorMessage,
  FormLabel,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  Select,
  SimpleGrid,
  Text,
} from "@chakra-ui/react";
import { CONDITION_OPERATORS, LATENCY_THRESHOLD_UNITS, PERCENTAGE_UNIT } from "../../../../../types/alerting";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionThresholdField({ mode, defs }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const form = isCreate ? defs.createForm : defs.updateForm;
  const errors = isCreate ? defs.createErrors : defs.updateErrors;
  const signal = form.signal;

  const isInvalid = isCreate
    ? !!(errors?.condition_operator || errors?.threshold_value || errors?.threshold_unit)
    : Boolean(errors?.condition_operator || errors?.threshold_value);

  const setForm = (patch: Record<string, unknown>) =>
    isCreate
      ? defs.setCreateForm({ ...defs.createForm, ...patch })
      : defs.setUpdateForm({ ...defs.updateForm, ...patch });

  return (
    <FormControl isRequired isInvalid={isInvalid}>
      <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
        Condition + Threshold
      </FormLabel>
      <SimpleGrid columns={3} spacing={3} mb={1}>
        <Text fontSize="xs" color="gray.500" fontWeight="medium">Condition</Text>
        <Text fontSize="xs" color="gray.500" fontWeight="medium">Threshold</Text>
        <Text fontSize="xs" color="gray.500" fontWeight="medium">Unit</Text>
      </SimpleGrid>
      <SimpleGrid columns={3} spacing={3}>
        <Select
          value={form.condition_operator ?? ""}
          onChange={(e) =>
            setForm({ condition_operator: e.target.value || (isCreate ? null : undefined) })
          }
          bg="white"
          placeholder="—"
        >
          {CONDITION_OPERATORS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <NumberInput
          value={form.threshold_value ?? ""}
          onChange={(_s, val) => {
            const next = Number.isNaN(val) ? (isCreate ? null : undefined) : val;
            const capped =
              signal && signal !== "latency" && typeof next === "number" ? Math.min(100, next) : next;
            setForm({ threshold_value: capped });
          }}
          min={0}
          max={signal && signal !== "latency" ? 100 : undefined}
          bg="white"
        >
          <NumberInputField placeholder={isCreate ? "Enter value" : "Value"} />
          <NumberInputStepper>
            <NumberIncrementStepper />
            <NumberDecrementStepper />
          </NumberInputStepper>
        </NumberInput>
        {signal === "latency" ? (
          <Select
            value={form.threshold_unit ?? "ms"}
            onChange={(e) => setForm({ threshold_unit: e.target.value || "ms" })}
            bg="white"
          >
            {LATENCY_THRESHOLD_UNITS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        ) : (
          <Box
            px={3}
            py={2}
            bg="gray.100"
            borderRadius="md"
            borderWidth="1px"
            borderColor="gray.200"
            textAlign="center"
            fontSize="sm"
            color={signal ? "gray.700" : "gray.400"}
            fontWeight="medium"
          >
            {signal ? PERCENTAGE_UNIT : "—"}
          </Box>
        )}
      </SimpleGrid>
      <FormErrorMessage>
        {isCreate
          ? (errors?.condition_operator ?? errors?.threshold_value ?? errors?.threshold_unit)
          : (errors?.condition_operator ?? errors?.threshold_value)}
      </FormErrorMessage>
    </FormControl>
  );
}
