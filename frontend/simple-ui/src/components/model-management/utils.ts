export const SAMPLE_MODEL_JSON = {
  version: "1.0.0",
  name: "example-model",
  description: "A sample model for demonstration purposes",
  refUrl: "https://github.com/example/example-model",
  task: {
    type: "asr",
  },
  languages: [
    {
      sourceLanguage: "hi",
      sourceScriptCode: "Deva",
      targetLanguage: "hi",
      targetScriptCode: "Deva",
    },
  ],
  license: "mit",
  domain: ["general"],
  inferenceEndPoint: {
    schema: {
      modelProcessingType: {
        type: "batch",
      },
      request: {
        input: [
          {
            audio: "base64_encoded_audio_string",
          },
        ],
        config: {
          language: {
            sourceLanguage: "hi",
          },
        },
      },
      response: {
        output: [
          {
            transcript: "string",
          },
        ],
      },
    },
  },
  benchmarks: [
    {
      benchmarkId: "example-benchmark-001",
      name: "Example Benchmark",
      description: "Sample benchmark for evaluation",
      domain: "general",
      createdOn: "2025-01-15T10:00:00.000Z",
      languages: {
        sourceLanguage: "hi",
        targetLanguage: "hi",
      },
      score: [
        {
          metricName: "WER",
          score: "7.5",
        },
      ],
    },
  ],
  submitter: {
    name: "Example Organization",
    aboutMe: "An example organization",
    team: [
      {
        name: "John Doe",
        aboutMe: "Lead Researcher",
        oauthId: {
          oauthId: "1234567890",
          provider: "google",
        },
      },
    ],
  },
};

export function getTaskColor(taskType: string): string {
  switch (taskType.toLowerCase()) {
    case "asr":
      return "orange";
    case "nmt":
      return "green";
    case "tts":
      return "blue";
    default:
      return "gray";
  }
}

export function validateModelData(data: Record<string, unknown>): string[] {
  const errors: string[] = [];

  // modelId is server-generated from name + version; not required in upload JSON

  if (!data.name || typeof data.name !== "string" || data.name.trim() === "") {
    errors.push("name is required and must be a non-empty string");
  }

  if (!data.version || typeof data.version !== "string" || data.version.trim() === "") {
    errors.push("version is required and must be a non-empty string");
  }

  if (!data.description || typeof data.description !== "string" || data.description.trim() === "") {
    errors.push("description is required and must be a non-empty string");
  }

  const task = data.task as { type?: string } | undefined;
  if (!task || typeof task !== "object" || !task.type) {
    errors.push("task is required and must be an object with a type field");
  }

  if (!data.languages || !Array.isArray(data.languages) || data.languages.length === 0) {
    errors.push("languages is required and must be a non-empty array");
  }

  if (!data.license || typeof data.license !== "string" || data.license.trim() === "") {
    errors.push("license is required and must be a non-empty string");
  }

  if (!data.domain || !Array.isArray(data.domain) || data.domain.length === 0) {
    errors.push("domain is required and must be a non-empty array");
  }

  if (!data.inferenceEndPoint || typeof data.inferenceEndPoint !== "object") {
    errors.push("inferenceEndPoint is required and must be an object");
  }

  const submitter = data.submitter as { name?: string } | undefined;
  if (!submitter || typeof submitter !== "object" || !submitter.name) {
    errors.push("submitter is required and must be an object with a name field");
  }

  // Validate model name format (alphanumeric, hyphens, forward slashes only)
  if (data.name && typeof data.name === "string") {
    const namePattern = /^[a-zA-Z0-9/-]+$/;
    if (!namePattern.test(data.name)) {
      errors.push(
        'name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). Example: "example-model" or "org/model-name"'
      );
    }
  }

  return errors;
}

export function downloadSampleModelJson(): void {
  const blob = new Blob([JSON.stringify(SAMPLE_MODEL_JSON, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "sample-model.json";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
