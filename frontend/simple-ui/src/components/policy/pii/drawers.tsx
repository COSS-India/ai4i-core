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
  Radio,
  RadioGroup,
  Select,
  Stack,
  Text,
  Textarea,
  Wrap,
} from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import FieldLabel from "../../common/FieldLabel";
import FormActions from "../../common/FormActions";
import FormDrawer from "../../common/FormDrawer";
import FormSection from "../../common/FormSection";
import ReadOnlyField from "../../common/ReadOnlyField";
import { MIN_REGEX_EXAMPLES } from "./apiMap";
import { regexCompiles } from "./detection";
import {
  HANDLING_OPTIONS,
  domainLabel,
  INSTITUTIONS,
  LANGUAGES,
  NER_MODELS,
  SCOPE_OPTIONS,
  parseExampleValues,
  previewFor,
  type DetectionMode,
  type Handling,
  type MaskingPattern,
  type PolicyScope,
  type PolicyType,
} from "./model";
import { usePiiPolicies, type PolicyInput, type TypeInput } from "./PiiPoliciesProvider";
import { ChoiceCard, handlingBadgeColor } from "./ui";

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

function TypeDrawer() {
  const { drawer, closeDrawer, types, addType, updateType } = usePiiPolicies();
  const open = drawer.kind === "add-type" || drawer.kind === "edit-type";
  const existing = drawer.kind === "edit-type" ? types.find((t) => t.id === drawer.id) : undefined;
  if (!open) return null;

  return (
    <TypeForm
      key={existing?.id ?? "new"}
      title={existing ? "Edit PII Type" : "Add PII Type"}
      submitLabel={existing ? "Save" : "Add PII Type"}
      nameLocked={Boolean(existing)}
      initial={{
        name: existing?.name ?? "",
        examples: existing?.examples.join("\n") ?? "",
        handling: existing?.handling ?? "Mask",
        maskingPattern: existing?.maskingPattern ?? "Partial",
        detectionMode: existing?.detectionMode ?? "Regex",
        regex: existing?.regex ?? "",
        nerModel: existing?.nerModel ?? NER_MODELS[0],
      }}
      onClose={closeDrawer}
      onSave={(input) => (existing ? updateType(existing.id, input) : addType(input))}
    />
  );
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
  initial: {
    name: string;
    examples: string;
    handling: Handling;
    maskingPattern: MaskingPattern;
    detectionMode: DetectionMode;
    regex: string;
    nerModel: string;
  };
  onClose: () => void;
  onSave: (input: TypeInput) => Promise<string | null>;
}) {
  const [name, setName] = useState(initial.name);
  const [examples, setExamples] = useState(initial.examples);
  const [handling, setHandling] = useState<Handling>(initial.handling);
  const [maskingPattern, setMaskingPattern] = useState<MaskingPattern>(initial.maskingPattern);
  const [detectionMode, setDetectionMode] = useState<DetectionMode>(initial.detectionMode);
  const [regex, setRegex] = useState(initial.regex);
  const [nerModel, setNerModel] = useState(initial.nerModel);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (saving) return;
    const next: Record<string, string> = {};
    const parsed = parseExampleValues(examples);
    if (!name.trim()) next.name = "Name is required.";
    if (parsed.length === 0) next.examples = "Add at least one example value.";
    else if (detectionMode === "Regex" && parsed.length < MIN_REGEX_EXAMPLES) {
      next.examples = `Add at least ${MIN_REGEX_EXAMPLES} example values.`;
    }
    if (detectionMode === "Regex" && !regex.trim()) next.regex = "A regex pattern is required in Regex mode.";
    else if (detectionMode === "Regex" && !regexCompiles(regex.trim())) {
      next.regex = "Enter a valid regular expression.";
    }
    if (detectionMode === "Model" && !nerModel) next.model = "Select an NER model.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    try {
      const error = await onSave({
        name: name.trim(),
        examples: parsed,
        handling,
        maskingPattern: handling === "Mask" ? maskingPattern : null,
        detectionMode,
        regex: regex.trim(),
        nerModel,
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
        <FormField label="PII Type Name" required error={errors.name}>
          <Input
            value={name}
            isDisabled={nameLocked}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Passport Number"
          />
        </FormField>
        <FormField label="Example Values" required error={errors.examples}>
          <Textarea
            value={examples}
            onChange={(e) => setExamples(e.target.value)}
            rows={3}
            placeholder={"One value per line\n9876543210"}
          />
        </FormField>
      </FormSection>
      <FormSection title="Handling">
        <Flex gap={8} wrap="wrap">
          <Box>
            <FieldLabel required>Handling</FieldLabel>
            <RadioGroup value={handling} onChange={(v) => setHandling(v as Handling)}>
              <HStack spacing={4}>
                {HANDLING_OPTIONS.map((h) => (
                  <Radio key={h} value={h} size="sm">
                    {h}
                  </Radio>
                ))}
              </HStack>
            </RadioGroup>
          </Box>
          {handling === "Mask" ? (
            <Box>
              <FieldLabel>Format</FieldLabel>
              <RadioGroup value={maskingPattern} onChange={(v) => setMaskingPattern(v as MaskingPattern)}>
                <HStack spacing={4}>
                  {(["Full", "Partial"] as const).map((f) => (
                    <Radio key={f} value={f} size="sm">
                      {f}
                    </Radio>
                  ))}
                </HStack>
              </RadioGroup>
            </Box>
          ) : null}
        </Flex>
      </FormSection>
      <FormSection title="Detection">
        <Box>
          <FieldLabel required>Detection Mode</FieldLabel>
          <RadioGroup value={detectionMode} onChange={(v) => setDetectionMode(v as DetectionMode)}>
            <HStack spacing={4}>
              {(["Regex", "Model"] as const).map((m) => (
                <Radio key={m} value={m} size="sm">
                  {m}
                </Radio>
              ))}
            </HStack>
          </RadioGroup>
        </Box>
        {detectionMode === "Regex" ? (
          <FormField label="Regex Pattern" required error={errors.regex}>
            <Input
              fontFamily="mono"
              value={regex}
              onChange={(e) => setRegex(e.target.value)}
              placeholder="e.g. \b[A-Z]{5}\d{4}[A-Z]\b"
            />
          </FormField>
        ) : (
          <FormField label="NER Model" required error={errors.model}>
            <Select value={nerModel} onChange={(e) => setNerModel(e.target.value)}>
              {NER_MODELS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </FormField>
        )}
        <ReadOnlyField label="Preview">
          <Badge colorScheme="orange" fontFamily="mono" textTransform="none">
            {previewFor(handling, handling === "Mask" ? maskingPattern : null)}
          </Badge>
        </ReadOnlyField>
      </FormSection>
    </FormDrawer>
  );
}

function TypeViewDrawer() {
  const { drawer, closeDrawer, types, domains, openDrawer } = usePiiPolicies();
  if (drawer.kind !== "view-type") return null;
  const t = types.find((x) => x.id === drawer.id);
  if (!t) return null;
  const domain = t.domainId ? domains.find((d) => d.id === t.domainId)?.name : "General";

  return (
    <FormDrawer
      isOpen
      onClose={closeDrawer}
      title="View PII Type"
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
        <ReadOnlyField label="PII Type Name">{t.name}</ReadOnlyField>
        <ReadOnlyField label="Domain">{domain ?? "General"}</ReadOnlyField>
        <ReadOnlyField label="Example Values">
          <Wrap>
            {t.examples.map((ex) => (
              <Badge textTransform="none" key={ex}>{ex}</Badge>
            ))}
          </Wrap>
        </ReadOnlyField>
        <Box borderTopWidth="1px" borderColor="ink.200" />
        <Flex gap={8} wrap="wrap">
          <Segment label="Handling" options={HANDLING_OPTIONS} current={t.handling} />
          {t.handling === "Mask" ? (
            <Segment label="Format" options={["Full", "Partial"]} current={t.maskingPattern ?? "Partial"} />
          ) : null}
        </Flex>
        <ReadOnlyField label="Detection Mode">
          {t.detectionMode}
          {t.detectionMode === "Model" ? ` · ${t.nerModel}` : ""}
          {t.detectionMode === "Regex" ? (
            <Text mt={1} fontFamily="mono" fontSize="xs" bg="ink.50" px={2} py={1} borderRadius="md" display="inline-block">
              {t.regex}
            </Text>
          ) : null}
        </ReadOnlyField>
        <ReadOnlyField label="Preview">
          <Badge colorScheme="orange" fontFamily="mono" textTransform="none">
            {previewFor(t.handling, t.maskingPattern)}
          </Badge>
        </ReadOnlyField>
      </Stack>
    </FormDrawer>
  );
}

function Segment({ label, options, current }: { label: string; options: readonly string[]; current: string }) {
  return (
    <Box>
      <FieldLabel>{label}</FieldLabel>
      <HStack borderWidth="1px" borderColor="ink.200" borderRadius="lg" p={0.5} spacing={0} w="fit-content">
        {options.map((o) => (
          <Text
            key={o}
            px={3}
            py={1.5}
            fontSize="sm"
            fontWeight="medium"
            borderRadius="md"
            bg={current === o ? "brand.500" : "transparent"}
            color={current === o ? "white" : "ink.500"}
          >
            {o}
          </Text>
        ))}
      </HStack>
    </Box>
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

  const grouped = useMemo(() => {
    const q = typeQuery.toLowerCase();
    const buckets: Record<Handling, typeof types> = { Mask: [], Redact: [], Hash: [] };
    types
      .filter((t) => t.name.toLowerCase().includes(q))
      .forEach((t) => buckets[t.handling].push(t));
    return buckets;
  }, [types, typeQuery]);

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
    if (typeIds.length === 0) next.types = "Link at least one PII type.";
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
        typeIds,
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
        <FormField label={`Link PII Types (${typeIds.length}/${types.length})`} required error={errors.types}>
          {typesStatus === "loading" ? (
            <Text fontSize="sm" color="ink.500" mb={2}>
              Loading PII definitions…
            </Text>
          ) : null}
          {typesStatus === "error" ? (
            <Text fontSize="sm" color="red.500" mb={2}>
              {typesError}
            </Text>
          ) : null}
          <Flex justify="space-between" mb={2}>
            <Button size="sm" variant="ghost" onClick={() => setTypesOpen((v) => !v)}>
              {typesOpen ? "Hide" : "Show"} types
            </Button>
            <HStack spacing={2}>
              <Button size="xs" variant="link" onClick={() => setTypeIds(types.map((t) => t.id))}>
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
                  placeholder="Search PII types..."
                  value={typeQuery}
                  onChange={(e) => setTypeQuery(e.target.value)}
                />
              </Box>
              <Box maxH="200px" overflowY="auto" borderWidth="1px" borderColor="ink.200" borderRadius="md" p={3}>
                <Stack spacing={4}>
                  {(["Mask", "Redact", "Hash"] as const).map((handling) =>
                    grouped[handling].length === 0 ? null : (
                      <Box key={handling}>
                        <Badge colorScheme={handlingBadgeColor(handling)} mb={2} textTransform="uppercase" fontSize="10px">
                          {handling}
                        </Badge>
                        <Box display="grid" gridTemplateColumns="1fr 1fr" gap={1}>
                          {grouped[handling].map((t) => (
                            <Checkbox
                              key={t.id}
                              size="sm"
                              isChecked={typeIds.includes(t.id)}
                              onChange={() => toggle(typeIds, t.id, setTypeIds)}
                            >
                              {t.name}
                            </Checkbox>
                          ))}
                        </Box>
                      </Box>
                    ),
                  )}
                </Stack>
              </Box>
            </Box>
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
            Linked PII Types ({p.typeIds.length})
          </Text>
          <Wrap>
            {p.typeIds.map((id) => {
              const t = types.find((x) => x.id === id);
              return t ? <Badge textTransform="none" key={id}>{t.name}</Badge> : null;
            })}
          </Wrap>
        </Box>
      </Stack>
    </FormDrawer>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <ReadOnlyField label={label}>{value}</ReadOnlyField>;
}
