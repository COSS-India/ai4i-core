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
 * Visible columns for the Model List (browser-local for 2.11).
 * Server prefs (`model-list` view) are a follow-up.
 */
export function useModelListVisibleColumns(options: {
  userId: string;
  catalogue?: readonly ModelListColumnDef[];
  modelSort: ModelSort;
}) {
  const {
    userId,
    catalogue = MODEL_LIST_COLUMNS,
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
    const next = loadVisibleModelColumns({
      userId: id,
      catalogue: resolvedCatalogue,
    });
    setVisibleColumnIds((current) => nextVisibleModelColumnIds(current, next));
    setLoadedCatalogueKey(catalogueKey);
  }, [preferenceUserId, catalogueKey, resolvedCatalogue]);

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
        catalogue: resolvedCatalogue,
        columnIds: next,
      });
      setVisibleColumnIds(resolved);
      resetSortIfColumnHidden(resolved);
    },
    [preferenceUserId, resetSortIfColumnHidden, resolvedCatalogue],
  );

  const resetVisibleColumns = useCallback(() => {
    const resolved = resetVisibleModelColumns({
      userId: preferenceUserId(),
      catalogue: resolvedCatalogue,
    });
    setVisibleColumnIds((current) => nextVisibleModelColumnIds(current, resolved));
    resetSortIfColumnHidden(resolved);
  }, [preferenceUserId, resetSortIfColumnHidden, resolvedCatalogue]);

  return {
    visibleColumnIds,
    visibleColumnsReady: loadedCatalogueKey === catalogueKey,
    applyVisibleColumns,
    resetVisibleColumns,
  };
}
