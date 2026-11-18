import { useCallback, useLayoutEffect, useState } from "react";
import { authService } from "../../services/authService";
import {
  defaultServiceListColumnIds,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  loadVisibleServiceColumns,
  nextVisibleColumnIds,
  persistVisibleServiceColumns,
  resetVisibleServiceColumns,
} from "./serviceColumnPreferences";

type RegistrySort = {
  mode: "time" | "sorted";
  sort: { key: string; direction: "asc" | "desc" };
  onSortChange: (next: { key: string; direction: "asc" | "desc" }) => void;
};

export function useServiceListVisibleColumns(options: {
  userId: string;
  serviceListCatalogue: readonly ServiceListColumnDef[];
  serviceListUsesServer: boolean;
  registrySort: RegistrySort;
  setRegistryPage: (page: number) => void;
}) {
  const {
    userId,
    serviceListCatalogue,
    serviceListUsesServer,
    registrySort,
    setRegistryPage,
  } = options;

  const [visibleColumnIds, setVisibleColumnIds] = useState<string[]>(() =>
    defaultServiceListColumnIds(serviceListCatalogue),
  );
  const catalogueKey = serviceListCatalogue.map((column) => column.id).join("|");
  // Catalogue the current selection was loaded for. The list fetch waits for
  // this so it never requests columns for a selection that is about to change.
  const [loadedCatalogueKey, setLoadedCatalogueKey] = useState<string | null>(null);

  const preferenceUserId = useCallback(
    () => userId || authService.getStoredUser()?.user_id || "",
    [userId],
  );

  useLayoutEffect(() => {
    // No user id yet → catalogue defaults, so the table is never stuck waiting.
    const next = loadVisibleServiceColumns({
      userId: preferenceUserId(),
      catalogue: serviceListCatalogue,
    });
    setVisibleColumnIds((current) => nextVisibleColumnIds(current, next));
    setLoadedCatalogueKey(catalogueKey);
  }, [preferenceUserId, catalogueKey, serviceListCatalogue]);

  const handleRegistrySortChange = useCallback(
    (next: { key: string; direction: "asc" | "desc" }) => {
      if (serviceListUsesServer) setRegistryPage(1);
      registrySort.onSortChange(next);
    },
    [registrySort, serviceListUsesServer, setRegistryPage],
  );

  const resetSortIfColumnHidden = useCallback(
    (visibleIds: readonly string[]) => {
      if (registrySort.mode !== "sorted") return;
      const sortKey = registrySort.sort.key;
      if (!sortKey) return;
      if (visibleIds.includes(sortKey)) return;
      handleRegistrySortChange({ key: "name", direction: "asc" });
    },
    [handleRegistrySortChange, registrySort.mode, registrySort.sort.key],
  );

  const applyVisibleColumns = useCallback(
    (next: readonly string[]) => {
      const resolved = persistVisibleServiceColumns({
        userId: preferenceUserId(),
        catalogue: serviceListCatalogue,
        columnIds: next,
      });
      setVisibleColumnIds(resolved);
      resetSortIfColumnHidden(resolved);
    },
    [preferenceUserId, resetSortIfColumnHidden, serviceListCatalogue],
  );

  const resetVisibleColumns = useCallback(() => {
    const resolved = resetVisibleServiceColumns({
      userId: preferenceUserId(),
      catalogue: serviceListCatalogue,
    });
    setVisibleColumnIds((current) => nextVisibleColumnIds(current, resolved));
    resetSortIfColumnHidden(resolved);
  }, [preferenceUserId, resetSortIfColumnHidden, serviceListCatalogue]);

  return {
    visibleColumnIds,
    visibleColumnsReady: loadedCatalogueKey === catalogueKey,
    applyVisibleColumns,
    resetVisibleColumns,
    handleRegistrySortChange,
  };
}
