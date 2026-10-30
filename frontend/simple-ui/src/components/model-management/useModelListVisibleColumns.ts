import { useCallback, useLayoutEffect, useState } from "react";
import { authService } from "../../services/authService";
import {
  MODEL_LIST_COLUMNS,
  defaultModelListColumnIds,
  type ModelListColumnDef,
} from "./modelListColumns";
import {
  loadVisibleModelColumns,
  nextVisibleModelColumnIds,
  persistVisibleModelColumns,
  resetVisibleModelColumns,
} from "./modelColumnPreferences";

type ModelSort = {
  sort: { key: string; direction: "asc" | "desc" };
  onSortChange: (next: { key: string; direction: "asc" | "desc" }) => void;
};

/**
 * Visible columns for the Model List. FE-only persistence uses localStorage
 * until BE registers the `model-list` preferences view (then set usesServer).
 */
export function useModelListVisibleColumns(options: {
  userId: string;
  catalogue?: readonly ModelListColumnDef[];
  /** When true, GET/PUT/DELETE `/preferences/columns/model-list`. */
  usesServer?: boolean;
  modelSort: ModelSort;
}) {
  const {
    userId,
    catalogue = MODEL_LIST_COLUMNS,
    usesServer = false,
    modelSort,
  } = options;
  const resolvedCatalogue = catalogue;

  const [visibleColumnIds, setVisibleColumnIds] = useState<string[]>(() =>
    defaultModelListColumnIds(resolvedCatalogue),
  );
  const catalogueKey = resolvedCatalogue.map((column) => column.id).join("|");
  const [loadedCatalogueKey, setLoadedCatalogueKey] = useState<string | null>(null);

  const preferenceUserId = useCallback(
    () => userId || authService.getStoredUser()?.user_id || "",
    [userId],
  );

  useLayoutEffect(() => {
    const id = preferenceUserId();
    if (!id) return;
    let cancelled = false;
    loadVisibleModelColumns({
      userId: id,
      usesServer,
      catalogue: resolvedCatalogue,
    })
      .then((next) => {
        if (cancelled) return;
        setVisibleColumnIds((current) => nextVisibleModelColumnIds(current, next));
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadedCatalogueKey(catalogueKey);
      });
    return () => {
      cancelled = true;
    };
  }, [preferenceUserId, usesServer, catalogueKey, resolvedCatalogue]);

  const resetSortIfColumnHidden = useCallback(
    (visibleIds: readonly string[]) => {
      const sortKey = modelSort.sort.key;
      if (!sortKey) return;
      if (visibleIds.includes(sortKey)) return;
      modelSort.onSortChange({ key: "name", direction: "asc" });
    },
    [modelSort],
  );

  const applyVisibleColumns = useCallback(
    (next: readonly string[]) => {
      const resolved = persistVisibleModelColumns({
        userId: preferenceUserId(),
        usesServer,
        catalogue: resolvedCatalogue,
        columnIds: next,
      });
      setVisibleColumnIds(resolved);
      resetSortIfColumnHidden(resolved);
    },
    [preferenceUserId, resetSortIfColumnHidden, resolvedCatalogue, usesServer],
  );

  const resetVisibleColumns = useCallback(() => {
    void resetVisibleModelColumns({
      userId: preferenceUserId(),
      usesServer,
      catalogue: resolvedCatalogue,
    }).then((resolved) => {
      setVisibleColumnIds((current) => nextVisibleModelColumnIds(current, resolved));
      resetSortIfColumnHidden(resolved);
    });
  }, [preferenceUserId, resetSortIfColumnHidden, resolvedCatalogue, usesServer]);

  return {
    visibleColumnIds,
    visibleColumnsReady: loadedCatalogueKey === catalogueKey,
    applyVisibleColumns,
    resetVisibleColumns,
  };
}
