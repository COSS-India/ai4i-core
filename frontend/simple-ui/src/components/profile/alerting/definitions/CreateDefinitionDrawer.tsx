// Create definition drawer

import DefinitionDrawerShell from "./form/DefinitionDrawerShell";
import DefinitionFormFields from "./form/DefinitionFormFields";
import type { DefinitionSectionProps } from "./types";

export default function CreateDefinitionDrawer(tab: DefinitionSectionProps) {
  const { defs } = tab;

  return (
    <DefinitionDrawerShell
      title="Create Alert Definition"
      isOpen={defs.isCreateOpen}
      onClose={defs.closeCreate}
      isSaving={defs.isCreating}
      saveLabel="Save Alert Definition"
      onSave={defs.handleCreate}
    >
      <DefinitionFormFields mode="create" defs={defs} />
    </DefinitionDrawerShell>
  );
}
