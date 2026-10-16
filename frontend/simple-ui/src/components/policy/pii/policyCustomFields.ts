import type { PiiType, Policy } from "./model";

/**
 * Fields added in the policy form belong to that policy alone. platform-core has nowhere to keep them
 * on the policy yet, so they live on a PII type the policy owns, named after the policy. The PII type
 * lists and the policy form's type choices leave owned types out.
 */
const OWNED_TYPE_PREFIX = "__policy__:";
/** policy_type is VARCHAR(100). */
const TYPE_NAME_MAX = 100;

export function isPolicyOwnedType(type: Pick<PiiType, "name">): boolean {
  return type.name.startsWith(OWNED_TYPE_PREFIX);
}

export function sharedTypes(types: PiiType[]): PiiType[] {
  return types.filter((type) => !isPolicyOwnedType(type));
}

/** Policy names are unique ignoring case, so the lowercased name identifies the policy. */
export function policyOwnedTypeName(policyName: string): string {
  const key = policyName.trim().toLowerCase();
  const name = `${OWNED_TYPE_PREFIX}${key}`;
  if (name.length <= TYPE_NAME_MAX) return name;
  const hash = fnv1a(key);
  const room = TYPE_NAME_MAX - OWNED_TYPE_PREFIX.length - hash.length - 1;
  return `${OWNED_TYPE_PREFIX}${key.slice(0, room)}~${hash}`;
}

export function policyOwnedType(policy: Pick<Policy, "typeIds">, types: PiiType[]): PiiType | undefined {
  return types.find((type) => policy.typeIds.includes(type.id) && isPolicyOwnedType(type));
}

function fnv1a(value: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
