import { FormControl, FormErrorMessage, FormLabel, Select, SimpleGrid, Text } from "@chakra-ui/react";
import { EVAL_INTERVALS, FORM_REQUIRED_ASTERISK } from "../../constants";
import { getAllowedForDurations } from "../../utils";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionTimingFields({ mode, defs }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const form = isCreate ? defs.createForm : defs.updateForm;
  const errors = isCreate ? defs.createErrors : defs.updateErrors;
  const evalInterval = form.evaluation_interval ?? "30s";

  const setForm = (patch: Record<string, unknown>) =>
    isCreate
      ? defs.setCreateForm({ ...defs.createForm, ...patch })
      : defs.setUpdateForm({ ...defs.updateForm, ...patch });

  const forDurationValue = (() => {
    const allowed = getAllowedForDurations(evalInterval);
    const cur = form.for_duration ?? (isCreate ? "" : "5m");
    return allowed.includes(cur) ? cur : allowed[0];
  })();

  const timingFields = (
    <>
      <FormControl isRequired isInvalid={isCreate ? !!errors?.evaluation_interval : Boolean(errors?.evaluation_interval)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          Evaluation Interval
        </FormLabel>
        <Select
          value={evalInterval}
          onChange={(e) => {
            const newEval = e.target.value;
            if (isCreate) {
              setForm({ evaluation_interval: newEval, for_duration: "" });
              return;
            }
            const allowed = getAllowedForDurations(newEval);
            const currentFor = defs.updateForm.for_duration ?? "5m";
            const newFor = allowed.includes(currentFor) ? currentFor : allowed[0];
            setForm({ evaluation_interval: newEval, for_duration: newFor });
          }}
          bg="white"
          placeholder={isCreate ? "Select evaluation interval" : undefined}
        >
          {EVAL_INTERVALS.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </Select>
        {isCreate && <Text fontSize="xs" color="gray.500" mt={1}>How often to check</Text>}
        <FormErrorMessage>{errors?.evaluation_interval}</FormErrorMessage>
      </FormControl>

      <FormControl isRequired isInvalid={isCreate ? !!errors?.for_duration : Boolean(errors?.for_duration)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          For Duration
        </FormLabel>
        <Select
          value={forDurationValue}
          onChange={(e) => setForm({ for_duration: e.target.value })}
          bg="white"
          placeholder={
            isCreate
              ? evalInterval
                ? "Select for duration"
                : "Select an evaluation interval first"
              : undefined
          }
          isDisabled={isCreate && !evalInterval}
        >
          {getAllowedForDurations(evalInterval).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </Select>
        {isCreate && (
          <Text fontSize="xs" color="gray.500" mt={1}>
            Alert fires only after the condition is met continuously for this duration.
          </Text>
        )}
        <FormErrorMessage>{errors?.for_duration}</FormErrorMessage>
      </FormControl>
    </>
  );

  if (isCreate) {
    return <SimpleGrid columns={2} spacing={4}>{timingFields}</SimpleGrid>;
  }

  return <>{timingFields}</>;
}
