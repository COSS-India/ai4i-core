import { Box, VStack, type BoxProps } from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useCallback } from "react";
import { useAuth } from "../../hooks/useAuth";
import { getHomePath } from "../../utils/navigation";
import ManagementPageHeader from "./ManagementPageHeader";
import { buildManageCrumbs } from "./PageBreadcrumb";

type FormPageParent = {
  label: string;
  href: string;
  /** Clears in-memory workflow state. The crumb still navigates to `href`. */
  onNavigate?: () => void;
};

/** Explicit Cancel/Back destination. Never used to build breadcrumbs. */
export type FormPageReturnTo = {
  href: string;
};

/**
 * Same-origin path for Cancel/Back (`pathname + search + hash`).
 * Resolves against this origin so control characters and protocol-relative
 * values cannot leave the app. Returns null when the target is external.
 */
export function safeFormReturnHref(href: string): string | null {
  if (typeof window === "undefined" || !href.trim()) return null;
  try {
    const url = new URL(href, window.location.origin);
    if (url.origin !== window.location.origin) return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

/**
 * Cancel/Back leaves via `returnTo` when set. Otherwise runs `onLeave`
 * and stays on the current page. Does not use history back.
 */
export function useFormPageLeave(
  returnTo: FormPageReturnTo | undefined,
  onLeave?: () => void,
) {
  const router = useRouter();
  return useCallback(() => {
    const href = returnTo?.href;
    onLeave?.();
    const path = href ? safeFormReturnHref(href) : null;
    if (path) {
      void router.push(path);
    }
  }, [onLeave, returnTo?.href, router]);
}

type FormPageControls = {
  leave: () => void;
};

type FormPageProps = {
  title: string;
  description?: string;
  /** Manage list this form belongs to. Becomes the middle breadcrumb. */
  parent: FormPageParent;
  /**
   * Where Cancel/Back returns. Independent of `parent`.
   * Omit when leaving should stay on this manage page.
   */
  returnTo?: FormPageReturnTo;
  /** Clears in-memory workflow state. Does not navigate. */
  onLeave?: () => void;
  /** Lifecycle controls (publish, activate). Form submit lives in `footer`. */
  actions?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode | ((controls: FormPageControls) => React.ReactNode);
  /** Form measure. The institution detail workspace opts out. */
  maxW?: BoxProps["maxW"];
};

/**
 * Create / Edit / View page for Manage entities.
 * Header, width, section stack, and footer are shared. Field sections stay
 * in the entity form.
 */
export default function FormPage({
  title,
  description,
  parent,
  returnTo,
  onLeave,
  actions,
  children,
  footer,
  maxW = "4xl",
}: FormPageProps) {
  const { user } = useAuth();
  const leave = useFormPageLeave(returnTo, onLeave);
  // Breadcrumbs follow the resource (`parent`), never the entry point.
  const crumbs = buildManageCrumbs(parent, title, getHomePath(user?.roles));
  const footerNode = typeof footer === "function" ? footer({ leave }) : footer;

  return (
    <Box w="full" maxW={maxW}>
      <ManagementPageHeader
        title={title}
        description={description}
        actions={actions}
        crumbs={crumbs}
      />
      <VStack align="stretch" spacing={0} w="full">
        {children}
        {footerNode ? (
          <Box mt={6} pt={4} borderTopWidth="1px" borderColor="ink.200">
            {footerNode}
          </Box>
        ) : null}
      </VStack>
    </Box>
  );
}
