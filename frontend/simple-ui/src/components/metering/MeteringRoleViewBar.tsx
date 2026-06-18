import React from "react";
import type { MeteringRoleView } from "../../utils/rbac";
import SegmentedTabBar from "./SegmentedTabBar";

interface MeteringRoleViewBarProps {
  activeView: MeteringRoleView;
  availableViews: MeteringRoleView[];
  canSwitchViews: boolean;
  onViewChange: (view: MeteringRoleView) => void;
}

const VIEW_LABELS: Record<MeteringRoleView, string> = {
  adopter: "Adopter Admin",
  tenant: "Tenant Admin",
};

const MeteringRoleViewBar: React.FC<MeteringRoleViewBarProps> = ({
  activeView,
  availableViews,
  canSwitchViews,
  onViewChange,
}) => {
  if (!canSwitchViews) {
    return null;
  }

  return (
    <SegmentedTabBar
      options={availableViews.map((view) => ({ id: view, label: VIEW_LABELS[view] }))}
      activeId={activeView}
      onChange={onViewChange}
      justify="flex-end"
      mb={4}
    />
  );
};

export default MeteringRoleViewBar;
