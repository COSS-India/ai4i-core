import { Text } from "@chakra-ui/react";

export const EVAL_INTERVALS = ["30s", "1m", "5m"] as const;
export const FOR_DURATIONS = ["1m", "2m", "5m", "10m"] as const;

/** Allowed "For Duration" options per "Evaluation Interval" (for_duration should be >= eval interval). */
export const FOR_DURATION_BY_EVAL_INTERVAL: Record<string, readonly string[]> = {
  "30s": ["1m", "2m", "5m"],
  "1m": ["2m", "5m", "10m"],
  "5m": ["5m", "10m"],
};

/** Visible mandatory-field marker used with `FormControl isRequired`. */
export const FORM_REQUIRED_ASTERISK = (
  <Text as="span" color="red.500" ml={1} aria-hidden>
    *
  </Text>
);

export const ALERT_TYPES_BY_CATEGORY: Record<string, { value: string; label: string }[]> = {
  application: [
    { value: "latency", label: "Latency" },
    { value: "error_rate", label: "Error Rate" },
  ],
  infrastructure: [
    { value: "CPU", label: "CPU" },
    { value: "Memory", label: "Memory" },
    { value: "Disk", label: "Disk" },
  ],
};
