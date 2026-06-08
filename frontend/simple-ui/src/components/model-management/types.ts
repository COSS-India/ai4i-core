import type { ModelDetails } from "../../types/platform";

/** Registry UI model row — requires fields used in forms/tables. */
export type Model = ModelDetails & {
  name: string;
  description: string;
  languages: Record<string, unknown>[];
  domain: string[];
  license: string;
  inferenceEndPoint: NonNullable<ModelDetails["inferenceEndPoint"]>;
  source: string;
  task: NonNullable<ModelDetails["task"]>;
};
