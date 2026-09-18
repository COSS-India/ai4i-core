import React from "react";
import CatalogTab from "./CatalogTab";

const NotificationsCatalogTab: React.FC = () => (
  <CatalogTab
    type="NOTIFICATION"
    entityLabel="notification"
    nameColumnHeader="Notification Name"
    emptyMessage="No notifications match your filters."
    hint="Set the Recipient Role for any notification. Check the roles that should receive it, uncheck the ones that should not, then Submit. A notification with no roles selected is disabled."
  />
);

export default NotificationsCatalogTab;
