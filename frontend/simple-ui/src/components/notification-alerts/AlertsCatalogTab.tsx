import React from "react";
import CatalogTab from "./CatalogTab";

const AlertsCatalogTab: React.FC = () => (
  <CatalogTab
    type="ALERT"
    entityLabel="alert"
    nameColumnHeader="Alert Name"
    emptyMessage="No alerts match your filters."
    showThresholds
    hint="Set the Recipient Role and Threshold values for any alert. Check the ones you want Enabled, uncheck the ones you want Disabled, then Submit. Enabling a row with no roles selected defaults to Tenant Admin."
  />
);

export default AlertsCatalogTab;
