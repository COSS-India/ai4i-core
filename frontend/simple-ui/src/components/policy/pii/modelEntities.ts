import { piiService } from "../../../services/piiService";

/** GET /pii/entities per language code, shared by every drawer. A failed request is dropped so it can be retried. */
const entityRequests = new Map<string, Promise<string[]>>();

export function loadModelEntities(language: string): Promise<string[]> {
  let request = entityRequests.get(language);
  if (!request) {
    request = piiService.getSupportedEntities(language);
    entityRequests.set(language, request);
    request.catch(() => entityRequests.delete(language));
  }
  return request;
}
