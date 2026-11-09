import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useModelRegistryList } from "../../src/components/model-management/useModelRegistryList";
import { getModelsPaginated } from "../../src/services/modelManagementService";

jest.mock("../../src/services/modelManagementService", () => ({
  MODEL_LIST_QUERY_KEY: ["models", "list"],
  getModelsPaginated: jest.fn(),
}));

const mockGetModelsPaginated = getModelsPaginated as jest.MockedFunction<
  typeof getModelsPaginated
>;

// 30 models at 25 per page: page 1 is full, page 2 has 5 rows, page 3 is empty.
const TOTAL = 30;
const rows = (count: number) =>
  Array.from({ length: count }, (_, i) => ({ modelId: `m${i}`, name: `m${i}`, version: "1" }));

const modelSort = {
  sort: { key: "", direction: "asc" as const },
  onSortChange: jest.fn(),
};
const enabledTaskTypes = ["nmt"];

function renderRegistry() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    () =>
      useModelRegistryList({
        columns: "name,version,actions",
        enabledTaskTypes,
        modelSort,
        enabled: true,
      }),
    { wrapper },
  );
}

describe("useModelRegistryList", () => {
  beforeEach(() => {
    mockGetModelsPaginated.mockReset();
    mockGetModelsPaginated.mockImplementation(async (params = {}) => {
      const offset = params.offset ?? 0;
      const limit = params.limit ?? 25;
      const count = Math.max(0, Math.min(limit, TOTAL - offset));
      return { items: rows(count), total: TOTAL, offset, limit };
    });
  });

  it("steps back from an empty page to the last page with data, and stays there", async () => {
    const { result } = renderRegistry();
    await waitFor(() => expect(result.current.items).toHaveLength(25));

    act(() => result.current.setPage(3));

    await waitFor(() => expect(result.current.page).toBe(2));
    await waitFor(() => expect(result.current.items).toHaveLength(5));
    // Page 3's empty placeholder must not trigger a second step back to page 1.
    expect(result.current.page).toBe(2);
    // Page 1 was requested once, on mount, and never again.
    const page1Calls = mockGetModelsPaginated.mock.calls.filter(([params]) => params?.offset === 0);
    expect(page1Calls).toHaveLength(1);
  });

  it("keeps the current rows on screen while the next page loads", async () => {
    const { result } = renderRegistry();
    await waitFor(() => expect(result.current.items).toHaveLength(25));

    let release: () => void = () => undefined;
    mockGetModelsPaginated.mockImplementationOnce(
      (params = {}) =>
        new Promise((resolve) => {
          release = () =>
            resolve({ items: rows(5), total: TOTAL, offset: params.offset ?? 0, limit: 25 });
        }),
    );

    act(() => result.current.setPage(2));

    // While page 2 loads, page 1's rows stay and the table is not in its loading state.
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items).toHaveLength(25);

    act(() => release());
    await waitFor(() => expect(result.current.items).toHaveLength(5));
  });
});
