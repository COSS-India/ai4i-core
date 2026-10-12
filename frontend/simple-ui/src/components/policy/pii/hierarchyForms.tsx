import {
  FormControl,
  FormErrorMessage,
  Input,
  Stack,
  Textarea,
} from "@chakra-ui/react";
import React, { useState } from "react";
import FieldLabel from "../../common/FieldLabel";
import FormActions from "../../common/FormActions";
import FormDrawer from "../../common/FormDrawer";

const NAME_MAX = 100;
const DESCRIPTION_MAX = 1000;

export function HierarchyNameForm({
  title,
  submitLabel,
  namePlaceholder,
  descriptionPlaceholder,
  onClose,
  onSave,
}: {
  title: string;
  submitLabel: string;
  namePlaceholder: string;
  descriptionPlaceholder: string;
  onClose: () => void;
  onSave: (name: string, description: string) => Promise<string | null>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (saving) return;
    if (!name.trim()) {
      setError("Enter a name.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const message = await onSave(name, description);
      if (message) setError(message);
      else onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormDrawer
      isOpen
      onClose={onClose}
      title={title}
      lockDismiss={saving}
      footer={
        <FormActions
          submitLabel={submitLabel}
          onCancel={onClose}
          onSubmit={() => {
            void submit();
          }}
          isLoading={saving}
          loadingText="Saving"
        />
      }
    >
      <Stack spacing={4}>
        <FormControl isInvalid={Boolean(error)}>
          <FieldLabel required>Name</FieldLabel>
          <Input
            value={name}
            maxLength={NAME_MAX}
            placeholder={namePlaceholder}
            onChange={(event) => {
              setName(event.target.value);
              if (error) setError("");
            }}
          />
          {error ? <FormErrorMessage>{error}</FormErrorMessage> : null}
        </FormControl>
        <FormControl>
          <FieldLabel>Description</FieldLabel>
          <Textarea
            rows={4}
            value={description}
            maxLength={DESCRIPTION_MAX}
            placeholder={descriptionPlaceholder}
            onChange={(event) => setDescription(event.target.value)}
          />
        </FormControl>
      </Stack>
    </FormDrawer>
  );
}
