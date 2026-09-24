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
import { APP_HOME_PATH, USAGE_DASHBOARD_PATH } from "../../utils/navigation";

export type Crumb = {
  label: string;
  href?: string;
};

function homeCrumb(homePath: string): Crumb {
  const path = homePath.split("?")[0];
  if (path === USAGE_DASHBOARD_PATH) {
    return { label: "Usage Dashboard", href: homePath };
  }
  return { label: "Explore", href: APP_HOME_PATH };
}

/**
 * Trail for inner pages. Home and auth are omitted (no useful parent).
 * Labels come from the page title / service metadata — never raw URL segments.
 */
export function getPageBreadcrumbs(
  pathname: string,
  pageTitle: string,
  homePath: string = APP_HOME_PATH,
): Crumb[] | null {
  if (!pathname || pathname.startsWith("/auth")) return null;

  const home = homeCrumb(homePath);
  const homePathname = (home.href ?? APP_HOME_PATH).split("?")[0];
  if (pathname === homePathname) return null;

  const title = pageTitle.trim();
  if (!title) return null;

  if (pathname === "/pipeline-builder") {
    return [
      home,
      { label: getServiceTitle("pipeline"), href: "/pipeline" },
      { label: title },
    ];
  }

  const serviceId = PATH_TO_SERVICE_ID[pathname];
  if (serviceId) {
    return [home, { label: title }];
  }

  return [home, { label: title }];
}

type PageBreadcrumbProps = {
  items: Crumb[];
} & Omit<BreadcrumbProps, "children">;

/** Compact, muted trail. Parent levels are links; the current page is stronger. */
export default function PageBreadcrumb({ items, ...rest }: PageBreadcrumbProps) {
  if (items.length < 2) return null;

  return (
    <Breadcrumb
      fontSize="sm"
      separator={<ChevronRightIcon color="ink.400" boxSize={3.5} />}
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
