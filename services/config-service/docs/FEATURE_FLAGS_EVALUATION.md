# Feature Flag Evaluation Guide

## What is Flag Evaluation?

**Flag evaluation** is the process of determining the value of a feature flag for a specific user and context. Think of it as asking: "For this user, in this situation, what should this feature flag return?"

### Why Evaluate Flags?

Feature flags allow you to:
- **Control feature rollouts**: Gradually enable features for specific users
- **A/B testing**: Test different variants with different user segments
- **User targeting**: Enable features for specific users (beta testers, premium users)
- **Environment control**: Enable features only in specific environments
- **Emergency kill switches**: Quickly disable features if issues arise

## Evaluation Process

When you evaluate a flag, the system:

1. **Checks Redis cache** - If the same flag was evaluated recently for the same user/context, return cached result
2. **Queries Unleash** - If not cached, ask Unleash what value to return
3. **Applies targeting rules** - Unleash checks:
   - Is the flag enabled in this environment?
   - Does the user match any targeting strategies?
   - What percentage rollout is configured?
   - Do any constraints apply?
4. **Returns result** - The evaluated value, reason, and variant (if applicable)
5. **Caches result** - Stores in Redis for fast future lookups

## Request Parameters Explained

### Required Parameters

#### `flag_name` (string, required)
The name of the feature flag to evaluate. Must exactly match the flag name in Unleash.

**Example**: `"new-ui-enabled"`

#### `default_value` (bool/str/int/float/dict, required)
The fallback value to return if:
- The flag doesn't exist
- The flag evaluation fails
- Unleash is unavailable

**Also determines the flag type:**
- `false` or `true` → Boolean flag
- `"blue"` → String flag
- `0` → Integer flag
- `0.0` → Float flag
- `{}` → Object/JSON flag

**Example**: `false` (for boolean flags)

#### `environment` (string, required)
The environment name. Must match one of the environments configured in Unleash.

**Allowed values**: `"development"`, `"staging"`, `"production"`

**Example**: `"development"`

### Optional Parameters

#### `user_id` (string, optional)
User identifier for user-based targeting. Used by strategies like:
- **userWithId**: Target specific users by ID
- **Gradual rollout**: Consistent rollout based on user ID hash

**When to use:**
- You want to target specific users
- You need consistent evaluation for the same user
- You're doing gradual rollouts

**Example**: `"user-123"`

**Note**: If not provided, the flag will be evaluated without user context (may affect targeting strategies).

#### `context` (object, optional)
Additional context attributes for advanced targeting. Can include any key-value pairs.

**Common use cases:**

1. **Region-based targeting**
   ```json
   {
     "region": "us-west",
     "country": "US"
   }
   ```

2. **Plan-based targeting**
   ```json
   {
     "plan": "premium",
     "subscription_active": true
   }
   ```

3. **Custom attributes**
   ```json
   {
     "beta": true,
     "department": "engineering",
     "team": "backend"
   }
   ```

4. **Multiple attributes**
   ```json
   {
     "region": "us-west",
     "plan": "premium",
     "beta": true,
     "custom_field": "value"
   }
   ```

**How strategies use context:**

Unleash strategies can use these context attributes to determine if a flag should be enabled:
- **Constraints**: Check if context values match specific conditions
- **Custom strategies**: Use any context attribute for targeting logic
- **Segment targeting**: Match users based on context attributes

## Evaluation Endpoints

### 1. POST /evaluate - Detailed Evaluation

Returns full evaluation details including value, variant, reason, and timestamp.

**When to use:**
- You need to know why a flag returned a specific value
- You're debugging flag behavior
- You need variant information
- You want evaluation metadata

**Example Request:**
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {"region": "us-west"},
  "default_value": false,
  "environment": "development"
}
```

**Example Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

### 2. POST /evaluate/boolean - Simple Boolean

Returns just the boolean value and reason. Faster and simpler.

**When to use:**
- You only need true/false
- You don't need evaluation metadata
- Performance is critical
- Simple feature gating

**Example Request:**
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {"region": "us-west"},
  "default_value": false,
  "environment": "development"
}
```

**Example Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "reason": "TARGETING_MATCH"
}
```

### 3. POST /evaluate/bulk - Multiple Flags

Evaluate multiple flags in a single request. All flags are evaluated in parallel.

**When to use:**
- You need to check multiple flags at once
- You want to reduce API calls
- Evaluating flags for the same user/context
- Building a feature flag dashboard

**Example Request:**
```json
{
  "flag_names": ["new-ui-enabled", "dark-mode", "beta-features"],
  "user_id": "user-123",
  "context": {"region": "us-west", "plan": "premium"},
  "environment": "development"
}
```

**Example Response:**
```json
{
  "results": {
    "new-ui-enabled": {
      "flag_name": "new-ui-enabled",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "dark-mode": {
      "flag_name": "dark-mode",
      "value": false,
      "variant": null,
      "reason": "DEFAULT",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "beta-features": {
      "flag_name": "beta-features",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

## Evaluation Reasons

The `reason` field tells you why a flag returned a specific value:

### TARGETING_MATCH
The flag is enabled and the user/context matches the targeting rules.

**Examples:**
- User ID is in the target list
- User matches percentage rollout
- Context attributes match constraints
- Strategy conditions are met

**What it means**: The flag is actively enabled for this user/context.

### DEFAULT
The flag is disabled or doesn't match targeting rules.

**Examples:**
- Flag is disabled in this environment
- User doesn't match targeting criteria
- Percentage rollout didn't select this user
- Constraints don't match

**What it means**: The flag returns the default value (not enabled).

### ERROR
Evaluation failed due to an error.

**Examples:**
- Flag doesn't exist in Unleash
- Unleash server is unavailable
- Invalid flag configuration
- Network error

**What it means**: Something went wrong, so the default value is returned as a safe fallback.

## Real-World Examples

### Example 1: Simple Feature Gate

**Scenario**: Check if new UI should be shown to a user

```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "default_value": false,
  "environment": "production"
}
```

**Result**: `true` if user should see new UI, `false` otherwise

### Example 2: Gradual Rollout

**Scenario**: Roll out feature to 25% of users

```json
{
  "flag_name": "new-checkout-flow",
  "user_id": "user-456",
  "default_value": false,
  "environment": "production"
}
```

**Result**: `true` for ~25% of users (based on user ID hash), `false` for others

### Example 3: Region-Based Feature

**Scenario**: Enable feature only for US West region

```json
{
  "flag_name": "region-specific-feature",
  "user_id": "user-789",
  "context": {"region": "us-west"},
  "default_value": false,
  "environment": "production"
}
```

**Result**: `true` if region is "us-west", `false` otherwise

### Example 4: Premium User Feature

**Scenario**: Enable feature only for premium users

```json
{
  "flag_name": "premium-features",
  "user_id": "user-101",
  "context": {"plan": "premium", "subscription_active": true},
  "default_value": false,
  "environment": "production"
}
```

**Result**: `true` if user has premium plan and active subscription

### Example 5: A/B Testing Variants

**Scenario**: Test different button colors

```json
{
  "flag_name": "button-color",
  "user_id": "user-202",
  "context": {},
  "default_value": "blue",
  "environment": "production"
}
```

**Result**: `"blue"`, `"red"`, or `"green"` depending on variant assignment

## Best Practices

1. **Always provide a sensible default_value**
   - Use the "safe" value (usually `false` for boolean flags)
   - This ensures your app works even if Unleash is down

2. **Include user_id for consistent evaluation**
   - Same user should get same result
   - Important for gradual rollouts

3. **Use context for advanced targeting**
   - Pass relevant attributes (region, plan, etc.)
   - Enables powerful targeting strategies

4. **Use bulk evaluation when possible**
   - More efficient than multiple requests
   - All flags evaluated with same context

5. **Handle ERROR reason gracefully**
   - Log errors for monitoring
   - Fall back to default value
   - Don't break user experience

6. **Cache evaluation results**
   - The system caches automatically in Redis
   - Don't re-evaluate the same flag multiple times in one request

## Common Mistakes

1. **Wrong environment name**
   - Ensure it matches Unleash environment exactly
   - Case-sensitive: "development" ≠ "Development"

2. **Missing user_id for user targeting**
   - Strategies that target users won't work without user_id
   - Always include user_id if using user-based strategies

3. **Wrong default_value type**
   - Boolean flag needs boolean default_value
   - String flag needs string default_value
   - Type mismatch causes errors

4. **Not handling ERROR reason**
   - Always check the reason field
   - Handle errors appropriately in your code

5. **Evaluating too frequently**
   - Use bulk evaluation for multiple flags
   - Cache results when possible
   - Don't evaluate the same flag multiple times

