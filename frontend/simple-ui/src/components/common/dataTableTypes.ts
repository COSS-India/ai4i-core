/**
 * Configuration types for the shared {@link DataTable}.
 *
 * Pages own API calls; DataTable owns presentation and emits callbacks.
 */

export type {
  DataTableSortState,
  TableSortDirection as DataTableSortDirection,
} from "../../utils/tableSort";

export type DataTableSearchConfig = {
  value: string;
  onChange: (value: string) => void;
  /**
   * When set, Enter in the search box calls this instead of treating typing
   * as the apply action. Use with an explicit Search button for server search.
   */
  onSubmit?: () => void;
  placeholder?: string;
  label?: string;
  /** Keep the label for screen readers and drop it from the toolbar layout. */
  hideLabel?: boolean;
  /** Short always-visible line under the field. Prefer `hint` for longer guidance. */
  helper?: string;
  /** Info-icon tip on the label (longer / optional guidance). */
  hint?: string;
  /** Validation message shown under the search input. */
  error?: string;
  /**
   * Fields the parent should search (documentation / client helpers).
   * DataTable does not filter rows itself.
   */
  fields?: string[];
  /** Debounce `onChange` in ms. Default: immediate. */
  debounceMs?: number;
  /** Control width. Defaults to a fixed search width. */
  width?: string | Record<string, string>;
};

export type DataTableFilterOption = {
  label: string;
  value: string;
};

/**
 * Declarative filter control rendered by DataTable.
 *
 * `param` is the backend query parameter name (parent maps values → API).
 * `multiselect` stores a comma-separated `value` (empty means all / none selected).
 */
export type DataTableFilterDef = {
  id: string;
  label: string;
  type: "select" | "multiselect" | "date" | "text";
  /** Backend query parameter (informational; parent performs the request). */
  param?: string;
  value: string;
  onChange: (value: string) => void;
  options?: DataTableFilterOption[];
  defaultValue?: string;
  placeholder?: string;
  /** Short always-visible line under the field. Prefer `hint` for longer guidance. */
  helper?: string;
  /** Info-icon tip on the label (longer / optional guidance). */
  hint?: string;
  /** Keep the label for screen readers and drop it from the toolbar layout. */
  hideLabel?: boolean;
  /**
   * Input subtype for `text` / `date` filters.
   * - text: `"text"` (default) or `"number"`
   * - date: `"date"` (default) or `"datetime-local"`
   */
  inputType?: "text" | "number" | "date" | "datetime-local";
  /**
   * Validation message for `text` filters. When set the field is marked
   * invalid (aria-invalid) and this replaces `helper` under the input.
   */
  error?: string;
  /** Width hint for the control. */
  width?: string | Record<string, string>;
  /**
   * Consecutive filters with the same cluster stay on one row and wrap
   * together, so a pair such as start and end time is not split.
   */
  cluster?: string;
};

export type DataTableActionClickPayload<T = unknown> = {
  actionId: string;
  row: T;
};
