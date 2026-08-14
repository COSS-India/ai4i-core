# 1. Manage API Keys

| | |
| --- | --- |
| Objective | Update or revoke an existing API key. |
| Role | Institution Admin |
| Prerequisites | You have at least one existing API key. |

**Step 1** Click "API Key Management," then click "Manage API Keys" to view your institution's application keys.

![Your API Keys, showing status, creation, and expiry for each](../assets/manage-api-keys-01-your-keys.png)

**Step 2** To rename a key or change its permissions, click the edit icon.

![Opening Update Key for an existing API key](../assets/manage-api-keys-02-open-update.png)

**Step 3** Update the key name or permissions, then click "Update." A key's expiry cannot be changed here.

![Updating the key name and permissions](../assets/manage-api-keys-03-update-key.png)

**Step 4** To revoke a key, click the revoke icon.

![Opening Revoke Key for an existing API key](../assets/manage-api-keys-04-open-revoke.png)

**Step 5** Confirm the revocation.

![Confirming the key revocation](../assets/manage-api-keys-05-confirm-revoke.png)

{% hint style="danger" %}
**IMPORTANT**

Revoking a key is permanent — revoked keys cannot be reactivated. If the application still needs access, you'll need to create a new key and update the application with it.
{% endhint %}

| | |
| --- | --- |
| Outcome | The key is updated, or revoked and immediately stops authenticating requests. |
| Next | Proceed to [Manage Institution Users](manage-users.md). |
