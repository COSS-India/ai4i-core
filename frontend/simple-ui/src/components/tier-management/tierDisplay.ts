export function getTaskTypeBadgeColor(taskType: string): string {
  switch (taskType.toUpperCase()) {
    case "LLM":
      return "purple";
    case "ASR":
      return "orange";
    case "NMT":
      return "green";
    case "TTS":
      return "blue";
    case "OCR":
      return "teal";
    case "PIPELINE":
      return "pink";
    case "NER":
      return "red";
    default:
      return "gray";
  }
}

export const framedList = {
  spacing: 0,
  borderWidth: "1px",
  borderColor: "ink.200",
  borderRadius: "10px",
  overflow: "hidden",
};

export const framedRow = {
  px: 3,
  py: "11px",
  borderBottomWidth: "1px",
  borderColor: "ink.100",
  _last: { borderBottomWidth: 0 },
};

export const framedEmpty = {
  textAlign: "center" as const,
  py: 4,
  px: 3,
  borderWidth: "1px",
  borderStyle: "dashed",
  borderColor: "ink.200",
  borderRadius: "10px",
};
