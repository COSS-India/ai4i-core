/**
 * Column selection rules shared by the admin list column pickers (Services,
 * Models, …). Each list supplies its catalogue and its default selection.
 */

export type SelectableColumn = {
  id: string;
  /** Always visible; the picker cannot turn these off. */
  mandatory: boolean;
};

/** Default selection for a catalogue (first visit and Reset to default). */
export type DefaultColumnIds<T extends SelectableColumn> = (
  catalogue: readonly T[],
) => string[];

/**
 * Keep mandatory columns and drop unknown ids. Optional columns may all be
 * hidden; defaults apply only when nothing usable is stored (first visit, or
 * every stored id is gone from the catalogue). Result is catalogue order.
 */
export function resolveColumnSelection<T extends SelectableColumn>(
  selected: readonly string[] | null | undefined,
  catalogue: readonly T[],
  defaults: DefaultColumnIds<T>,
): string[] {
  const known = new Set(catalogue.map((column) => column.id));
  const picked = new Set((selected ?? []).filter((id) => known.has(id)));
  if (picked.size === 0) return defaults(catalogue);
  return catalogue
    .filter((column) => column.mandatory || picked.has(column.id))
    .map((column) => column.id);
}

/** Only mandatory columns are locked; every optional column can be turned off. */
export function canToggleOffColumn(
  id: string,
  catalogue: readonly SelectableColumn[],
): boolean {
  const column = catalogue.find((entry) => entry.id === id);
  return column != null && !column.mandatory;
}

/** Turn an optional column on or off. Mandatory columns stay. */
export function toggleColumnSelection<T extends SelectableColumn>(
  current: readonly string[],
  id: string,
  catalogue: readonly T[],
  defaults: DefaultColumnIds<T>,
): string[] {
  if (!canToggleOffColumn(id, catalogue)) {
    return resolveColumnSelection(current, catalogue, defaults);
  }
  const next = current.includes(id)
    ? current.filter((columnId) => columnId !== id)
    : [...current, id];
  return resolveColumnSelection(next, catalogue, defaults);
}
