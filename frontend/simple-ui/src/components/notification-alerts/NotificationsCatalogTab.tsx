import React from "react";
import CatalogTab from "./CatalogTab";

const NotificationsCatalogTab: React.FC = () => (
  <CatalogTab
    type="NOTIFICATION"
    entityLabel="notification"
    nameColumnHeader="Notification Name"
    emptyMessage="No notifications match your filters."
    hint="Set the Recipient Role for any notification. Check the ones you want Enabled, uncheck the ones you want Disabled, then Submit. Enabling a row with no roles selected defaults to Tenant Admin."
  />
);

export default NotificationsCatalogTab;
