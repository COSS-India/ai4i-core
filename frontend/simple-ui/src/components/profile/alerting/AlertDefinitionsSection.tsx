// Alert definitions — table and CRUD drawers

import type { UseAlertingTabReturn } from "../hooks/useAlertingTab";
import AlertDefinitionsTable from "./definitions/AlertDefinitionsTable";
import CreateDefinitionDrawer from "./definitions/CreateDefinitionDrawer";
import DeleteDefinitionDialog from "./definitions/DeleteDefinitionDialog";
import UpdateDefinitionDrawer from "./definitions/UpdateDefinitionDrawer";
import ViewDefinitionDrawer from "./definitions/ViewDefinitionDrawer";

type Props = UseAlertingTabReturn;

export default function AlertDefinitionsSection(tab: Props) {
  return (
    <>
      <AlertDefinitionsTable {...tab} />
      <CreateDefinitionDrawer {...tab} />
      <ViewDefinitionDrawer {...tab} />
      <UpdateDefinitionDrawer {...tab} />
      <DeleteDefinitionDialog {...tab} />
    </>
  );
}
