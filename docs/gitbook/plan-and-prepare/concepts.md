# 3. Key Terms

The following terms are used throughout this guide.

| Term | Definition |
| --- | --- |
| **Adopter** | The organization that deploys and governs an AI Switch instance. It onboards Institutions and hosts the LLM Service they consume. |
| **Institution** | Your organization: onboarded by the Adopter to consume the LLM Service it hosts. It is allocated a Tier and Budget, which it extends to the Applications it registers. |
| **Application** | A solution built by your institution that consumes the LLM Service through an API Key. Your institution can register one or more Applications. |
| **API Key** | A credential your institution creates, used to authenticate an Application's requests to an LLM Service. |
| **Service** | A registered model version made available for consumption through a specific endpoint — the machine or GPU where that model version is hosted. The same model version hosted on a different machine is a distinct Service. |
| **Tier** | Defines the maximum consumption ceilings for requests and LLM Service usage. All Quotas and Rate Limits mapped to a Tier must stay within these ceilings. A Tier is assigned to your institution. |
| **Budget** | A monetary spend cap set for your institution, expressed in the currency defined on its assigned Tier. It governs how much your institution can spend in a billing period, regardless of how much Quota remains. |
| **Quota** | The maximum amount of LLM Service your institution is allowed to consume within a specified time period. Quotas help ensure fair usage of shared platform resources, prevent excessive consumption, and support controlled service entitlements. They reset automatically at the end of the configured time window. |
| **Rate Limit** | The maximum speed at which requests can be sent within a given period. Unlike Quotas, which control total monthly volume, Rate Limits control how fast your institution or an API Key can consume LLM Service within an hour — protecting platform stability and ensuring fair access for all institutions. |
| **Metering** | The recording of your institution's usage, including a rollup across all its Applications, tracked against its assigned Budget. |
