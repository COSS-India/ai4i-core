import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getModelColumnConfig } from "../../services/configManagementService";
import {
  modelListColumnsFromConfig,
  type ModelListColumnDef,
} from "./modelListColumns";

/** Model List columns from the `model-column` config; built-in catalogue if it is missing or fails. */
export function useModelListColumnCatalogue(): {
  catalogue: readonly ModelListColumnDef[];
  isLoading: boolean;
} {
  const query = useQuery({
    queryKey: ["configs", "model-column"],
    queryFn: getModelColumnConfig,
  });
  const catalogue = useMemo(
    () => modelListColumnsFromConfig(query.data),
    [query.data],
  );
  return { catalogue, isLoading: query.isPending };
}
