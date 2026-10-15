import { ChevronDownIcon, ChevronUpIcon, SearchIcon } from "@chakra-ui/icons";
import {
  Badge,
  Box,
  Button,
  Checkbox,
  Flex,
  FormControl,
  FormErrorMessage,
  FormHelperText,
  HStack,
  Input,
  Popover,
  PopoverBody,
  PopoverContent,
  PopoverTrigger,
  Portal,
  Radio,
  RadioGroup,
  Select,
  SimpleGrid,
  Stack,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  Textarea,
  useDisclosure,
  Wrap,
} from "@chakra-ui/react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import FieldLabel from "../../common/FieldLabel";
import FormActions from "../../common/FormActions";
import FormDrawer from "../../common/FormDrawer";
import FormSection from "../../common/FormSection";
import ReadOnlyField from "../../common/ReadOnlyField";
import { apiDomainName, entityNamesForPolicy, MIN_REGEX_EXAMPLES } from "./apiMap";
import { regexCompiles } from "./detection";
import {
  choiceKeys as keysOfChoices,
  customDraftErrors,
  draftFromField,
  entityAdditionKey,
  fieldDefined,
  fieldLabel,
  otherDetectableEntities,
  ownPolicyFields,
  policyFieldChoices,
  unavailableReason,
  type CustomFieldDraft,
  type DetectableEntities,
  type EntityAddition,
  type TypeChoice,
} from "./fieldSelection";
import { loadModelEntities } from "./modelEntities";
import { isPolicyOwnedType, policyOwnedType, sharedTypes } from "./policyCustomFields";
import {
  DEFAULT_POLICY_LANGUAGES,
  domainLabel,
  editableLanguages,
  isFieldShown,
  languageLabel,
  MODEL_FIELD_LANGUAGES,
  parseSelectedFieldKey,
  POLICY_LANGUAGES,
  SCOPE_OPTIONS,
  selectedFieldKey,
  SHOW_MODEL_SUPPORTED_FIELDS,
  subcategoriesForCategory,
  subcategoryAfterCategoryChange,
  subcategoryEffective,
  type PolicyField,
  type PolicyScope,
  type SelectedPolicyField,
} from "./model";
import { usePiiPolicies, type PolicyInput, type TypeInput } from "./PiiPoliciesProvider";

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
  const shownFields = existing?.fields.filter(isFieldShown) ?? [];
  const hiddenFields = existing?.fields.filter((field) => !isFieldShown(field)) ?? [];

  return (
    <TypeForm
      key={existing?.id ?? "new"}
      title={existing ? "Edit Policy Type" : "Create Policy Type"}
      submitLabel={existing ? "Save" : "Create Policy Type"}
      nameLocked={Boolean(existing)}
      initial={{
        name: existing?.name ?? "",
        fields:
          existing && shownFields.length > 0
            ? shownFields.map((field, index) => ({ ...field, key: `${existing.id}-${index}` }))
            : [blankField("field-1")],
      }}
      onClose={closeDrawer}
      onSave={(input) =>
        existing
          ? updateType(existing.id, { ...input, fields: [...input.fields, ...hiddenFields] })
          : addType(input)
      }
    />
  );
}

function languageOptions(current: string): string[] {
  if (current && !MODEL_FIELD_LANGUAGES.includes(current as (typeof MODEL_FIELD_LANGUAGES)[number])) {
    return [current, ...MODEL_FIELD_LANGUAGES];
  }
  return [...MODEL_FIELD_LANGUAGES];
}

interface EntityList {
  status: "loading" | "ready" | "error";
  entities: string[];
}

/** Detectable entities per language code, from inference-service. */
function useModelEntities(languages: string[]): {
  lists: Record<string, EntityList>;
  retry: () => void;
} {
  const [lists, setLists] = useState<Record<string, EntityList>>({});
  const [attempt, setAttempt] = useState(0);
  const languageKey = Array.from(new Set(languages)).sort().join(",");

  useEffect(() => {
    // Responses for a language set the user has since changed are dropped.
    let current = true;
    languageKey
      .split(",")
      .filter(Boolean)
      .forEach((language) => {
        setLists((prev) =>
          prev[language]?.status === "ready"
            ? prev
            : { ...prev, [language]: { status: "loading", entities: [] } },
        );
        loadModelEntities(language).then(
          (entities) => {
            if (current) setLists((prev) => ({ ...prev, [language]: { status: "ready", entities } }));
          },
          () => {
            if (current) setLists((prev) => ({ ...prev, [language]: { status: "error", entities: [] } }));
          },
        );
      });
    return () => {
      current = false;
    };
  }, [languageKey, attempt]);

  return { lists, retry: () => setAttempt((value) => value + 1) };
}

function modelEntityOptions(current: string, list: EntityList | undefined): string[] {
  const entities = list?.entities ?? [];
  return current && !entities.includes(current) ? [current, ...entities] : entities;
}

function modelEntityPlaceholder(list: EntityList | undefined): string {
  if (list?.status === "ready") return "Select an entity";
  if (list?.status === "error") return "Entities unavailable";
  return "Loading entities…";
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
  const { lists: entityLists } = useModelEntities(
    fields.filter((field) => field.mode === "model").map((field) => field.language || "en"),
  );

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
      const entityName = field.entityName.trim();
      const identity =
        field.mode === "model"
          ? `model:${entityName.toLowerCase()}:${language}`
          : `custom:${entityName.toLowerCase()}`;
      if (entityName) {
        if (seen.has(identity)) next[`${field.key}-entity`] = "This entity is already listed.";
        seen.add(identity);
      }
      if (field.mode === "model" && entityName && !next[`${field.key}-entity`]) {
        const list = entityLists[language];
        if (list?.status === "ready" && !list.entities.includes(entityName)) {
          next[`${field.key}-entity`] = `${entityName} cannot be detected in ${language}.`;
        }
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
          domain: "",
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
                {SHOW_MODEL_SUPPORTED_FIELDS ? (
                  <FormField label="Field mode" required>
                    <Select
                      value={field.mode}
                      onChange={(e) => {
                        const mode = e.target.value === "model" ? "model" : "custom";
                        const detectable = entityLists[field.language || "en"]?.entities ?? [];
                        const entityName =
                          mode === "model" && !detectable.includes(field.entityName) ? "" : field.entityName;
                        updateField(field.key, { mode, entityName });
                      }}
                    >
                      <option value="model">Model-supported</option>
                      <option value="custom">Custom</option>
                    </Select>
                  </FormField>
                ) : null}
                {field.mode === "model" ? (
                  <>
                    <FormField label="Entity name" required error={errors[`${field.key}-entity`]}>
                      <Select
                        value={field.entityName}
                        placeholder={modelEntityPlaceholder(entityLists[field.language || "en"])}
                        onChange={(e) => updateField(field.key, { entityName: e.target.value })}
                      >
                        {modelEntityOptions(field.entityName, entityLists[field.language || "en"]).map(
                          (entity) => (
                            <option key={entity} value={entity}>
                              {entity}
                            </option>
                          ),
                        )}
                      </Select>
                      {entityLists[field.language || "en"]?.status === "error" ? (
                        <Text fontSize="xs" color="red.500" mt={1}>
                          Could not load the entities for {field.language || "en"}. Change the language
                          or reopen the form to retry.
                        </Text>
                      ) : null}
                    </FormField>
                    <FormField label="Language" required>
                      <Select
                        value={field.language || "en"}
                        onChange={(e) => {
                          const language = e.target.value;
                          const list = entityLists[language];
                          const entityName =
                            list?.status === "ready" && !list.entities.includes(field.entityName)
                              ? ""
                              : field.entityName;
                          updateField(field.key, { language, entityName });
                        }}
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
  const entity = drawer.entity;
  const fields = entity
    ? t.fields.filter((field) => field.entityName === entity.name && field.mode === entity.mode)
    : t.fields.filter(isFieldShown);

  return (
    <FormDrawer
      isOpen
      onClose={closeDrawer}
      size="wide"
      title={entity ? "View PII Type" : "View Policy Type"}
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
        <ReadOnlyField label={entity ? "Group" : "Policy Type Name"}>{t.name}</ReadOnlyField>
        <Stack spacing={3}>
          {fields.map((field) => (
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
  const { drawer, closeDrawer, addDomain } = usePiiPolicies();
  if (drawer.kind !== "add-domain") return null;
  return <DomainForm onClose={closeDrawer} onSave={addDomain} />;
}

function DomainForm({
  onClose,
  onSave,
}: {
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
      setError("Domain name is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const message = await onSave(name.trim(), description.trim());
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
      title="Create Domain"
      lockDismiss={saving}
      footer={
        <FormActions
          submitLabel="Create Domain"
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
        <FormField label="Domain Name" required error={error}>
          <Input
            value={name}
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
  const {
    drawer,
    closeDrawer,
    policies,
    types,
    typesStatus,
    subcategories,
    policyCategoryFilter,
    policySubcategoryFilter,
    addPolicy,
    updatePolicy,
  } = usePiiPolicies();
  const open = drawer.kind === "create-policy" || drawer.kind === "edit-policy";
  const existing = drawer.kind === "edit-policy" ? policies.find((p) => p.id === drawer.id) : undefined;
  if (!open) return null;
  const existingSub = existing ? subcategories.find((s) => s.id === existing.subcategoryId) : undefined;
  const existingLanguages = existing ? editableLanguages(existing) : null;
  const filteredSub = subcategories.find((s) => s.id === policySubcategoryFilter);
  const owned = existing ? policyOwnedType(existing, types) : undefined;
  return (
    <PolicyForm
      // Remount once the types load, so the policy's own fields are filled in.
      key={existing ? `${existing.id}:${typesStatus === "ready"}` : "new-policy"}
      title={existing ? "Edit Policy" : "Create Policy"}
      submitLabel={existing ? "Save" : "Create Policy"}
      nameLocked={Boolean(existing)}
      initial={
        existing && existingLanguages
          ? {
              name: existing.name,
              description: existing.description,
              categoryId: existingSub?.categoryId ?? "",
              subCategoryId: existingSub ? existing.subcategoryId : "",
              domainIds: existing.domainIds,
              languages: existingLanguages.languages,
              languagesPrefilled: existingLanguages.prefilled,
              typeIds: existing.typeIds.filter((id) => id !== owned?.id),
              selectedFields: existing.selectedFields?.filter((field) => field.typeId !== owned?.id) ?? null,
              ownFields: owned?.fields ?? [],
              scope: existing.scope,
            }
          : {
              name: "",
              description: "",
              categoryId: filteredSub?.categoryId ?? policyCategoryFilter,
              subCategoryId: filteredSub?.id ?? "",
              domainIds: [],
              languages: [...DEFAULT_POLICY_LANGUAGES],
              typeIds: [],
              selectedFields: [],
              ownFields: [],
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
    categoryId: string;
    subCategoryId: string;
    domainIds: string[];
    languages: string[];
    /** The policy had no saved languages, so `languages` holds the defaults. */
    languagesPrefilled?: boolean;
    /** Shared PII types only; the policy's own fields are in ownFields. */
    typeIds: string[];
    selectedFields: SelectedPolicyField[] | null;
    ownFields: PolicyField[];
    scope: PolicyScope | "";
  };
  onClose: () => void;
  onSave: (input: PolicyInput) => Promise<string | null>;
}) {
  const { domains, types: allTypes, typesStatus, typesError, categories, subcategories } = usePiiPolicies();
  const types = useMemo(() => sharedTypes(allTypes), [allTypes]);
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [categoryId, setCategoryId] = useState(initial.categoryId);
  const [subCategoryId, setSubCategoryId] = useState(initial.subCategoryId);
  const subcategoryChoices = useMemo(
    () => (categoryId ? subcategoriesForCategory(subcategories, categoryId) : []),
    [subcategories, categoryId],
  );
  const [domainIds, setDomainIds] = useState(initial.domainIds);
  const [languages, setLanguages] = useState(initial.languages);
  // null on a policy saved without picks, where every linked field applies, until the admin changes a pick.
  const [picks, setPicks] = useState<string[] | null>(
    initial.selectedFields ? initial.selectedFields.map(selectedFieldKey) : null,
  );
  const [scope, setScope] = useState<PolicyScope | "">(initial.scope);
  const [typesOpen, setTypesOpen] = useState(true);
  const [typeQuery, setTypeQuery] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<CustomFieldDraft[]>(() =>
    initial.ownFields
      .filter((field) => field.mode === "custom")
      .map((field, index) => draftFromField(`custom-${index + 1}`, field)),
  );
  const draftKeyRef = useRef(drafts.length + 1);
  const [entityPicks, setEntityPicks] = useState<string[]>(() =>
    initial.ownFields
      .filter((field) => field.mode === "model")
      .map((field) => entityAdditionKey({ language: field.language || "en", entityName: field.entityName })),
  );
  const { lists: entityLists, retry: retryEntities } = useModelEntities(languages);
  const detectable = useMemo<DetectableEntities>(
    () =>
      Object.fromEntries(
        Object.entries(entityLists)
          .filter(([, list]) => list.status === "ready")
          .map(([language, list]) => [language, list.entities]),
      ),
    [entityLists],
  );
  const entitiesReady = languages.every((language) => entityLists[language]?.status === "ready");

  const typeChoices = useMemo<TypeChoice[]>(
    () =>
      policyFieldChoices(
        types,
        new Set(domainIds.map((id) => apiDomainName(domainLabel(id, domains)).toLowerCase())),
        languages,
        detectable,
      ),
    [types, domainIds, domains, languages, detectable],
  );

  const visibleChoices = useMemo(() => {
    const query = typeQuery.trim().toLowerCase();
    if (!query) return typeChoices;
    const matches = (field: SelectedPolicyField) => field.entityName.toLowerCase().includes(query);
    return typeChoices
      .map((choice) =>
        choice.name.toLowerCase().includes(query)
          ? choice
          : {
              ...choice,
              custom: choice.custom.filter(matches),
              model: choice.model
                .map(([language, fields]): [string, SelectedPolicyField[]] => [language, fields.filter(matches)])
                .filter(([, fields]) => fields.length > 0),
            },
      )
      .filter((choice) => choice.custom.length > 0 || choice.model.length > 0);
  }, [typeChoices, typeQuery]);

  const otherEntities = useMemo(
    () => (typesStatus === "ready" ? otherDetectableEntities(typeChoices, languages, detectable) : []),
    [typesStatus, typeChoices, languages, detectable],
  );
  const visibleOtherEntities = useMemo(() => {
    const query = typeQuery.trim().toLowerCase();
    if (!query) return otherEntities;
    return otherEntities
      .map(([language, entities]): [string, string[]] => [
        language,
        entities.filter((entity) => entity.toLowerCase().includes(query)),
      ])
      .filter(([, entities]) => entities.length > 0);
  }, [otherEntities, typeQuery]);
  // Picks for a language that was removed, or an entity a type now covers, no longer apply.
  const entityAdditions = useMemo<EntityAddition[]>(
    () =>
      otherEntities
        .flatMap(([language, entities]) => entities.map((entityName) => ({ language, entityName })))
        .filter((addition) => entityPicks.includes(entityAdditionKey(addition))),
    [otherEntities, entityPicks],
  );
  // Used by Select All, Clear and the count while the Model supported fields section is shown.
  // const entityKeys = useMemo(
  //   () =>
  //     otherEntities.flatMap(([language, entities]) =>
  //       entities.map((entityName) => entityAdditionKey({ language, entityName })),
  //     ),
  //   [otherEntities],
  // );

  const choiceKeys = useMemo(() => keysOfChoices(typeChoices), [typeChoices]);
  const linkedKeys = useMemo(
    () =>
      choiceKeys.filter((key) => initial.typeIds.includes(parseSelectedFieldKey(key).typeId)),
    [choiceKeys, initial.typeIds],
  );
  // Until the types and every language's detectable entities have loaded, picks are kept as they are.
  const choicesReady = typesStatus === "ready" && entitiesReady;
  const currentPicks = picks ?? linkedKeys;
  const selectedPicks = choicesReady ? currentPicks.filter((key) => choiceKeys.includes(key)) : currentPicks;
  // Saved or kept picks the form cannot offer; they block saving until removed.
  const unavailablePicks = choicesReady && picks ? picks.filter((key) => !choiceKeys.includes(key)) : [];
  const savedSelections = picks === null ? null : selectedPicks.map(parseSelectedFieldKey);
  const savedTypeIds = savedSelections
    ? Array.from(new Set(savedSelections.map((field) => field.typeId)))
    : initial.typeIds;

  const togglePick = (key: string) => {
    setPicks((prev) => {
      const base = prev ?? linkedKeys;
      return base.includes(key) ? base.filter((item) => item !== key) : [...base, key];
    });
  };
  const removePicks = (keys: string[]) => {
    setPicks((prev) => (prev ?? linkedKeys).filter((key) => !keys.includes(key)));
  };

  const toggle = (list: string[], value: string, setter: (next: string[]) => void) => {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  const save = async () => {
    if (saving) return;
    const next: Record<string, string> = {};
    if (!categoryId) next.category = "Select a category.";
    if (!subCategoryId) next.subcategory = "Select a sub-category.";
    if (!name.trim()) next.name = "Policy name is required.";
    if (description.length > 200) next.description = "Description is limited to 200 characters.";
    if (domainIds.length === 0) next.domain = "Select at least one domain.";
    if (languages.length === 0) next.languages = "Select at least one language.";
    if (languages.length > 0 && !entitiesReady) {
      next.types = "Wait for the model supported fields of each language to load, or retry.";
    } else if (unavailablePicks.length > 0) {
      next.types = "Remove the selections marked as unavailable, or add back their language or domain.";
    } else if (savedTypeIds.length === 0 && drafts.length === 0 && entityAdditions.length === 0) {
      next.types = "Select at least one policy field.";
    }
    const draftErrors = customDraftErrors(drafts);
    Object.assign(next, draftErrors);
    if (!scope) next.scope = "Select a scope.";
    setErrors(next);
    if (next.types || Object.keys(draftErrors).length > 0) setTypesOpen(true);
    if (Object.keys(next).length || !scope) return;
    setSaving(true);
    try {
      const error = await onSave({
        name: name.trim(),
        description: description.trim(),
        subCategoryId,
        domainIds,
        languages,
        typeIds: savedTypeIds,
        selectedFields: savedSelections,
        ownFields: ownPolicyFields(drafts, entityAdditions),
        scope,
      });
      if (!error) onClose();
      else if (error.startsWith("Couldn't save the policy's custom fields")) setErrors({ custom: error });
      else if (error.includes("selected_policy_fields")) setErrors({ types: error });
      else if (/\blanguages\b/.test(error)) setErrors({ languages: error });
      else setErrors({ name: error });
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
        <SimpleGrid columns={{ base: 1, md: 2 }} spacingX={4} spacingY={4}>
          <FormField label="Category" required error={errors.category}>
            <Select
              value={categoryId}
              placeholder="Select a category"
              onChange={(e) => {
                const next = e.target.value;
                setCategoryId(next);
                setSubCategoryId(subcategoryAfterCategoryChange(subcategories, subCategoryId, next));
              }}
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.status === "Active" ? "" : " (Inactive)"}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Sub-category" required error={errors.subcategory}>
            <Select
              value={subCategoryId}
              placeholder={
                !categoryId
                  ? "Select a category first"
                  : subcategoryChoices.length === 0
                    ? "No sub-categories in this category"
                    : "Select a sub-category"
              }
              isDisabled={!categoryId || subcategoryChoices.length === 0}
              onChange={(e) => setSubCategoryId(e.target.value)}
            >
              {subcategoryChoices.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {subcategoryEffective(s, categories) === "Active" ? "" : " (Inactive)"}
                </option>
              ))}
            </Select>
          </FormField>
        </SimpleGrid>
        <SimpleGrid columns={{ base: 1, md: 2 }} spacingX={4} spacingY={4} alignItems="start">
          <ChipPicker
            label="Domain"
            required
            error={errors.domain}
            placeholder="Select domains"
            options={domains.map((d) => ({ value: d.id, label: d.name, checked: domainIds.includes(d.id) }))}
            onCheck={(value, checked) =>
              setDomainIds(checked ? [...domainIds, value] : domainIds.filter((id) => id !== value))
            }
          />
          <ChipPicker
            label="Supported Languages"
            required
            error={errors.languages}
            helper={
              initial.languagesPrefilled
                ? `No languages are saved for this policy, so ${DEFAULT_POLICY_LANGUAGES.map(languageLabel).join(", ")} is preselected. Check them before saving.`
                : undefined
            }
            placeholder="Select languages"
            options={[
              ...POLICY_LANGUAGES,
              // Codes saved outside the offered list stay visible so they can be removed.
              ...languages
                .filter((code) => !POLICY_LANGUAGES.some((language) => language.code === code))
                .map((code) => ({ code, label: code })),
            ].map(({ code, label }) => ({ value: code, label, checked: languages.includes(code) }))}
            onCheck={(value) => toggle(languages, value, setLanguages)}
          />
        </SimpleGrid>
        <FormField label="Scope" required error={errors.scope}>
          <RadioGroup
            aria-label="Scope"
            value={scope}
            onChange={(value) => setScope(value as PolicyScope)}
          >
            <HStack spacing={5} flexWrap="wrap" rowGap={2}>
              {SCOPE_OPTIONS.map((option) => (
                <Radio key={option} value={option} size="sm">
                  {option}
                </Radio>
              ))}
            </HStack>
          </RadioGroup>
        </FormField>
        <Box borderTopWidth="1px" borderColor="ink.200" />
        <FormControl isInvalid={Boolean(errors.types)}>
          <Flex justify="space-between" align="center" mb={2}>
            <HStack
              as="button"
              type="button"
              spacing={1.5}
              aria-expanded={typesOpen}
              onClick={() => setTypesOpen((v) => !v)}
            >
              {typesOpen ? <ChevronUpIcon /> : <ChevronDownIcon />}
              <Text fontSize="sm" fontWeight="600">
                Link Policy Fields
                <Text as="span" color="red.500" ml={0.5}>
                  *
                </Text>
              </Text>
              <Text fontSize="xs" color="ink.400">
                {/* With Model supported fields shown: ({selectedPicks.length + entityAdditions.length}/{choiceKeys.length + entityKeys.length}) */}
                ({selectedPicks.length}/{choiceKeys.length})
              </Text>
            </HStack>
            {choiceKeys.length > 0 ? (
              <HStack spacing={2} fontSize="xs">
                <Button
                  size="xs"
                  variant="link"
                  colorScheme="orange"
                  onClick={() => {
                    setPicks((prev) => Array.from(new Set([...(prev ?? linkedKeys), ...choiceKeys])));
                    // setEntityPicks(entityKeys);
                  }}
                >
                  Select All
                </Button>
                <Text color="ink.300">|</Text>
                <Button
                  size="xs"
                  variant="link"
                  color="ink.500"
                  onClick={() => {
                    removePicks(choiceKeys);
                    // setEntityPicks([]);
                  }}
                >
                  Clear
                </Button>
              </HStack>
            ) : null}
          </Flex>
          {typesOpen ? (
            <>
              {picks === null && initial.typeIds.length > 0 ? (
                <Text fontSize="xs" color="ink.500" mb={2}>
                  No field selections are saved for this policy, so every field of its linked PII types applies.
                </Text>
              ) : null}
              {typesStatus === "loading" ? (
                <Text fontSize="sm" color="ink.500" mb={2}>
                  Loading PII types…
                </Text>
              ) : null}
              {typesStatus === "error" ? (
                <Text fontSize="sm" color="red.500" mb={2}>
                  {typesError}
                </Text>
              ) : null}
              <ModelEntityStatus languages={languages} lists={entityLists} onRetry={retryEntities} />
              {unavailablePicks.length > 0 ? (
                <Box borderWidth="1px" borderColor="red.200" bg="red.50" borderRadius="md" p={3} mb={2} role="alert">
                  <Flex justify="space-between" align="center" mb={1}>
                    <Text fontSize="sm" fontWeight="600" color="red.700">
                      Unavailable selections ({unavailablePicks.length})
                    </Text>
                    <Button size="xs" variant="link" colorScheme="red" onClick={() => removePicks(unavailablePicks)}>
                      Remove all
                    </Button>
                  </Flex>
                  <Stack spacing={1}>
                    {unavailablePicks.map((key) => {
                      const field = parseSelectedFieldKey(key);
                      const typeName = types.find((type) => type.id === field.typeId)?.name ?? `PII type ${field.typeId}`;
                      return (
                        <Flex key={key} justify="space-between" align="center" gap={2}>
                          <Text fontSize="sm">
                            {fieldLabel(field)} · {typeName} —{" "}
                            <Text as="span" color="red.600">
                              {unavailableReason(field, types, languages, detectable)}
                            </Text>
                          </Text>
                          <Button
                            size="xs"
                            variant="ghost"
                            aria-label={`Remove ${fieldLabel(field)}`}
                            onClick={() => removePicks([key])}
                          >
                            Remove
                          </Button>
                        </Flex>
                      );
                    })}
                  </Stack>
                </Box>
              ) : null}
              {domainIds.length > 0 && choicesReady && typeChoices.length === 0 ? (
                <Text fontSize="sm" color="ink.500">
                  No PII types for the selected domain and languages.
                </Text>
              ) : null}
              <Flex gap={2} mb={2} align="center">
                {typeChoices.length > 0 || otherEntities.length > 0 ? (
                  <Box position="relative" flex="1">
                    <SearchIcon
                      position="absolute"
                      left={2.5}
                      top="50%"
                      transform="translateY(-50%)"
                      color="ink.400"
                      boxSize={3}
                    />
                    <Input
                      size="sm"
                      pl={8}
                      placeholder="Search PII types and entities..."
                      value={typeQuery}
                      onChange={(e) => setTypeQuery(e.target.value)}
                    />
                  </Box>
                ) : null}
                {/* Hidden for now; custom fields saved on an existing policy still show below.
                <Button
                  size="sm"
                  variant="outline"
                  ml="auto"
                  flexShrink={0}
                  onClick={() => {
                    const key = `custom-${draftKeyRef.current++}`;
                    setDrafts((prev) => [...prev, { key, entityName: "", examples: [], regex: "" }]);
                  }}
                >
                  Add custom field
                </Button>
                */}
              </Flex>
              <CustomFieldDrafts
                drafts={drafts}
                errors={errors}
                onChange={(key, patch) =>
                  setDrafts((prev) => prev.map((draft) => (draft.key === key ? { ...draft, ...patch } : draft)))
                }
                onRemove={(key) => setDrafts((prev) => prev.filter((draft) => draft.key !== key))}
              />
              {typeChoices.length > 0 ? (
                <>
                  <Box maxH="240px" overflowY="auto" borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
                    <Stack spacing={3}>
                      {visibleChoices.map((choice) => (
                        <Box key={choice.id}>
                          <Text
                            fontSize="2xs"
                            fontWeight="700"
                            letterSpacing="0.5px"
                            textTransform="uppercase"
                            color="orange.600"
                            borderBottomWidth="1px"
                            borderColor="ink.100"
                            pb={1}
                            mb={2}
                          >
                            {choice.name}
                          </Text>
                          {choice.custom.length > 0 ? (
                            <SimpleGrid columns={2} spacingX={4} spacingY={2}>
                              {choice.custom.map((field) => {
                                const key = selectedFieldKey(field);
                                return (
                                  <Checkbox
                                    key={key}
                                    size="sm"
                                    isChecked={selectedPicks.includes(key)}
                                    onChange={() => togglePick(key)}
                                  >
                                    {field.entityName}
                                  </Checkbox>
                                );
                              })}
                            </SimpleGrid>
                          ) : null}
                          {choice.model.map(([language, fields]) => (
                            <Box key={language} mt={choice.custom.length > 0 ? 3 : 0}>
                              <Text fontSize="2xs" fontWeight="600" color="ink.500" mb={1}>
                                Model-supported · {languageLabel(language)}
                              </Text>
                              <SimpleGrid columns={2} spacingX={4} spacingY={2}>
                                {fields.map((field) => {
                                  const key = selectedFieldKey(field);
                                  return (
                                    <Checkbox
                                      key={key}
                                      size="sm"
                                      isChecked={selectedPicks.includes(key)}
                                      onChange={() => togglePick(key)}
                                    >
                                      {field.entityName}
                                    </Checkbox>
                                  );
                                })}
                              </SimpleGrid>
                            </Box>
                          ))}
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                </>
              ) : null}
              {/* Model supported fields: hidden for now. Restore together with entityKeys in Select All and the count.
              {otherEntities.length > 0 ? (
                <Box mt={3} borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
                  <Text fontSize="sm" fontWeight="600" mb={2}>
                    Model supported fields
                  </Text>
                  <Box maxH="220px" overflowY="auto">
                    <Stack spacing={3}>
                      {visibleOtherEntities.map(([language, entities]) => (
                        <Box key={language}>
                          <Text fontSize="2xs" fontWeight="600" color="ink.500" mb={1}>
                            {languageLabel(language)}
                          </Text>
                          <SimpleGrid columns={2} spacingX={4} spacingY={2}>
                            {entities.map((entityName) => {
                              const key = entityAdditionKey({ language, entityName });
                              return (
                                <Checkbox
                                  key={key}
                                  size="sm"
                                  isChecked={entityPicks.includes(key)}
                                  onChange={() =>
                                    setEntityPicks((prev) =>
                                      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key],
                                    )
                                  }
                                >
                                  {entityName}
                                </Checkbox>
                              );
                            })}
                          </SimpleGrid>
                        </Box>
                      ))}
                      {visibleOtherEntities.length === 0 ? (
                        <Text fontSize="sm" color="ink.500">
                          No entities match the search.
                        </Text>
                      ) : null}
                    </Stack>
                  </Box>
                </Box>
              ) : null}
              */}
            </>
          ) : null}
          {errors.types ? <FormErrorMessage>{errors.types}</FormErrorMessage> : null}
        </FormControl>
      </Stack>
    </FormDrawer>
  );
}

function CustomFieldDrafts({
  drafts,
  errors,
  onChange,
  onRemove,
}: {
  drafts: CustomFieldDraft[];
  errors: Record<string, string>;
  onChange: (key: string, patch: Partial<CustomFieldDraft>) => void;
  onRemove: (key: string) => void;
}) {
  if (drafts.length === 0 && !errors.custom) return null;
  return (
    <Box mb={3}>
      <Stack spacing={3}>
        {drafts.map((draft, index) => (
          <Box key={draft.key} borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
            <Flex justify="space-between" align="center" mb={3} gap={3}>
              <Text fontSize="sm" fontWeight="semibold">
                Custom field {index + 1}
              </Text>
              <Button size="xs" variant="ghost" colorScheme="red" onClick={() => onRemove(draft.key)}>
                Remove
              </Button>
            </Flex>
            <Stack spacing={3}>
              <FormField label="Entity name" required error={errors[`${draft.key}-entity`]}>
                <Input
                  value={draft.entityName}
                  onChange={(e) => onChange(draft.key, { entityName: e.target.value })}
                  placeholder="e.g. CUSTOM_ID"
                />
              </FormField>
              <FormField label="Examples" required error={errors[`${draft.key}-examples`]}>
                <ExampleTags values={draft.examples} onChange={(examples) => onChange(draft.key, { examples })} />
                <Text fontSize="xs" color="ink.400" mt={1}>
                  At least {MIN_REGEX_EXAMPLES} examples. Press Enter to add one.
                </Text>
              </FormField>
              <FormField label="Regex" required error={errors[`${draft.key}-regex`]}>
                <Input
                  fontFamily="mono"
                  value={draft.regex}
                  onChange={(e) => onChange(draft.key, { regex: e.target.value })}
                  placeholder="e.g. \d{4}-\d{4}"
                />
              </FormField>
            </Stack>
          </Box>
        ))}
      </Stack>
      {errors.custom ? (
        <Text fontSize="sm" color="red.500" mt={2} role="alert">
          {errors.custom}
        </Text>
      ) : null}
    </Box>
  );
}

/** GET /pii/entities failures for the policy's languages; saving waits until they load. */
function ModelEntityStatus({
  languages,
  lists,
  onRetry,
}: {
  languages: string[];
  lists: Record<string, EntityList>;
  onRetry: () => void;
}) {
  const failed = languages.filter((language) => lists[language]?.status === "error");
  if (failed.length === 0) return null;
  return (
    <Text fontSize="xs" color="red.500" mb={2}>
      Couldn&apos;t load model supported fields for {failed.map(languageLabel).join(", ")}.{" "}
      <Button size="xs" variant="link" colorScheme="red" onClick={onRetry}>
        Retry
      </Button>
    </Text>
  );
}

/** Multi-select: the picked options sit as removable chips inside the field; the list opens below it. */
function ChipPicker({
  label,
  required,
  error,
  helper,
  placeholder,
  options,
  onCheck,
}: {
  label: string;
  required?: boolean;
  error?: string;
  helper?: string;
  placeholder: string;
  options: { value: string; label: string; checked: boolean }[];
  onCheck: (value: string, checked: boolean) => void;
}) {
  const { isOpen, onToggle, onClose } = useDisclosure();
  const selected = options.filter((option) => option.checked);
  return (
    <FormField label={label} required={required} error={error}>
      <Popover isOpen={isOpen} onClose={onClose} placement="bottom-start" matchWidth isLazy>
        <PopoverTrigger>
          <Flex
            role="combobox"
            aria-expanded={isOpen}
            aria-haspopup="listbox"
            aria-label={label}
            tabIndex={0}
            onClick={onToggle}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
                e.preventDefault();
                onToggle();
              }
            }}
            align="center"
            gap={2}
            minH="40px"
            px={3}
            py={1.5}
            borderWidth="1px"
            borderRadius="md"
            borderColor={error ? "red.500" : isOpen ? "blue.500" : "ink.200"}
            boxShadow={isOpen ? "0 0 0 1px var(--chakra-colors-blue-500)" : undefined}
            bg="white"
            cursor="pointer"
            _hover={{ borderColor: error ? "red.500" : isOpen ? "blue.500" : "ink.300" }}
            _focusVisible={{ borderColor: "blue.500", boxShadow: "0 0 0 1px var(--chakra-colors-blue-500)" }}
          >
            <Wrap flex="1" spacing={1.5}>
              {selected.length === 0 ? (
                <Text fontSize="md" color="ink.400">
                  {placeholder}
                </Text>
              ) : (
                selected.map((option) => (
                  <Tag key={option.value} size="md" colorScheme="blue" borderRadius="full">
                    <TagLabel>{option.label}</TagLabel>
                    <TagCloseButton
                      aria-label={`Remove ${option.label}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onCheck(option.value, false);
                      }}
                    />
                  </Tag>
                ))
              )}
            </Wrap>
            <ChevronDownIcon color="ink.500" boxSize={5} transform={isOpen ? "rotate(180deg)" : undefined} />
          </Flex>
        </PopoverTrigger>
        <Portal>
          <PopoverContent w="auto" boxShadow="md" borderColor="ink.200" _focus={{ boxShadow: "md" }}>
            <PopoverBody p={1} maxH="220px" overflowY="auto" role="listbox" aria-multiselectable>
              {options.map((option) => (
                <Checkbox
                  key={option.value}
                  display="flex"
                  py={2}
                  px={3}
                  borderRadius="md"
                  _hover={{ bg: "ink.50" }}
                  isChecked={option.checked}
                  onChange={(e) => onCheck(option.value, e.target.checked)}
                >
                  {option.label}
                </Checkbox>
              ))}
            </PopoverBody>
          </PopoverContent>
        </Portal>
      </Popover>
      {helper && !error ? (
        <FormHelperText fontSize="xs" color="ink.500" mt={1}>
          {helper}
        </FormHelperText>
      ) : null}
    </FormField>
  );
}

function PolicyViewDrawer() {
  const { drawer, closeDrawer, policies, types, typesStatus, domains, subscriptions, role } = usePiiPolicies();
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
        <Detail label="Scope" value={p.scope} />
        <Detail
          label="Domain"
          value={p.domainIds.map((id) => domainLabel(id, domains)).filter(Boolean).join(", ") || "—"}
        />
        {p.policyType === "Global" || role !== "adopter" ? null : (
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
                subscribers.map((id) => (
                  <Badge textTransform="none" key={id}>
                    {id}
                  </Badge>
                ))
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
          {p.languages.length === 0 ? (
            <Text fontSize="sm" color="ink.500">
              —
            </Text>
          ) : (
            <Wrap>
              {p.languages.map((code) => (
                <Badge textTransform="none" key={code}>
                  {languageLabel(code)}
                </Badge>
              ))}
            </Wrap>
          )}
        </Box>
        {p.selectedFields ? (
          <Box>
            <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
              Selected Policy Fields ({p.selectedFields.length})
            </Text>
            <Wrap>
              {p.selectedFields.map((field) => {
                const type = types.find((t) => t.id === field.typeId);
                const stale = typesStatus === "ready" && !fieldDefined(field, types);
                return (
                  <Badge
                    textTransform="none"
                    key={selectedFieldKey(field)}
                    colorScheme={stale ? "red" : undefined}
                    title={type ? (isPolicyOwnedType(type) ? "Custom field of this policy" : type.name) : undefined}
                  >
                    {fieldLabel(field)}
                    {stale ? " · no longer defined" : ""}
                  </Badge>
                );
              })}
            </Wrap>
          </Box>
        ) : null}
        {role === "adopter" ? (
          <Box>
            <Text fontSize="xs" fontWeight="medium" color="ink.500" textTransform="uppercase" mb={1}>
              Entity Names
            </Text>
            {p.selectedFields == null && p.typeIds.length > 0 ? (
              <Text fontSize="xs" color="ink.500" mb={1}>
                No field selections are saved, so every field of the linked PII types applies.
              </Text>
            ) : null}
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
        ) : null}
      </Stack>
    </FormDrawer>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <ReadOnlyField label={label}>{value}</ReadOnlyField>;
}
