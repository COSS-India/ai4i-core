// Alert routing rules — table and CRUD drawers

import type { UseAlertingTabReturn } from "../hooks/useAlertingTab";
import AlertRoutingTable from "./routing/AlertRoutingTable";
import CreateRoutingRuleDrawer from "./routing/CreateRoutingRuleDrawer";
import DeleteRoutingRuleDialog from "./routing/DeleteRoutingRuleDialog";
import UpdateRoutingRuleDrawer from "./routing/UpdateRoutingRuleDrawer";
import ViewRoutingRuleDrawer from "./routing/ViewRoutingRuleDrawer";

type Props = UseAlertingTabReturn;

export default function AlertRoutingSection(tab: Props) {
  return (
    <>
      <AlertRoutingTable {...tab} />
      <CreateRoutingRuleDrawer {...tab} />
      <ViewRoutingRuleDrawer {...tab} />
      <UpdateRoutingRuleDrawer {...tab} />
      <DeleteRoutingRuleDialog {...tab} />
    </>
  );
}
