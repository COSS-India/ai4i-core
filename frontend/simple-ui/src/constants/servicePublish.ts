// Service publish state (services-management)

/** Service publish state (services-management). */
export const SERVICE_PUBLISH = {
  FILTER: {
    ALL: "",
    PUBLISHED: "published",
    UNPUBLISHED: "unpublished",
  },
  LABEL: {
    PUBLISHED: "Published",
    UNPUBLISHED: "Unpublished",
  },
} as const;

export const SERVICE_PUBLISH_FILTER_LIST: readonly (typeof SERVICE_PUBLISH.FILTER)["PUBLISHED" | "UNPUBLISHED"][] =
  [SERVICE_PUBLISH.FILTER.PUBLISHED, SERVICE_PUBLISH.FILTER.UNPUBLISHED];

export function isServicePublishFilterStatus(
  actual: string,
  expected: (typeof SERVICE_PUBLISH.FILTER)["PUBLISHED"] | (typeof SERVICE_PUBLISH.FILTER)["UNPUBLISHED"]
): boolean {
  return actual.trim().toLowerCase() === expected;
}

export function formatServicePublishLabel(isPublished: boolean): string {
  return isPublished ? SERVICE_PUBLISH.LABEL.PUBLISHED : SERVICE_PUBLISH.LABEL.UNPUBLISHED;
}

export function formatServicePublishFilterLabel(filter: string): string {
  if (isServicePublishFilterStatus(filter, SERVICE_PUBLISH.FILTER.PUBLISHED)) {
    return SERVICE_PUBLISH.LABEL.PUBLISHED;
  }
  if (isServicePublishFilterStatus(filter, SERVICE_PUBLISH.FILTER.UNPUBLISHED)) {
    return SERVICE_PUBLISH.LABEL.UNPUBLISHED;
  }
  return filter;
}
