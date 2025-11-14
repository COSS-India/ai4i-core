# Understanding Default Values in Feature Flags

## What is `default_value`?

The `default_value` is a **required parameter** you provide when evaluating a feature flag. It serves as the fallback value that will be returned in the `value` field when:

1. The flag doesn't exist
2. The flag is disabled (`is_enabled: false`)
3. The user doesn't match targeting rules
4. Evaluation fails (network error, etc.)

## How `value` is Determined

The `value` field in the response is determined as follows:

| Scenario | `value` | `is_enabled` | `reason` |
|----------|---------|--------------|----------|
| Flag enabled + user matches targeting | Evaluated result (could be `true`, variant, etc.) | `true` | `TARGETING_MATCH` |
| Flag enabled + user doesn't match | **`default_value`** | `true` | `DEFAULT` |
| Flag disabled | **`default_value`** | `false` | `DISABLED` |
| Flag doesn't exist | **`default_value`** | `false` | `ERROR` |
| Evaluation error | **`default_value`** | `false` | `ERROR` |

**Key Point**: The `value` field will **always equal your `default_value`** when the flag is disabled, doesn't exist, or the user doesn't match targeting.

## Recommended Default Values

### Boolean Flags
```json
{
  "flag_name": "new-ui-enabled",
  "default_value": false  // ← Safe default: feature is OFF
}
```

**Why `false`?**
- If the flag doesn't exist or is disabled, you want the feature to be OFF
- This is the "safe" default that won't break your application
- Only enable the feature when explicitly enabled in Unleash

### String Flags
```json
{
  "flag_name": "button-color",
  "default_value": "blue"  // ← Sensible default color
}
```

**Why a specific string?**
- Use a value that makes sense for your application
- Could be `"blue"`, `""` (empty), or any valid default
- This is what users will see if the flag doesn't match

### Integer Flags
```json
{
  "flag_name": "max-upload-size",
  "default_value": 10  // ← Safe default: 10 MB
}
```

**Why a specific number?**
- Use a minimum safe value
- Could be `0` for limits, or a reasonable default like `10` for sizes
- This ensures your app has a valid value even if the flag fails

### Float Flags
```json
{
  "flag_name": "discount-percentage",
  "default_value": 0.0  // ← Safe default: no discount
}
```

**Why `0.0`?**
- Use a minimum safe value
- `0.0` means "no discount" which is safe
- Only apply discounts when explicitly configured

### Object Flags
```json
{
  "flag_name": "api-config",
  "default_value": {  // ← Minimal safe configuration
    "timeout": 30,
    "retries": 3
  }
}
```

**Why a minimal object?**
- Provide a configuration that works even if the flag fails
- Include only essential fields with safe values
- This ensures your app can function with basic settings

## Examples

### Example 1: Boolean Flag - Disabled

**Request:**
```json
{
  "flag_name": "new-ui-enabled",
  "default_value": false,
  "environment": "development"
}
```

**Response (flag is disabled):**
```json
{
  "flag_name": "new-ui-enabled",
  "value": false,        // ← Same as default_value
  "is_enabled": false,   // ← Flag is disabled
  "reason": "DISABLED"
}
```

**Your code:**
```typescript
if (result.value) {  // false - feature is off
  showNewUI();
}
```

### Example 2: Boolean Flag - Enabled but User Doesn't Match

**Request:**
```json
{
  "flag_name": "premium-features",
  "default_value": false,
  "user_id": "user-123",
  "environment": "production"
}
```

**Response (flag enabled, but user not in target list):**
```json
{
  "flag_name": "premium-features",
  "value": false,        // ← Same as default_value
  "is_enabled": true,     // ← Flag is enabled in Unleash
  "reason": "DEFAULT"     // ← But user doesn't match
}
```

**Your code:**
```typescript
if (result.value) {  // false - user doesn't get feature
  showPremiumFeatures();
}
```

### Example 3: String Flag - Disabled

**Request:**
```json
{
  "flag_name": "button-color",
  "default_value": "blue",
  "environment": "production"
}
```

**Response (flag is disabled):**
```json
{
  "flag_name": "button-color",
  "value": "blue",       // ← Same as default_value
  "is_enabled": false,
  "reason": "DISABLED"
}
```

**Your code:**
```typescript
button.style.color = result.value;  // "blue" - default color
```

## Best Practices

### ✅ DO: Use Safe Defaults

```typescript
// Good: Safe default (feature off)
const { value } = await evaluateFeatureFlag({
  flag_name: "experimental-feature",
  default_value: false  // ← Safe: feature is off by default
});
```

```typescript
// Good: Sensible default value
const { value } = await evaluateFeatureFlag({
  flag_name: "max-file-size",
  default_value: 10  // ← Safe: 10 MB limit
});
```

### ❌ DON'T: Use Unsafe Defaults

```typescript
// Bad: Unsafe default (feature on by default)
const { value } = await evaluateFeatureFlag({
  flag_name: "experimental-feature",
  default_value: true  // ← Dangerous: feature on if flag fails!
});
```

```typescript
// Bad: No default value (will cause error)
const { value } = await evaluateFeatureFlag({
  flag_name: "max-file-size"
  // Missing default_value - API will reject this
});
```

## Summary

- **`default_value`** is what you provide in the request
- **`value`** in the response will be `default_value` when:
  - Flag is disabled
  - Flag doesn't exist
  - User doesn't match targeting
  - Evaluation fails
- **Always use safe defaults**: `false` for booleans, `0` for numbers, sensible strings/objects
- **The `value` field is what you use in your code** - it will always have a valid value thanks to `default_value`

## Key Takeaway

**The `value` field will always equal your `default_value` when the flag is disabled or doesn't match targeting.** This ensures your application always has a safe, predictable value to use, even when things go wrong.

