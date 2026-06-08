// Update definition drawer

import DefinitionDrawerShell from "./form/DefinitionDrawerShell";
import DefinitionFormFields from "./form/DefinitionFormFields";
import type { DefinitionSectionProps } from "./types";

export default function UpdateDefinitionDrawer(tab: DefinitionSectionProps) {
  const { defs, expandedUpdateServices } = tab;

  return (
    <DefinitionDrawerShell
      title="Update Alert Definition"
      isOpen={defs.isUpdateOpen}
      onClose={defs.closeUpdate}
      isSaving={defs.isUpdating}
      saveLabel="Save Changes"
      onSave={defs.handleUpdate}
      saveDisabled={
        defs.updateForm.category !== "infrastructure" && expandedUpdateServices.length === 0
      }
    >
      <DefinitionFormFields
        mode="update"
        defs={defs}
        expandedUpdateServices={expandedUpdateServices}
      />
    </DefinitionDrawerShell>
  );
}
