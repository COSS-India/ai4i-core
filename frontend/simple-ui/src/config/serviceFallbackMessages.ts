import { INSTITUTION } from "./constants";

/** Copy for Application service fallbacks (AI4IDS-3488). */
export const SERVICE_FALLBACK_COPY = {
  createdPrompt: {
    body:
      "Set up service fallbacks so requests keep succeeding if a service is unavailable. " +
      "Fallbacks apply to every API key of this Application.",
    optionalNote: "Optional. You can configure this any time from the Application details.",
    skip: "Skip for now",
    configure: "Configure fallbacks",
  },
  editor: {
    title: "Service fallbacks",
    description:
      "If a primary service is unavailable, requests from every API key of this Application go to its fallback.",
    tierLabel: "Tier",
    emptyTitle: "No fallbacks configured",
    emptyBody:
      "Choose a primary service and the fallback to use when the primary is unavailable. Fallbacks are optional.",
    addFallback: "Add fallback",
    rowTitle: (index: number) => `Fallback ${index + 1}`,
    remove: "Remove",
    primaryService: "Primary service",
    fallbackService: "Fallback service",
    selectPrimary: "Select service",
    selectFallback: "Select service",
    unavailableOption: (id: string) => `${id} (no longer available)`,
    sameModel: "Same model. Output stays consistent.",
    differentModel: "Different model. Output may differ when used.",
    noAlternatives:
      "No other service is available in this Tier. Each task type has only one published service, so there is nothing to fall back to.",
    staleTitle: "Some saved fallbacks are no longer used",
    staleBody:
      "They name a service that is no longer published in this Tier. Remove them, or pick another service, before saving.",
    removeStale: "Remove them",
    inactiveNote:
      "This Application is inactive, so its fallbacks are not used until it is activated again.",
    noTier: `This ${INSTITUTION} is not mapped to a Tier, so fallbacks cannot be configured.`,
    loading: "Loading services in this Tier…",
    loadFailed: "Could not load the services in this Tier.",
    retry: "Retry",
    close: "Close",
    cancel: "Cancel",
    save: "Save changes",
    saving: "Saving...",
    statusClean: "No unsaved changes",
    statusChanges: (count: number) => `${count} unsaved change${count === 1 ? "" : "s"}`,
    statusIncomplete: "Select a primary and fallback in every fallback to save.",
    statusStale: "Remove fallbacks that are no longer available to save.",
    saved: "Service fallbacks saved.",
  },
  action: {
    label: "Service fallbacks",
    notConfigured: "Not configured. Click to set up.",
    configured: (count: number) =>
      `${count} fallback${count === 1 ? "" : "s"} configured. Click to edit.`,
  },
  details: {
    none: "No fallbacks set",
    configure: "Configure fallbacks",
    edit: "Edit fallbacks",
    unavailable: "no longer available",
  },
} as const;

export function applicationCreatedTitle(name?: string | null): string {
  const trimmed = name?.trim();
  return trimmed ? `${trimmed} created` : "Application created";
}

export function fallbackEditorDescription(applicationName?: string | null): string {
  const name = applicationName?.trim();
  const body = SERVICE_FALLBACK_COPY.editor.description;
  return name ? `${name} · ${body}` : body;
}
