# Global UI standards

Locked conventions for `frontend/simple-ui`. Reuse existing shared components. Do not invent a parallel design system.

## Primary

- Create / Add / New → blue primary
- Save / Update / Submit → blue primary
- Delete / Revoke → destructive
- Cancel / Close → outline
- Disabled → `not-allowed`

## Management

- `ManagementPageHeader` for management pages
- `CreateButton` for page-level Create / Add
- `CreateModal` for Create
- `StandardModal` for Edit / View
- `FormActions` for standardized form actions
- `FieldLabel` + `FieldHint` + `FormErrorMessage` for management fields

Long-detail View (Model, Service) stays a tab/page. Complex workflows (e.g. Manage Tier) keep their existing container.

## Tables

- Institution-style toolbar
- Search / filter consistency
- Pagination below the table
- Row click = View where meaningful
- Pointer only for clickable rows
- Action controls must not trigger row View
- No row click for expansion / inline-edit / selection tables

Do not modify `DataTable.tsx` unless explicitly asked.

## Visual

- Cool slate neutrals (`ink`)
- Blue global interaction colour
- Service / task colours remain identity colours
- Semantic colours remain semantic
- No page-specific warm / brick palette
