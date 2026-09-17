import React from "react";
import CatalogTab from "./CatalogTab";

const AlertsCatalogTab: React.FC = () => (
  <CatalogTab
    type="ALERT"
    entityLabel="alert"
    nameColumnHeader="Alert Name"
    emptyMessage="No alerts match your filters."
    showThresholds
    hint="Set the Recipient Role and Threshold values for any alert. Check the roles that should receive it, uncheck the ones that should not, then Submit. An alert with no roles selected is disabled."
  />
);

export default AlertsCatalogTab;
