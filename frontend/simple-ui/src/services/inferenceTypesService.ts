import { z } from "zod";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import { unwrapPlatformDataEnvelope } from "./dto/unwrap";

export interface InferenceTypeItem {
  name: string;
  endpoint_pattern: string;
  unit: string;
}

const inferenceTypeItemSchema = z.object({
  name: z.string(),
  endpoint_pattern: z.string(),
  unit: z.string(),
});

// API shape: { data: { inference_types: [...] } }
const inferenceTypesResponseSchema = z.preprocess((raw) => {
  const data = unwrapPlatformDataEnvelope(raw);
  if (data && typeof data === "object" && "inference_types" in data) {
    return (data as { inference_types: unknown }).inference_types;
  }
  return data;
}, z.array(inferenceTypeItemSchema));

export async function fetchInferenceTypes(): Promise<InferenceTypeItem[]> {
  try {
    const response = await apiService.get(
      apiEndpoints.platform.inferenceTypes,
      {
        suppressErrorAlert: true,
        responseSchema: inferenceTypesResponseSchema,
      },
    );
    return response.data ?? [];
  } catch (error: unknown) {
    console.error("Fetch inference types error:", error);
    throw error;
  }
}
