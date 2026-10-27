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

  const [visibleColumnIds, setVisibleColumnIds] = useState<string[]>(
    defaultServiceListColumnIds,
  );
  const catalogueKey = serviceListCatalogue.map((column) => column.id).join("|");

  const preferenceUserId = useCallback(
    () => userId || authService.getStoredUser()?.user_id || "",
    [userId],
  );

  useLayoutEffect(() => {
    const id = preferenceUserId();
    if (!id) return;
    let cancelled = false;
    void loadVisibleServiceColumns({
      userId: id,
      usesServer: serviceListUsesServer,
      catalogue: serviceListCatalogue,
    }).then((next) => {
      if (cancelled) return;
      setVisibleColumnIds((current) => nextVisibleColumnIds(current, next));
    });
    return () => {
      cancelled = true;
    };
  }, [preferenceUserId, serviceListUsesServer, catalogueKey, serviceListCatalogue]);

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
        usesServer: serviceListUsesServer,
        catalogue: serviceListCatalogue,
        columnIds: next,
      });
      setVisibleColumnIds(resolved);
      resetSortIfColumnHidden(resolved);
    },
    [
      preferenceUserId,
      resetSortIfColumnHidden,
      serviceListCatalogue,
      serviceListUsesServer,
    ],
  );

  const resetVisibleColumns = useCallback(() => {
    const defaults = resetVisibleServiceColumns({
      userId: preferenceUserId(),
      usesServer: serviceListUsesServer,
      catalogue: serviceListCatalogue,
    });
    setVisibleColumnIds(defaults);
    resetSortIfColumnHidden(defaults);
  }, [
    preferenceUserId,
    resetSortIfColumnHidden,
    serviceListCatalogue,
    serviceListUsesServer,
  ]);

  return {
    visibleColumnIds,
    applyVisibleColumns,
    resetVisibleColumns,
    handleRegistrySortChange,
  };
}
