import { SearchIcon } from "@chakra-ui/icons";
import {
  Badge,
  Box,
  Button,
  Checkbox,
  Flex,
  FormControl,
  FormErrorMessage,
  HStack,
  Input,
  Select,
  Stack,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  Textarea,
  Wrap,
} from "@chakra-ui/react";
import React, { useMemo, useRef, useState } from "react";
import FieldLabel from "../../common/FieldLabel";
import FormActions from "../../common/FormActions";
import FormDrawer from "../../common/FormDrawer";
import FormSection from "../../common/FormSection";
import ReadOnlyField from "../../common/ReadOnlyField";
import { apiDomainName, entityNamesForPolicy, MIN_REGEX_EXAMPLES } from "./apiMap";
import { regexCompiles } from "./detection";
import {
  domainLabel,
  INSTITUTIONS,
  LANGUAGES,
  MODEL_FIELD_LANGUAGES,
  MODEL_SUPPORTED_ENTITIES,
  SCOPE_OPTIONS,
  type PolicyField,
  type PolicyScope,
  type PolicyType,
} from "./model";
import { usePiiPolicies, type PolicyInput, type TypeInput } from "./PiiPoliciesProvider";
import { ChoiceCard } from "./ui";

function FormField({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <FormControl isInvalid={Boolean(error)}>
      <FieldLabel required={required}>{label}</FieldLabel>
      {children}
      {error ? <FormErrorMessage>{error}</FormErrorMessage> : null}
    </FormControl>
  );
}

export function PiiDrawers() {
  return (
    <>
      <TypeDrawer />
      <TypeViewDrawer />
      <DomainDrawer />
      <PolicyDrawer />
      <PolicyViewDrawer />
    </>
  );
}

interface FieldRow extends PolicyField {
  key: string;
}

function TypeDrawer() {
  const { drawer, closeDrawer, types, addType, updateType } = usePiiPolicies();
  const open = drawer.kind === "add-type" || drawer.kind === "edit-type";
  const existing = drawer.kind === "edit-type" ? types.find((t) => t.id === drawer.id) : undefined;
  if (!open) return null;

  return (
    <TypeForm
      key={existing?.id ?? "new"}
      title={existing ? "Edit Policy Type" : "Create Policy Type"}
      submitLabel={existing ? "Save" : "Create Policy Type"}
      nameLocked={Boolean(existing)}
      initial={{
        name: existing?.name ?? "",
        fields:
          existing && existing.fields.length > 0
            ? existing.fields.map((field, index) => ({ ...field, key: `${existing.id}-${index}` }))
            : [blankField("field-1")],
      }}
      onClose={closeDrawer}
      onSave={(input) => (existing ? updateType(existing.id, input) : addType(input))}
    />
  );
}

function languageOptions(current: string): string[] {
  if (current && !MODEL_FIELD_LANGUAGES.includes(current as (typeof MODEL_FIELD_LANGUAGES)[number])) {
    return [current, ...MODEL_FIELD_LANGUAGES];
  }
  return [...MODEL_FIELD_LANGUAGES];
}

function modelEntityOptions(current: string): string[] {
  if (current && !MODEL_SUPPORTED_ENTITIES.includes(current as (typeof MODEL_SUPPORTED_ENTITIES)[number])) {
    return [current, ...MODEL_SUPPORTED_ENTITIES];
  }
  return [...MODEL_SUPPORTED_ENTITIES];
}

function blankField(key: string): FieldRow {
  return {
    key,
    mode: "custom",
    domain: "",
    entityName: "",
    examples: [],
    regex: "",
    language: "en",
  };
}

function TypeForm({
  title,
  submitLabel,
  nameLocked,
  initial,
  onClose,
  onSave,
}: {
  title: string;
  submitLabel: string;
  nameLocked: boolean;
  initial: { name: string; fields: FieldRow[] };
  onClose: () => void;
  onSave: (input: TypeInput) => Promise<string | null>;
}) {
  const [name, setName] = useState(initial.name);
  const [fields, setFields] = useState<FieldRow[]>(initial.fields);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const keyRef = useRef(initial.fields.length + 1);

  const updateField = (key: string, patch: Partial<FieldRow>) => {
    setFields((prev) => prev.map((field) => (field.key === key ? { ...field, ...patch } : field)));
  };

  const save = async () => {
    if (saving) return;
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Policy type name is required.";
    if (fields.length === 0) next.fields = "Add at least one policy field.";
    const seen = new Set<string>();
    fields.forEach((field) => {
      if (!field.entityName.trim()) next[`${field.key}-entity`] = "Entity name is required.";
      const language = field.language.trim().toLowerCase() || "en";
      const identity =
        field.mode === "model"
          ? `${field.domain.trim().toLowerCase()}:${field.entityName.trim().toLowerCase()}:${language}`
          : `${field.domain.trim().toLowerCase()}:${field.entityName.trim().toLowerCase()}`;
      if (field.entityName.trim()) {
        if (seen.has(identity)) next[`${field.key}-entity`] = "This entity is already listed.";
        seen.add(identity);
      }
      if (field.mode === "custom") {
        if (field.examples.length < MIN_REGEX_EXAMPLES) {
          next[`${field.key}-examples`] = `Add at least ${MIN_REGEX_EXAMPLES} examples.`;
        }
        if (!field.regex.trim()) next[`${field.key}-regex`] = "A regex pattern is required.";
        else if (!regexCompiles(field.regex.trim())) next[`${field.key}-regex`] = "Enter a valid regular expression.";
      }
    });
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    try {
      const error = await onSave({
        name: name.trim(),
        fields: fields.map(({ key: _key, ...field }) => ({
          ...field,
          domain: field.domain.trim(),
          entityName: field.entityName.trim(),
          regex: field.regex.trim(),
          examples: field.examples.map((example) => example.trim()).filter(Boolean),
        })),
      });
      if (error) setErrors({ name: error });
      else onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormDrawer
      isOpen
      onClose={onClose}
      size="wide"
      title={title}
      lockDismiss={saving}
      footer={
        <FormActions
          cancelLabel="Cancel"
          submitLabel={submitLabel}
          onCancel={onClose}
          onSubmit={() => {
            void save();
          }}
          isLoading={saving}
          loadingText="Saving"
        />
      }
    >
      <FormSection title="Identity">
        <FormField label="Policy Type Name" required error={errors.name}>
          <Input
            value={name}
            isDisabled={nameLocked}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. PII, Rate Limiting"
          />
        </FormField>
      </FormSection>
      <FormSection title="Policy Fields">
        {errors.fields ? (
          <Text fontSize="xs" color="red.500">
            {errors.fields}
          </Text>
        ) : null}
        <Stack spacing={4}>
          {fields.map((field, index) => (
            <Box key={field.key} borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
              <Flex justify="space-between" align="center" mb={3} gap={3}>
                <Text fontSize="sm" fontWeight="semibold">
                  Field {index + 1}
                </Text>
                <Button
                  size="xs"
                  variant="ghost"
                  colorScheme="red"
                  isDisabled={fields.length === 1}
                  onClick={() => setFields((prev) => prev.filter((row) => row.key !== field.key))}
                >
                  Remove
                </Button>
              </Flex>
              <Stack spacing={3}>
                <FormField label="Field mode" required>
                  <Select
                    value={field.mode}
                    onChange={(e) => {
                      const mode = e.target.value === "model" ? "model" : "custom";
                      const entityName =
                        mode === "model" &&
                        !MODEL_SUPPORTED_ENTITIES.includes(
                          field.entityName as (typeof MODEL_SUPPORTED_ENTITIES)[number],
                        )
                          ? ""
                          : field.entityName;
                      updateField(field.key, { mode, entityName });
                    }}
                  >
                    <option value="model">Model-supported</option>
                    <option value="custom">Custom</option>
                  </Select>
                </FormField>
                {field.mode === "model" ? (
                  <>
                    <FormField label="Entity name" required error={errors[`${field.key}-entity`]}>
                      <Select
                        value={field.entityName}
                        placeholder="Select an entity"
                        onChange={(e) => updateField(field.key, { entityName: e.target.value })}
                      >
                        {modelEntityOptions(field.entityName).map((entity) => (
                          <option key={entity} value={entity}>
                            {entity}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                    <FormField label="Language" required>
                      <Select
                        value={field.language || "en"}
                        onChange={(e) => updateField(field.key, { language: e.target.value })}
                      >
                        {languageOptions(field.language).map((language) => (
                          <option key={language} value={language}>
                            {language}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                  </>
                ) : (
                  <>
                    <FormField label="Entity name" required error={errors[`${field.key}-entity`]}>
                      <Input
                        value={field.entityName}
                        onChange={(e) => updateField(field.key, { entityName: e.target.value })}
                        placeholder="e.g. CUSTOM_ID"
                      />
                    </FormField>
                    <FormField
                      label="Examples"
                      required
                      error={errors[`${field.key}-examples`]}
                    >
                      <ExampleTags
                        values={field.examples}
                        onChange={(examples) => updateField(field.key, { examples })}
                      />
                      <Text fontSize="xs" color="ink.400" mt={1}>
                        At least {MIN_REGEX_EXAMPLES} examples. Press Enter to add one.
                      </Text>
                    </FormField>
                    <FormField label="Regex" required error={errors[`${field.key}-regex`]}>
                      <Input
                        fontFamily="mono"
                        value={field.regex}
                        onChange={(e) => updateField(field.key, { regex: e.target.value })}
                        placeholder="e.g. \d{4}-\d{4}"
                      />
                    </FormField>
                  </>
                )}
              </Stack>
            </Box>
          ))}
        </Stack>
        <Button
          size="sm"
          variant="outline"
          mt={3}
          onClick={() => {
            const key = `field-${keyRef.current++}`;
            setFields((prev) => [...prev, blankField(key)]);
          }}
        >
          Add field
        </Button>
      </FormSection>
    </FormDrawer>
  );
}

function ExampleTags({ values, onChange }: { values: string[]; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const next = draft.trim();
    if (!next || values.includes(next)) {
      setDraft("");
      return;
    }
    onChange([...values, next]);
    setDraft("");
  };
  return (
    <Box>
      <Input
        value={draft}
        placeholder="1234-5678"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
      />
      {values.length > 0 ? (
        <Wrap mt={2}>
          {values.map((value) => (
            <Tag key={value} size="sm" colorScheme="blue">
              <TagLabel>{value}</TagLabel>
              <TagCloseButton onClick={() => onChange(values.filter((item) => item !== value))} />
            </Tag>
          ))}
        </Wrap>
      ) : null}
    </Box>
  );
}

function TypeViewDrawer() {
  const { drawer, closeDrawer, types, openDrawer } = usePiiPolicies();
  if (drawer.kind !== "view-type") return null;
  const t = types.find((x) => x.id === drawer.id);
  if (!t) return null;

  return (
    <FormDrawer
      isOpen
      onClose={closeDrawer}
      size="wide"
      title="View Policy Type"
      footer={
        <FormActions
          cancelLabel="Close"
          onCancel={closeDrawer}
          extraLabel="Edit"
          onExtra={() => openDrawer({ kind: "edit-type", id: t.id })}
          hideSubmit
        />
      }
    >
      <Stack spacing={4}>
        <ReadOnlyField label="Policy Type Name">{t.name}</ReadOnlyField>
        <Stack spacing={3}>
          {t.fields.map((field) => (
            <Box
              key={`${field.domain}:${field.language}:${field.entityName}:${field.mode}`}
              borderWidth="1px"
              borderColor="ink.200"
              borderRadius="md"
              p={3}
            >
              <Flex justify="space-between" gap={3} mb={2}>
                <Text fontSize="sm" fontWeight="semibold">
                  {field.entityName}
                </Text>
                <Badge textTransform="none">{field.mode === "model" ? "Model-supported" : "Custom"}</Badge>
              </Flex>
              {field.mode === "model" ? (
                <Text fontSize="xs" color="ink.500" mb={2}>
                  {field.language || "en"}
                </Text>
              ) : null}
              {field.mode === "custom" ? (
                <Stack spacing={2}>
                  <Wrap>
                    {field.examples.map((example) => (
                      <Badge textTransform="none" key={example}>
                        {example}
                      </Badge>
                    ))}
                  </Wrap>
                  <Text fontFamily="mono" fontSize="xs" bg="ink.50" px={2} py={1} borderRadius="md">
                    {field.regex}
                  </Text>
                </Stack>
              ) : null}
            </Box>
          ))}
        </Stack>
      </Stack>
    </FormDrawer>
  );
}

function DomainDrawer() {
  const { drawer, closeDrawer, domains, addDomain, updateDomain } = usePiiPolicies();
  const open = drawer.kind === "add-domain" || drawer.kind === "edit-domain";
  const existing = drawer.kind === "edit-domain" ? domains.find((d) => d.id === drawer.id) : undefined;
  if (!open) return null;
  return (
    <DomainForm
      key={existing?.id ?? "new-domain"}
      title={existing ? "Edit Domain" : "Create Domain"}
      submitLabel={existing ? "Save" : "Create Domain"}
      nameLocked={Boolean(existing?.isDefault)}
      initialName={existing?.name ?? ""}
      initialDescription={existing?.description ?? ""}
      onClose={closeDrawer}
      onSave={(name, description) =>
        existing ? updateDomain(existing.id, name, description) : addDomain(name, description)
      }
    />
  );
}

function DomainForm({
  title,
  submitLabel,
  nameLocked,
  initialName,
  initialDescription,
  onClose,
  onSave,
}: {
  title: string;
  submitLabel: string;
  nameLocked: boolean;
  initialName: string;
  initialDescription: string;
  onClose: () => void;
  onSave: (name: string, description: string) => string | null;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [error, setError] = useState("");
  return (
    <FormDrawer
      isOpen
      onClose={onClose}
      title={title}
      footer={
        <FormActions
          submitLabel={submitLabel}
          onCancel={onClose}
          onSubmit={() => {
            if (!name.trim()) {
              setError("Domain name is required.");
              return;
            }
            const message = onSave(name.trim(), description.trim());
            if (message) setError(message);
            else onClose();
          }}
        />
      }
    >
      <Stack spacing={4}>
        <FormField label="Domain Name" required error={error}>
          <Input
            value={name}
            isDisabled={nameLocked}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Insurance"
          />
        </FormField>
        <FormField label="Domain Description">
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormField>
      </Stack>
    </FormDrawer>
  );
}

function PolicyDrawer() {
  const { drawer, closeDrawer, policies, addPolicy, updatePolicy } = usePiiPolicies();
  const open = drawer.kind === "create-policy" || drawer.kind === "edit-policy";
  const existing = drawer.kind === "edit-policy" ? policies.find((p) => p.id === drawer.id) : undefined;
  if (!open) return null;
  return (
    <PolicyForm
      key={existing?.id ?? "new-policy"}
      title={existing ? "Edit Policy" : "Create Policy"}
      submitLabel={existing ? "Save" : "Create Policy"}
      nameLocked={Boolean(existing)}
      initial={
        existing
          ? {
              name: existing.name,
              description: existing.description,
              domainIds: existing.domainIds,
              languages: existing.languages,
              typeIds: existing.typeIds,
              policyType: existing.policyType,
              scope: existing.scope,
            }
          : {
              name: "",
              description: "",
              domainIds: [],
              languages: ["English"],
              typeIds: [],
              policyType: "Global",
              scope: "" as PolicyScope | "",
            }
      }
      onClose={closeDrawer}
      onSave={(input) => (existing ? updatePolicy(existing.id, input) : addPolicy(input))}
    />
  );
}

function PolicyForm({
  title,
  submitLabel,
  nameLocked,
  initial,
  onClose,
  onSave,
}: {
  title: string;
  submitLabel: string;
  nameLocked: boolean;
  initial: {
    name: string;
    description: string;
    domainIds: string[];
    languages: string[];
    typeIds: string[];
    policyType: PolicyType;
    scope: PolicyScope | "";
  };
  onClose: () => void;
  onSave: (input: PolicyInput) => Promise<string | null>;
}) {
  const { domains, types, typesStatus, typesError } = usePiiPolicies();
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [domainIds, setDomainIds] = useState(initial.domainIds);
  const [languages, setLanguages] = useState(initial.languages);
  const [typeIds, setTypeIds] = useState(initial.typeIds);
  const [policyType, setPolicyType] = useState<PolicyType>(initial.policyType);
  const [scope, setScope] = useState<PolicyScope | "">(initial.scope);
  const [domainOpen, setDomainOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [typesOpen, setTypesOpen] = useState(true);
  const [typeQuery, setTypeQuery] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const domainChoices = useMemo(() => {
    const wanted = new Set(
      domainIds.map((id) => apiDomainName(domainLabel(id, domains)).toLowerCase()),
    );
    return types
      .map((type) => {
        const entities: string[] = [];
        type.fields.forEach((field) => {
          if (!field.entityName) return;
          const matchesDomain = !field.domain || wanted.has(field.domain.toLowerCase());
          if (!matchesDomain || entities.includes(field.entityName)) return;
          entities.push(field.entityName);
        });
        return { id: type.id, name: type.name, entities };
      })
      .filter((choice) => choice.entities.length > 0);
  }, [types, domainIds, domains]);

  const visibleChoices = useMemo(() => {
    const query = typeQuery.trim().toLowerCase();
    if (!query) return domainChoices;
    return domainChoices.filter(
      (choice) =>
        choice.name.toLowerCase().includes(query) ||
        choice.entities.some((name) => name.toLowerCase().includes(query)),
    );
  }, [domainChoices, typeQuery]);

  const selectedTypeIds = typeIds.filter((id) => domainChoices.some((choice) => choice.id === id));

  const toggle = (list: string[], value: string, setter: (next: string[]) => void) => {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  const save = async () => {
    if (saving) return;
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Policy name is required.";
    if (description.length > 200) next.description = "Description is limited to 200 characters.";
    if (domainIds.length === 0) next.domain = "Select at least one domain.";
    if (languages.length === 0) next.languages = "Select at least one language.";
    if (selectedTypeIds.length === 0) next.types = "Select at least one policy type.";
    if (!scope) next.scope = "Select a scope.";
    setErrors(next);
    if (Object.keys(next).length || !scope) return;
    setSaving(true);
    try {
      const error = await onSave({
        name: name.trim(),
        description: description.trim(),
        domainIds,
        languages,
        typeIds: selectedTypeIds,
        policyType,
        scope,
      });
      if (error) setErrors({ name: error });
      else onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormDrawer
      isOpen
      onClose={onClose}
      size="wide"
      title={title}
      lockDismiss={saving}
      footer={
        <FormActions
          submitLabel={submitLabel}
          onCancel={onClose}
          onSubmit={() => {
            void save();
          }}
          isLoading={saving}
          loadingText="Saving"
        />
      }
    >
      <Stack spacing={4}>
        <FormField label="Policy Name" required error={errors.name}>
          <Input
            value={name}
            isDisabled={nameLocked}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Retail Banking Safeguard"
          />
        </FormField>
        <FormField label="Description" error={errors.description}>
          <Textarea
            value={description}
            maxLength={200}
            rows={2}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Text fontSize="xs" color="ink.400" textAlign="right" mt={1}>
            {description.length}/200
          </Text>
        </FormField>
        <ChipPicker
          label="Domain"
          required
          error={errors.domain}
          open={domainOpen}
          onToggle={() => {
            setDomainOpen((v) => !v);
            setLangOpen(false);
          }}
          emptyLabel="Select domains…"
          selectedLabels={domainIds.map((id) => domains.find((d) => d.id === id)?.name ?? "").filter(Boolean)}
          onRemove={(label) => {
            const match = domains.find((d) => d.name === label);
            if (match) setDomainIds(domainIds.filter((id) => id !== match.id));
          }}
          options={domains.map((d) => ({ value: d.id, label: d.name, checked: domainIds.includes(d.id) }))}
          onCheck={(value, checked) =>
            setDomainIds(checked ? [...domainIds, value] : domainIds.filter((id) => id !== value))
          }
        />
        <Box>
          <FieldLabel required>Policy Type</FieldLabel>
          <Stack spacing={2}>
            <ChoiceCard
              name="policy-type"
              title="Global"
              description="Applied automatically to every institution. Institutions cannot unsubscribe."
              checked={policyType === "Global"}
              onSelect={() => setPolicyType("Global")}
            />
            <ChoiceCard
              name="policy-type"
              title="Institution level"
              description="Institutions choose whether to subscribe to this policy."
              checked={policyType === "Institution level"}
              onSelect={() => setPolicyType("Institution level")}
            />
          </Stack>
        </Box>
        <ChipPicker
          label="Supported Languages"
          required
          error={errors.languages}
          open={langOpen}
          onToggle={() => {
            setLangOpen((v) => !v);
            setDomainOpen(false);
          }}
          emptyLabel="Select languages…"
          selectedLabels={languages}
          onRemove={(label) => setLanguages(languages.filter((l) => l !== label))}
          options={LANGUAGES.map((l) => ({ value: l, label: l, checked: languages.includes(l) }))}
          onCheck={(value) => toggle(languages, value, setLanguages)}
        />
        <Box borderTopWidth="1px" borderColor="ink.200" />
        <FormField
          label={`Policy Types (${selectedTypeIds.length}/${domainChoices.length})`}
          required
          error={errors.types}
        >
          {domainIds.length === 0 ? (
            <Text fontSize="sm" color="ink.500">
              Select a domain to see its policy types.
            </Text>
          ) : null}
          {typesStatus === "loading" ? (
            <Text fontSize="sm" color="ink.500" mb={2}>
              Loading policy types…
            </Text>
          ) : null}
          {typesStatus === "error" ? (
            <Text fontSize="sm" color="red.500" mb={2}>
              {typesError}
            </Text>
          ) : null}
          {domainIds.length > 0 && typesStatus !== "loading" && domainChoices.length === 0 ? (
            <Text fontSize="sm" color="ink.500">
              No policy types for the selected domain.
            </Text>
          ) : null}
          {domainChoices.length > 0 ? (
            <>
              <Flex justify="space-between" mb={2}>
                <Button size="sm" variant="ghost" onClick={() => setTypesOpen((v) => !v)}>
                  {typesOpen ? "Hide" : "Show"} types
                </Button>
                <HStack spacing={2}>
                  <Button
                    size="xs"
                    variant="link"
                    onClick={() => setTypeIds(domainChoices.map((choice) => choice.id))}
                  >
                    Select All
                  </Button>
                  <Button size="xs" variant="link" color="ink.500" onClick={() => setTypeIds([])}>
                    Clear
                  </Button>
                </HStack>
              </Flex>
              {typesOpen ? (
                <Box>
                  <Box position="relative" mb={2}>
                    <SearchIcon position="absolute" left={2.5} top="50%" transform="translateY(-50%)" color="ink.400" boxSize={3} />
                    <Input
                      size="sm"
                      pl={8}
                      placeholder="Search policy types..."
                      value={typeQuery}
                      onChange={(e) => setTypeQuery(e.target.value)}
                    />
                  </Box>
                  <Box maxH="240px" overflowY="auto" borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
                    <Stack spacing={3}>
                      {visibleChoices.map((choice) => (
                        <Box key={choice.id}>
                          <Checkbox
                            size="sm"
                            isChecked={selectedTypeIds.includes(choice.id)}
                            onChange={() => toggle(typeIds, choice.id, setTypeIds)}
                          >
                            {choice.name}
                          </Checkbox>
                          <Text pl={6} mt={1} fontSize="xs" color="ink.500">
                            {choice.entities.join(", ")}
                          </Text>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                </Box>
              ) : null}
            </>
          ) : null}
        </FormField>
        <Box>
          <FieldLabel required>Scope</FieldLabel>
          <Stack spacing={2}>
            {SCOPE_OPTIONS.map((option) => (
              <ChoiceCard
                key={option}
                name="policy-scope"
                title={option}
                description={
                  option === "Input requests"
                    ? "Runs on the request before it reaches the model."
                    : option === "Output requests"
                      ? "Runs on the model response."
                      : "Runs on the request and on the model response."
                }
                checked={scope === option}
                onSelect={() => setScope(option)}
              />
            ))}
          </Stack>
          {errors.scope ? (
            <Text fontSize="xs" color="red.500" mt={1}>
              {errors.scope}
            </Text>
          ) : null}
        </Box>
      </Stack>
    </FormDrawer>
  );
}

function ChipPicker({
  label,
  required,
  error,
  open,
  onToggle,
  emptyLabel,
  selectedLabels,
  onRemove,
  options,
  onCheck,
}: {
  label: string;
  required?: boolean;
  error?: string;
  open: boolean;
  onToggle: () => void;
  emptyLabel: string;
  selectedLabels: string[];
  onRemove: (label: string) => void;
  options: { value: string; label: string; checked: boolean }[];
  onCheck: (value: string, checked: boolean) => void;
}) {
  return (
    <FormField label={label} required={required} error={error}>
      <Wrap mb={selectedLabels.length ? 2 : 0}>
        {selectedLabels.map((item) => (
          <Badge key={item} colorScheme="blue" borderRadius="full" px={2} py={1} textTransform="none">
            <HStack spacing={1}>
              <Text>{item}</Text>
              <Button size="xs" variant="ghost" minW={4} h={4} p={0} aria-label={`Remove ${item}`} onClick={() => onRemove(item)}>
                ×
              </Button>
            </HStack>
          </Badge>
        ))}
      </Wrap>
      <Button variant="outline" w="full" justifyContent="flex-start" fontWeight="normal" color="ink.500" onClick={onToggle}>
        {selectedLabels.length === 0 ? emptyLabel : `${selectedLabels.length} selected — click to change`}
      </Button>
      {open ? (
        <Box mt={1} borderWidth="1px" borderColor="ink.200" borderRadius="md" p={2} maxH="160px" overflowY="auto">
          {options.map((o) => (
            <Checkbox
              key={o.value}
              display="flex"
              py={1.5}
              px={2}
              isChecked={o.checked}
              onChange={(e) => onCheck(o.value, e.target.checked)}
            >
              {o.label}
            </Checkbox>
          ))}
        </Box>
      ) : null}
    </FormField>
  );
}

function PolicyViewDrawer() {
  const { drawer, closeDrawer, policies, types, domains, subscriptions } = usePiiPolicies();
  if (drawer.kind !== "view-policy") return null;
  const p = policies.find((x) => x.id === drawer.id);
  if (!p) return null;
  const subscribers = subscriptions[p.policyId] ?? [];
  const entityNames = entityNamesForPolicy(p, types, domains);
  return (
    <FormDrawer
      isOpen
      onClose={closeDrawer}
      size="wide"
      title={p.name}
      description={p.policyId}
      footer={<FormActions cancelLabel="Close" onCancel={closeDrawer} hideSubmit />}
    >
      <Stack spacing={4}>
        <Detail label="Policy Name" value={p.name} />
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
            Policy Type
          </Text>
          <Badge textTransform="none" colorScheme={p.policyType === "Global" ? "blue" : "gray"}>{p.policyType}</Badge>
        </Box>
        <Detail label="Scope" value={p.scope} />
        <Detail
          label="Domain"
          value={p.domainIds.map((id) => domainLabel(id, domains)).filter(Boolean).join(", ") || "—"}
        />
        {p.policyType === "Global" ? (
          <Detail label="Institutions" value="Applied to all institutions automatically. Institutions cannot unsubscribe." />
        ) : (
          <Box>
            <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
              Subscribed Institutions ({subscribers.length})
            </Text>
            <Wrap>
              {subscribers.length === 0 ? (
                <Text fontSize="sm" color="ink.500">
                  No subscriptions yet
                </Text>
              ) : (
                subscribers.map((id) => {
                  const inst = INSTITUTIONS.find((i) => i.id === id);
                  return inst ? <Badge textTransform="none" key={id}>{inst.name}</Badge> : null;
                })
              )}
            </Wrap>
          </Box>
        )}
        {p.description ? <Detail label="Description" value={p.description} /> : null}
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
            Status
          </Text>
          <Badge textTransform="none" colorScheme={p.status === "Active" ? "green" : "gray"}>{p.status}</Badge>
        </Box>
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
            Languages supported
          </Text>
          <Wrap>
            {p.languages.map((l) => (
              <Badge textTransform="none" key={l}>{l}</Badge>
            ))}
          </Wrap>
        </Box>
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
            Entity Names
          </Text>
          {entityNames.length === 0 ? (
            <Text fontSize="sm" color="ink.500">
              —
            </Text>
          ) : (
            <Wrap>
              {entityNames.map((name) => (
                <Badge textTransform="none" key={name}>
                  {name}
                </Badge>
              ))}
            </Wrap>
          )}
        </Box>
      </Stack>
    </FormDrawer>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <ReadOnlyField label={label}>{value}</ReadOnlyField>;
}
