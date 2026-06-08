import { FormControl, FormErrorMessage, FormLabel, Select } from "@chakra-ui/react";
import {
  CATEGORIES,
  PERCENTAGE_UNIT,
  SIGNAL_METRICS_BY_SIGNAL,
  SIGNALS_BY_SUB_CATEGORY,
  SUB_CATEGORIES_BY_CATEGORY,
} from "../../../../../types/alerting";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import OptionSelector from "../../OptionSelector";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionClassificationFields({ mode, defs }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const form = isCreate ? defs.createForm : defs.updateForm;
  const errors = isCreate ? defs.createErrors : defs.updateErrors;
  const category = form.category ?? (isCreate ? "" : "application");
  const subCategory = form.sub_category ?? "";
  const signal = form.signal ?? "";

  const setForm = (patch: Record<string, unknown>) =>
    isCreate
      ? defs.setCreateForm({ ...defs.createForm, ...patch })
      : defs.setUpdateForm({ ...defs.updateForm, ...patch });

  return (
    <>
      <FormControl isRequired isInvalid={isCreate ? !!errors?.category : Boolean(errors?.category)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          Category
        </FormLabel>
        <OptionSelector
          options={CATEGORIES}
          value={category}
          onChange={(v) =>
            setForm({
              category: v,
              sub_category: null,
              signal: null,
              signal_metric: null,
              ...(isCreate
                ? {}
                : { condition_operator: null, service: v === "infrastructure" ? undefined : defs.updateForm.service }),
            })
          }
        />
        <FormErrorMessage>{errors?.category}</FormErrorMessage>
      </FormControl>

      <FormControl isRequired isInvalid={isCreate ? !!errors?.sub_category : Boolean(errors?.sub_category)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          Subcategory
        </FormLabel>
        <Select
          value={subCategory}
          onChange={(e) =>
            setForm({
              sub_category: e.target.value || null,
              signal: null,
              signal_metric: null,
              threshold_value: isCreate ? null : undefined,
              threshold_unit: undefined,
            })
          }
          bg="white"
          placeholder={category ? "Select subcategory..." : "Select a category first"}
          isDisabled={!category}
        >
          {(SUB_CATEGORIES_BY_CATEGORY[category] ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <FormErrorMessage>{errors?.sub_category}</FormErrorMessage>
      </FormControl>

      <FormControl isRequired isInvalid={isCreate ? !!errors?.signal : Boolean(errors?.signal)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          Signal
        </FormLabel>
        <Select
          value={signal}
          onChange={(e) => {
            const sig = e.target.value || null;
            setForm({
              signal: sig,
              signal_metric: null,
              threshold_value: isCreate ? null : undefined,
              threshold_unit: sig === "latency" ? "ms" : sig ? PERCENTAGE_UNIT : undefined,
            });
          }}
          bg="white"
          placeholder={subCategory ? "Select signal..." : "Select a subcategory first"}
          isDisabled={!subCategory}
        >
          {(SIGNALS_BY_SUB_CATEGORY[subCategory] ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <FormErrorMessage>{errors?.signal}</FormErrorMessage>
      </FormControl>

      <FormControl isRequired isInvalid={isCreate ? !!errors?.signal_metric : Boolean(errors?.signal_metric)}>
        <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
          Signal Metric
        </FormLabel>
        <Select
          value={form.signal_metric ?? ""}
          onChange={(e) => setForm({ signal_metric: e.target.value || null })}
          bg="white"
          placeholder={signal ? "Select metric..." : isCreate ? "Select a signal type first" : "Select a signal first"}
          isDisabled={!signal}
        >
          {(SIGNAL_METRICS_BY_SIGNAL[signal] ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <FormErrorMessage>{errors?.signal_metric}</FormErrorMessage>
      </FormControl>
    </>
  );
}
