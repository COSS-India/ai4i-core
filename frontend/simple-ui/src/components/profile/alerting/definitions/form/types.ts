import type { useAlertDefinitions } from "../../../hooks/useAlertDefinitions";

export type AlertDefinitionsHook = ReturnType<typeof useAlertDefinitions>;
export type DefinitionFormMode = "create" | "update";

export interface DefinitionFormFieldsProps {
  mode: DefinitionFormMode;
  defs: AlertDefinitionsHook;
  expandedUpdateServices?: string[];
}
