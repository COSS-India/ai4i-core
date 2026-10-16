import { MODEL_FIELD_LIMITS } from "../../config/constants";

export const validateModelData = (data: any): string[] => {
  const errors: string[] = [];
  const {
    NAME_MIN,
    NAME_MAX,
    VERSION_MIN,
    VERSION_MAX,
    DESCRIPTION_MIN,
    DESCRIPTION_MAX,
    REF_URL_MIN,
    REF_URL_MAX,
    LICENSE_URL_MAX,
    SUBMITTER_NAME_MIN,
    SUBMITTER_NAME_MAX,
    TEAM_NAME_MIN,
    TEAM_NAME_MAX,
  } = MODEL_FIELD_LIMITS;

  // Enum membership (license/domain/language/script) is enforced by the API —
  // do not duplicate ULCA closed lists here. Validate shape + lengths only.

  if (!data.name || typeof data.name !== "string" || data.name.trim() === "") {
    errors.push("name is required and must be a non-empty string");
  } else {
    const name = data.name.trim();
    if (name.length < NAME_MIN || name.length > NAME_MAX) {
      errors.push(`name must be ${NAME_MIN}–${NAME_MAX} characters (got ${name.length})`);
    }
    if (/\s/.test(name)) {
      errors.push("name must not contain spaces");
    }
    const namePattern = /^[a-zA-Z0-9/-]+$/;
    if (!namePattern.test(name)) {
      errors.push(
        'name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). Example: "example-model" or "org/model-name"'
      );
    }
  }

  if (!data.version || typeof data.version !== "string" || data.version.trim() === "") {
    errors.push("version is required and must be a non-empty string");
  } else if (
    data.version.trim().length < VERSION_MIN ||
    data.version.trim().length > VERSION_MAX
  ) {
    errors.push(`version must be ${VERSION_MIN}–${VERSION_MAX} characters`);
  }

  if (!data.description || typeof data.description !== "string" || data.description.trim() === "") {
    errors.push("description is required and must be a non-empty string");
  } else {
    const descLen = data.description.length;
    if (descLen < DESCRIPTION_MIN || descLen > DESCRIPTION_MAX) {
      errors.push(
        `description must be ${DESCRIPTION_MIN}–${DESCRIPTION_MAX} characters (got ${descLen})`
      );
    }
  }

  if (data.refUrl != null && data.refUrl !== "") {
    if (typeof data.refUrl !== "string") {
      errors.push("refUrl must be a string when provided");
    } else if (data.refUrl.length < REF_URL_MIN || data.refUrl.length > REF_URL_MAX) {
      errors.push(`refUrl must be ${REF_URL_MIN}–${REF_URL_MAX} characters when provided`);
    }
  }

  if (!data.task || typeof data.task !== "object" || !data.task.type) {
    errors.push("task is required and must be an object with a type field");
  }

  if (data.languages != null && !Array.isArray(data.languages)) {
    errors.push("languages must be an array when provided");
  } else if (Array.isArray(data.languages)) {
    data.languages.forEach((pair: any, index: number) => {
      if (!pair || typeof pair !== "object") {
        errors.push(`languages[${index}] must be an object`);
      } else if (!pair.sourceLanguage || typeof pair.sourceLanguage !== "string") {
        errors.push(`languages[${index}].sourceLanguage is required`);
      }
    });
  }

  if (!data.license || typeof data.license !== "string" || data.license.trim() === "") {
    errors.push("license is required and must be a non-empty string");
  }

  if (data.licenseUrl != null && data.licenseUrl !== "") {
    if (typeof data.licenseUrl !== "string") {
      errors.push("licenseUrl must be a string when provided");
    } else if (data.licenseUrl.length > LICENSE_URL_MAX) {
      errors.push(`licenseUrl must be at most ${LICENSE_URL_MAX} characters`);
    }
  }

  if (!data.domain || !Array.isArray(data.domain) || data.domain.length === 0) {
    errors.push("domain is required and must be a non-empty array");
  }

  if (!data.trainingDataset || typeof data.trainingDataset !== "object") {
    errors.push(
      "trainingDataset is required and must be an object with a description field"
    );
  } else if (
    !data.trainingDataset.description ||
    typeof data.trainingDataset.description !== "string" ||
    data.trainingDataset.description.trim() === ""
  ) {
    errors.push("trainingDataset.description is required and must be a non-empty string");
  }

  if (data.adapterConfig != null) {
    if (typeof data.adapterConfig !== "object" || Array.isArray(data.adapterConfig)) {
      errors.push("adapterConfig must be an object when provided");
    } else {
      if (!Array.isArray((data.adapterConfig as Record<string, unknown>).inputs)) {
        errors.push("adapterConfig.inputs is required and must be an array");
      }
      if (!Array.isArray((data.adapterConfig as Record<string, unknown>).outputs)) {
        errors.push("adapterConfig.outputs is required and must be an array");
      }
    }
  }

  if (data.schema != null) {
    if (typeof data.schema !== "object" || Array.isArray(data.schema)) {
      errors.push("schema must be an object when provided");
    } else if (!(data.schema as Record<string, unknown>).model_name) {
      errors.push("schema.model_name is required");
    }
  }

  if (!data.submitter || typeof data.submitter !== "object" || !data.submitter.name) {
    errors.push("submitter is required and must be an object with a name field");
  } else {
    const submitterName = String(data.submitter.name);
    if (
      submitterName.length < SUBMITTER_NAME_MIN ||
      submitterName.length > SUBMITTER_NAME_MAX
    ) {
      errors.push(
        `submitter.name must be ${SUBMITTER_NAME_MIN}–${SUBMITTER_NAME_MAX} characters`
      );
    }
    if (Array.isArray(data.submitter.team)) {
      data.submitter.team.forEach((member: any, index: number) => {
        if (!member?.name || typeof member.name !== "string") {
          errors.push(`submitter.team[${index}].name is required`);
        } else if (
          member.name.length < TEAM_NAME_MIN ||
          member.name.length > TEAM_NAME_MAX
        ) {
          errors.push(
            `submitter.team[${index}].name must be ${TEAM_NAME_MIN}–${TEAM_NAME_MAX} characters`
          );
        }
      });
    }
  }

  return errors;
};
