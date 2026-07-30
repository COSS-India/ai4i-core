// Map a yaml task-type name (hyphen form, as exposed by /inference-types and
// NEXT_PUBLIC_ENABLED_TASK_TYPES) to the metering service key the backend uses
// in SERVICE_BREAKDOWN_CONFIG / heatmap responses (underscore form). Single
// source so the metering `services=` filter and the service-breakdown filter
// can't drift apart.
//
// Special case: audio language detection is `audio-lang-detection` in the yaml
// but `audio_language_detection` in the metering config.
const YAML_TO_METERING_KEY: Record<string, string> = {
  "audio-lang-detection": "audio_language_detection",
};

export function toMeteringKey(taskTypeName: string): string {
  const k = taskTypeName.trim().toLowerCase();
  return YAML_TO_METERING_KEY[k] ?? k.replace(/-/g, "_");
}
