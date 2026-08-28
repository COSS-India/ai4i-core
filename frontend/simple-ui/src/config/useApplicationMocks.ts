/**
 * Temporary mock switch for Application Management until auth-service
 * application APIs are live.
 *
 * To go live:
 *   1. Set this to `false`
 *   2. Delete `src/services/applicationMockStore.ts`
 *   3. Remove the mock branch in `applicationService.ts`
 */
export const USE_APPLICATION_MOCKS = true;
