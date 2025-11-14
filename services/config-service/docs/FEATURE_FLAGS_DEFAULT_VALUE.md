# Understanding Default Values in Feature Flags

## What is `default_value`?

The `default_value` is a **required parameter** you provide when evaluating a feature flag. It serves as the fallback value that will be returned in the `value` field when:

1. The flag doesn't exist
2. The flag is disabled (`is_enabled: false`)
3. The user doesn't match targeting rules
4. Evaluation fails (network error, etc.)

## How `value` is Determined

The `value` field in the response is determined as follows:

| Scenario | `value` | `reason` |
|----------|---------|----------|
| Flag enabled + user matches targeting | Evaluated result (could be `true`, variant, etc.) | `TARGETING_MATCH` |
| Flag enabled + user doesn't match | **`default_value`** | `DEFAULT` |
| Flag disabled | **`default_value`** | `DISABLED` |
| Flag doesn't exist | **`default_value`** | `ERROR` |
| Evaluation error | **`default_value`** | `ERROR` |

**Key Point**: The `value` field will **always equal your `default_value`** when the flag is disabled, doesn't exist, or the user doesn't match targeting.

## Evaluation Reasons Explained

The `reason` field in the evaluation response tells you **why** a specific value was returned. Understanding these reasons helps you debug feature flag behavior and understand what's happening in your system.

### TARGETING_MATCH

**What it means**: The flag is enabled and the user/context matches the targeting rules configured in Unleash.

**When you'll see this**:
- The flag is enabled (`is_enabled: true`) in the specified environment
- The user matches targeting criteria (user ID in target list, percentage rollout selected them, constraints match, etc.)
- For boolean flags without targeting: flag is enabled and has no targeting rules (everyone gets it)

**What the value means**:
- For boolean flags: `value` will be `true` (the feature is active)
- For string/integer/float flags: `value` will be the configured variant or evaluated result
- For object flags: `value` will be the configured object/variant

**Example Response**:
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",  // ← User matches targeting, feature is ON
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**Use case**: This is the "success" case - the feature flag is working as intended and the user should see the feature.

---

### DEFAULT

**What it means**: The flag is enabled, but the user/context doesn't match the targeting rules, OR the evaluation determined the default value should be used.

**When you'll see this**:
- The flag is enabled (`is_enabled: true`) in the specified environment
- BUT the user doesn't match targeting criteria:
  - User ID is not in the target list
  - Percentage rollout didn't select this user (e.g., 50% rollout, user falls in the other 50%)
  - Context attributes don't match constraints (e.g., region, plan, etc.)
- For non-boolean flags: when the flag is enabled but no variant matches

**What the value means**:
- `value` will always equal your `default_value`
- The feature is NOT active for this user (even though the flag is enabled)

**Example Response**:
```json
{
  "flag_name": "premium-features",
  "value": false,        // ← Same as default_value
  "variant": null,
  "reason": "DEFAULT",   // ← Flag is enabled but user doesn't match targeting
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**Use case**: Gradual rollouts, A/B testing, or targeted feature releases where not everyone gets the feature even though it's enabled.

---

### DISABLED

**What it means**: The flag exists but is explicitly disabled in the specified environment.

**When you'll see this**:
- The flag exists in Unleash
- The flag is disabled (`is_enabled: false`) for the requested environment
- This is an intentional "off" state (not an error)

**What the value means**:
- `value` will always equal your `default_value`
- The feature is intentionally turned off
- The `reason` field tells you it's disabled (not an error)

**Example Response**:
```json
{
  "flag_name": "new-ui-enabled",
  "value": false,        // ← Same as default_value
  "variant": null,
  "reason": "DISABLED",  // ← Flag is intentionally disabled
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**Use case**: Emergency kill switches, feature toggles, or when you want to temporarily disable a feature without deleting it.

---

### ERROR

**What it means**: Something went wrong during evaluation, so the system returned the safe default value.

**When you'll see this**:
- The flag doesn't exist in Unleash (wrong name or environment)
- Unleash server is unavailable or unreachable
- Network error connecting to Unleash
- Invalid flag configuration
- SDK evaluation failed and fallback also failed
- Authentication/authorization error with Unleash API

**What the value means**:
- `value` will always equal your `default_value` (safe fallback)
- The system couldn't determine the actual flag state, so it defaults to safe behavior
- The `reason` field indicates an error occurred

**Example Response**:
```json
{
  "flag_name": "non-existent-flag",
  "value": false,        // ← Same as default_value (safe fallback)
  "variant": null,
  "reason": "ERROR",     // ← Flag doesn't exist or evaluation failed
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**Use case**: Error handling - your application should treat this as "feature is off" and continue operating normally. Check logs if you see unexpected ERROR reasons.

---

## Quick Reference: Reason Types

| Reason | Flag State | User Matches? | Value | Meaning |
|--------|-----------|---------------|-------|---------|
| `TARGETING_MATCH` | Enabled | ✅ Yes | Evaluated result | Feature is ON for this user |
| `DEFAULT` | Enabled | ❌ No | `default_value` | Feature is OFF (user doesn't match targeting) |
| `DISABLED` | Disabled | N/A | `default_value` | Feature is OFF (intentionally disabled) |
| `ERROR` | Unknown | N/A | `default_value` | Feature is OFF (evaluation failed) |

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
  "variant": null,
  "reason": "DISABLED",  // ← Flag is disabled
  "evaluated_at": "2024-01-15T10:30:00Z"
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
  "variant": null,
  "reason": "DEFAULT",   // ← Flag is enabled but user doesn't match targeting
  "evaluated_at": "2024-01-15T10:30:00Z"
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
  "variant": null,
  "reason": "DISABLED",  // ← Flag is disabled
  "evaluated_at": "2024-01-15T10:30:00Z"
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

