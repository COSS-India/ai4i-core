import { useQuery } from "@tanstack/react-query";
import {
  fetchInferenceTypes,
  type InferenceTypeItem,
} from "../services/inferenceTypesService";
import { MODEL_TASK_TYPE_LIST } from "../config/constants";

const INFERENCE_TYPES_QUERY_KEY = "inferenceTypes";

export function useInferenceTypes() {
  const query = useQuery({
    queryKey: [INFERENCE_TYPES_QUERY_KEY],
    queryFn: fetchInferenceTypes,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const inferenceTypes: InferenceTypeItem[] = query.data ?? [];

  // Fall back to the static list if the API hasn't responded or errored
  const taskTypeNames: string[] =
    inferenceTypes.length > 0
      ? inferenceTypes.map((t) => t.name)
      : [...MODEL_TASK_TYPE_LIST];

  // { "asr": "Audio minutes", "llm": "M Tokens", ... } derived from API
  const unitByTaskType: Record<string, string> = Object.fromEntries(
    inferenceTypes.map((t) => [t.name, t.unit]),
  );

  return {
    inferenceTypes,
    taskTypeNames,
    unitByTaskType,
    isLoading: query.isLoading,
  };
}
