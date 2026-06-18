import React from "react";
import SegmentedTabBar from "./SegmentedTabBar";

export type MeteringSubTab = "overview" | "tenant" | "service";

const SUB_TABS: { id: MeteringSubTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "tenant", label: "Tenant Consumption" },
  { id: "service", label: "Service Consumption" },
];

interface MeteringSubTabBarProps {
  activeTab: MeteringSubTab;
  onChange: (tab: MeteringSubTab) => void;
}

const MeteringSubTabBar: React.FC<MeteringSubTabBarProps> = ({ activeTab, onChange }) => (
  <SegmentedTabBar options={SUB_TABS} activeId={activeTab} onChange={onChange} />
);

export default MeteringSubTabBar;
