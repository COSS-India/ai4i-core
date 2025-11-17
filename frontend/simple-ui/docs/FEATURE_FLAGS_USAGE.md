# Feature Flags Integration Guide

This guide shows how to use feature flags in the UI to conditionally enable/disable features.

## Quick Start

### 1. Import the hook

```tsx
import { useFeatureFlag } from '../hooks/useFeatureFlag';
```

### 2. Use in your component

```tsx
const MyComponent = () => {
  const { isEnabled, isLoading } = useFeatureFlag({
    flagName: 'my-feature-enabled',
    environment: 'development', // or 'staging', 'production'
    defaultValue: false, // What to return if flag doesn't exist
  });

  if (isLoading) {
    return <Spinner />;
  }

  if (isEnabled) {
    return <NewFeature />;
  }

  return <OldFeature />;
};
```

## Examples

### Conditionally Show/Hide UI Elements

```tsx
const { isEnabled: showBetaFeatures } = useFeatureFlag({
  flagName: 'beta-features-enabled',
  environment: 'development',
  defaultValue: false,
});

return (
  <>
    <StandardFeatures />
    {showBetaFeatures && <BetaFeatures />}
  </>
);
```

### Enable/Disable Features Based on User

The hook automatically uses the current user's ID for targeting:

```tsx
const { isEnabled } = useFeatureFlag({
  flagName: 'premium-features',
  environment: 'production',
  defaultValue: false,
  // User ID is automatically included from useAuth
});
```

### With Additional Context

```tsx
const { isEnabled } = useFeatureFlag({
  flagName: 'region-specific-feature',
  environment: 'production',
  defaultValue: false,
  context: {
    region: 'us-west',
    plan: 'premium',
  },
});
```

### Using Non-Boolean Values

For string, number, or object flags:

```tsx
import { useFeatureFlagValue } from '../hooks/useFeatureFlag';

const { value: maxUploadSize } = useFeatureFlagValue({
  flagName: 'max-upload-size',
  environment: 'production',
  defaultValue: 10, // MB
});

// Use the value
if (fileSize > maxUploadSize) {
  // Show error
}
```

## API

### `useFeatureFlag(options)`

Evaluates a boolean feature flag.

**Options:**
- `flagName` (string, required): Name of the feature flag in Unleash
- `environment` (string, optional): Environment name (default: 'development')
- `defaultValue` (boolean, optional): Default value if flag doesn't exist (default: false)
- `enabled` (boolean, optional): Whether to run the query (default: true)
- `context` (object, optional): Additional context for targeting

**Returns:**
- `isEnabled` (boolean): Whether the flag is enabled
- `isLoading` (boolean): Loading state
- `error` (Error | null): Error if evaluation failed
- `reason` (string | undefined): Why the flag returned this value
- `refetch` (function): Manually refetch the flag

### `useFeatureFlagValue<T>(options)`

Evaluates a feature flag with any value type.

**Options:** Same as `useFeatureFlag`, but `defaultValue` can be any type.

**Returns:** Same as `useFeatureFlag`, plus:
- `value` (T): The flag value
- `variant` (string | undefined): Variant name if applicable

## Notes

- **Caching Strategy**: Feature flags are cached for 30 seconds to reduce API calls
- **Auto-refresh**: Flags automatically refresh when the window regains focus
- **User Targeting**: The hook automatically includes the current user ID from `useAuth` for targeting
- **Default Values**: If the flag doesn't exist, it returns the `defaultValue`
- **Manual Refresh**: Use the `refetch()` function to manually refresh a flag when needed
- **React Query**: Uses React Query for intelligent caching and automatic refetching

