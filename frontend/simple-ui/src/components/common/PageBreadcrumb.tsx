import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  type BreadcrumbProps,
} from "@chakra-ui/react";
import { ChevronRightIcon } from "@chakra-ui/icons";
import NextLink from "next/link";
import React from "react";
import { getServiceTitle, PATH_TO_SERVICE_ID } from "../../config/serviceMetadata";
import { APP_HOME_PATH } from "../../utils/navigation";

export type Crumb = {
  label: string;
  href?: string;
  /**
   * Runs on click in addition to `href`. Manage detail pages use this to
   * clear in-memory create/view state when the list route is already current.
   */
  /** Return path is skipped when this calls `preventDefault`. */
  onClick?: (event: React.MouseEvent) => void;
};

/**
 * Breadcrumb rules:
 * - Top-level sidebar pages (e.g. Logs Dashboard, Alerts & Notifications,
 *   Institution Management) show no breadcrumb.
 * - The landing page (Usage Dashboard) is never prepended to another
 *   section's breadcrumb.
 * - Detail/nested pages show a trail: parent section, then current page
 *   (Explore → Try-it service; Pipeline → Pipeline Builder; Manage list →
 *   record).
 * Labels come from the page title / service metadata — never raw URL segments.
 */
export function getPageBreadcrumbs(
  pathname: string,
  pageTitle: string,
): Crumb[] | null {
  if (!pathname || pathname.startsWith("/auth")) return null;

  const title = pageTitle.trim();
  if (!title) return null;

  // Nested under the Pipeline service page: Pipeline -> current page.
  if (pathname === "/pipeline-builder") {
    return [
      { label: getServiceTitle("pipeline"), href: "/pipeline" },
      { label: title },
    ];
  }

  // Try-it pages are opened from Explore cards, not the sidebar.
  if (PATH_TO_SERVICE_ID[pathname]) {
    return [
      { label: "Explore", href: APP_HOME_PATH },
      { label: title },
    ];
  }

  // Sidebar / other top-level pages have no parent section to show.
  return null;
}

type ManageParent = {
  label: string;
  href: string;
  /** Call `preventDefault` to keep the crumb from navigating. */
  onNavigate?: (event: React.MouseEvent) => void;
};

/**
 * Manage list (link) → current record/page (not a link), e.g.
 * Institution Management → 365works. No landing page is prepended, and
 * the trail follows the page hierarchy regardless of how the user
 * reached the page. The parent always targets the list route, never
 * history back.
 */
export function buildManageCrumbs(
  parent: ManageParent,
  currentLabel: string,
): Crumb[] {
  return [
    { label: parent.label, href: parent.href, onClick: parent.onNavigate },
    { label: currentLabel },
  ];
}

type PageBreadcrumbProps = {
  items: Crumb[];
} & Omit<BreadcrumbProps, "children">;

/** Compact, muted trail. Parent levels are links; the current page is stronger. */
export default function PageBreadcrumb({ items, ...rest }: PageBreadcrumbProps) {
  // A lone crumb is a top-level page, which shows no breadcrumb.
  if (items.length < 2) return null;

  return (
    <Breadcrumb
      fontSize="xs"
      separator={<ChevronRightIcon color="ink.400" boxSize={3} />}
      mb={2}
      {...rest}
    >
      {items.map((item, index) => {
        const href = item.href;
        const isCurrent = index === items.length - 1 || !href;
        return (
          <BreadcrumbItem key={`${item.label}-${index}`} isCurrentPage={isCurrent}>
            {isCurrent || !href ? (
              <BreadcrumbLink
                as="span"
                color="ink.800"
                fontWeight="600"
                cursor="default"
                _hover={{ textDecoration: "none" }}
              >
                {item.label}
              </BreadcrumbLink>
            ) : (
              <NextLink href={href} passHref legacyBehavior>
                <BreadcrumbLink
                  color="ink.500"
                  fontWeight="500"
                  _hover={{ color: "ink.800", textDecoration: "none" }}
                  onClick={(event) => item.onClick?.(event)}
                >
                  {item.label}
                </BreadcrumbLink>
              </NextLink>
            )}
          </BreadcrumbItem>
        );
      })}
    </Breadcrumb>
  );
}
