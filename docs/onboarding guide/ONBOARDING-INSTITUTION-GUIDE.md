# Institution Admin Guide

Sign in, give your applications access to models, and track usage · Version 1.0


### Part I — Plan & Prepare

*Understand your role as Institution Admin and gather what you need before you begin.*


## 1. Introduction


### About AI4I Orchestrate

AI4I Orchestrate provides a single platform for secure, controlled use of hosted AI models at scale. Organizations can offer open-source and other hosted models to institutions and their applications while retaining control over access and the underlying AI infrastructure.

It brings access controls, usage tracking, and operational monitoring together, so organizations can manage model use, measure consumption, and maintain accountability across institutions and applications.


### Purpose of this Guide

Follow Part II to set up access for your institution:

- Activate your account and sign in.
- Onboard your applications and create API keys to give them access to models.
- Onboard your institution’s users.
After setup, use the remaining parts for ongoing tasks:

- **Part III — Track Budget & Usage:** review your institution’s budget and usage.
- **Part IV — Manage & Maintain:** manage applications, API keys, users, and your account.

### Intended Audience

This guide is for the Institution Admin responsible for managing the institution’s access to AI4I Orchestrate. It covers application and user onboarding, access to models through API keys, and budget and usage tracking.


## 2. Before You Begin


### Roles & Responsibilities

**Adopter Admin —** onboards your institution and assigns its tier and budget. These define the usage limits and spending cap within which you manage your institution.

**Institution Admin —** manages your institution’s applications, creates API keys for access to models, onboards institution users, and tracks budget and usage against the assigned tier.

**Institution User —** is onboarded by the Institution Admin and can sign in to explore available models in the portal.


### Information to Keep Ready

Keep the following information ready:

- Access to the email address shared with your Adopter Admin. Your account activation email will be sent there.
- Each application’s name, the share of your institution’s budget to allocate to it, and the permissions and expiry needed for its API key.
- The name and email address of each institution user you want to add. Phone numbers are optional.

### Readiness Checklist

Use this checklist to track your readiness for setup. Your progress is saved automatically.

- [ ] You can open the AI4I Orchestrate link shared by your Adopter Admin in a supported browser.

- [ ] You have activated your account and set your password.

- [ ] Your institution has been assigned a tier and budget.

- [ ] You have identified the applications that need access and the share of your institution’s budget to allocate to each.

- [ ] You know the name, permissions, budget allocation, and expiry for each application’s API key.

- [ ] You have each institution user’s name and email address, and their phone number if available.


## 3. Key Terms

The following terms are used throughout this guide.

| Term | Definition |
| --- | --- |
| Adopter | The organization that deploys and governs an AI4I Orchestrate instance. It hosts models and onboards institutions that use them. |
| Institution | Your organization, onboarded by the adopter to use its hosted models. It receives a tier and budget and allocates a share of that budget to its onboarded applications. |
| Application | An application onboarded under your institution to access hosted models. It receives a share of your institution’s budget, which can then be allocated to its API keys. |
| API Key | A credential that an application uses to authenticate and route requests to hosted models. Each key belongs to one onboarded application and receives a share of that application’s budget. |
| Service | A model made available on a particular machine or GPU. The same model hosted on another machine is a separate service. |
| Tier | A plan assigned to your institution that defines the quota and rate limit for each model task type. It sets how much your institution can use and how quickly it can send requests. |
| Budget | A monetary spending limit assigned to your institution along with its tier. It limits total spend even when quota remains. |
| Quota | The maximum amount of model usage your institution can consume each month, set for each model task type on its assigned tier.Quotas support fair access to shared resources. They reset automatically at the start of each month. |
| Rate Limit | The maximum number of requests your institution can send per minute, as set on its assigned tier.Quota limits total monthly usage. Rate limits control how quickly requests are sent, helping protect platform stability and maintain fair access. |
| Metering | The recording of your institution’s model usage, including the combined usage of its applications, tracked against its assigned budget. |


### Part II — Onboard & Provision

*Sign in, give your applications access to models, and onboard your institution’s users.*


## 4. Institution Creation

- **Objective:** Understand how your Adopter Admin sets up your institution before you sign in.

- **Role:** Adopter Admin

- **Prerequisites:** None. Your Adopter Admin completes this setup before you sign in.

Share the following information with your Adopter Admin. They use it to create your institution on AI4I Orchestrate and assign its tier and budget.


### Information to Share with Your Adopter Admin

- Your institution’s name.
- The name and email address of the person who will act as Institution Admin.
- Your expected usage and spend, so the Adopter Admin can assign a suitable tier and budget.
- **Outcome:** Your institution is created with an assigned tier and budget. These set the usage limits and spending cap for your institution and its applications.

- **Next:** You receive an activation email when your Adopter Admin onboards your institution. Continue to Activate Your Account.


## 5. Activate Your Account

- **Objective:** Verify your email and set your password so you can sign in to AI4I Orchestrate.

- **Role:** Institution Admin

- **Prerequisites:**
  - Your Adopter Admin has onboarded your institution.
  - You can access the email address shared with your Adopter Admin.

- **Step 1** Open the activation email from AI4I Orchestrate to activate your institution and your Institution Admin account.


![The Set Your Password activation email.](images/onboarding-institution/image_1.jpg)

*The Set Your Password activation email.*

- **Step 2** Click **Set Your Password** in the email.


![Opening the Set Your Password link.](images/onboarding-institution/image_2.jpg)

*Opening the Set Your Password link.*

- **Step 3** Enter a password that meets the requirements shown. Enter it again in **Confirm Password**, then click **Set Password**.


![Setting a new password and confirming it.](images/onboarding-institution/image_3.jpg)

*Setting a new password and confirming it.*

- **Step 4** Once your password is set, click **Go to sign in**.


![Password set successfully, ready to sign in.](images/onboarding-institution/image_4.jpg)

*Password set successfully, ready to sign in.*

- **Step 5** Check the confirmation email sent after you set your password. It includes your institution name and sign-in email address; keep it for reference.


![The confirmation email sent after your password is set.](images/onboarding-institution/image_5.png)

*The confirmation email sent after your password is set.*

- **Outcome:** Your account is activated and your password is set.

- **Next:** Continue to Signing In.


## 6. Signing In

- **Objective:** Sign in to AI4I Orchestrate using your email and the password you set.

- **Role:** Institution Admin

- **Prerequisites:**
  - Your institution account has been activated.
  - You have set your password.

- **Step 1** Open the AI4I Orchestrate link shared by your Adopter Admin. Enter your email address and password, then click **Sign In**.


![Signing in to AI4I Orchestrate.](images/onboarding-institution/image_6.jpg)

*Signing in to AI4I Orchestrate.*

- **Step 2** After you sign in, the **Usage Dashboard** opens. This is your institution’s landing page.


![The Usage Dashboard, your institution’s landing page.](images/onboarding-institution/image_7.jpg)

*The Usage Dashboard, your institution’s landing page.*

- **Outcome:** You are signed in and viewing your institution’s Usage Dashboard.

- **Next:** Continue to Onboard an Application.


## 7. Onboard an Application

- **Objective:** Onboard an application under your institution and allocate a share of the institution’s budget to it.

- **Role:** Institution Admin

- **Prerequisites:**
  - Your institution has an assigned tier and budget.
  - You know the application’s name. You can also provide a description, domain, and budget allocation percentage.

- **Step 1** In the left navigation, click **Institution Management**.


![Institution Management in the left navigation.](images/onboarding-institution/image_8.jpg)

*Institution Management in the left navigation.*

- **Step 2** Click the **Applications** tab to see your institution’s applications and budget allocation.


![The Applications tab, showing your institution’s applications and budget allocation.](images/onboarding-institution/image_9.jpg)

*The Applications tab, showing your institution’s applications and budget allocation.*

- **Step 3** Click **Create Application**.


![The Create Application button.](images/onboarding-institution/image_10.jpg)

*The Create Application button.*

- **Step 4** Enter the **Application name**. The name must be unique within your institution. Add a **Description**, **Domain**, and **Budget allocation** if needed, then click **Create Application**.


![The application details and optional budget allocation.](images/onboarding-institution/image_11.jpg)

*The application details and optional budget allocation.*

- **Outcome:** The application is onboarded under your institution, with a budget allocation if you entered one.

- **Next:** Continue to Create an API Key.


## 8. Create an API Key

- **Objective:** Create an API key that gives an onboarded application access to models.

- **Role:** Institution Admin

- **Prerequisites:**
  - The application is already onboarded.
  - You know the API key’s required permissions, budget allocation, and expiry.

- **Step 1** In the left navigation, click **API Key Management**.


![API Key Management in the left navigation.](images/onboarding-institution/image_12.jpg)

*API Key Management in the left navigation.*

- **Step 2** Click **Create API Key**.


![The Create API Key button.](images/onboarding-institution/image_13.jpg)

*The Create API Key button.*

- **Step 3** Enter a **Key Name**, select the **Application**, and choose the **Permissions** the key needs. Enter the **Budget Allocation** as a percentage of the application’s budget, set the **Expiry (Days)** between 1 and 365, then click **Create API Key**.


![The key name, application, permissions, budget allocation, and expiry.](images/onboarding-institution/image_14.jpg)

*The key name, application, permissions, budget allocation, and expiry.*

- **Step 4** Click **Copy** and store the new API key securely before closing the panel.


![The API key created, shown once with the Copy option.](images/onboarding-institution/image_15.jpg)

*The API key created, shown once with the Copy option.*

- **Outcome:** The application has an API key with the permissions, budget allocation, and expiry you set.

- **Next:** Continue to Onboard Institution Users.


## 9. Onboard Institution Users

- **Objective:** Add users to your institution so they can sign in and test available models in Try It Now.

- **Role:** Institution Admin

- **Prerequisites:** You have the user’s name and email address. A phone number is optional.

- **Step 1** In the left navigation, click **Institution Management**.


![Institution Management in the left navigation.](images/onboarding-institution/image_16.jpg)

*Institution Management in the left navigation.*

- **Step 2** Click the **Users** tab, then click **Add User**.


![The Users tab and Add User button.](images/onboarding-institution/image_17.jpg)

*The Users tab and Add User button.*

- **Step 3** Enter the user’s **Email** and **Full Name**, and select their **Role**. Add a **Phone Number** if available. Select the checkbox to agree to the Terms of Service and Privacy Policy, then click **Add User**.


![The new user’s details, role, and policy agreement.](images/onboarding-institution/image_18.jpg)

*The new user’s details, role, and policy agreement.*

- **Step 4** The user appears with the status **Pending Activation**. They receive an activation email to verify their email address and set their password.


![The new user, shown with Pending Activation status.](images/onboarding-institution/image_19.jpg)

*The new user, shown with Pending Activation status.*

- **Outcome:** The user is added with the selected role. Their account becomes active after they verify their email address and set their password through the activation email.

- **Next:** Continue to Part III to track your institution’s budget and usage.


### Part III — Track Budget & Usage

*Track your institution’s budget and usage against its assigned tier.*


## 10. Usage Dashboard

- **Objective:** Track your institution’s usage and spend against its assigned tier and budget, including usage by model and application.

- **Role:** Institution Admin

- **Prerequisites:** Your institution has at least one application in use.

- **Step 1** In the left navigation, click **Usage Dashboard**. Use the date range options, such as **Today**, **Yesterday**, **Last 7 days**, or a custom range, to set the period you want to review.


![Usage Dashboard in the left navigation.](images/onboarding-institution/image_20.jpg)

*Usage Dashboard in the left navigation.*

- **Step 2** Click the **Institution** tab to review your institution’s total, successful, and failed requests, its average requests per second (RPS), and request volume over the selected period.


![The Institution tab.](images/onboarding-institution/image_21.jpg)

*The Institution tab.*

- **Step 3** Click the **Model** tab to review total and active models, the overall success rate, and the most used model. **Model Consumption** ranks models by request volume.


![The Model tab and Model Consumption.](images/onboarding-institution/image_22.jpg)

*The Model tab and Model Consumption.*

- **Step 4** Scroll down to **Model Consumption Drill Down** to see total requests, native consumption, and success and failure rates for each model and service. Expand a row to see input and output tokens. Use the **Task Type** filter to narrow the results.


![Usage by model and service in Model Consumption Drill Down.](images/onboarding-institution/image_23.jpg)

*Usage by model and service in Model Consumption Drill Down.*

- **Step 5** Click the **Budget** tab to review how much of your institution’s budget is used and its effective dates, your spend in the selected period, and usage by task type against the quota of each assigned tier.


![The Budget tab for your institution.](images/onboarding-institution/image_24.jpg)

*The Budget tab for your institution.*

- **Step 6** Click the **Applications** tab to compare each application’s allocated budget, spend, and remaining budget.


![Budget allocation and spend for each application in the Applications tab.](images/onboarding-institution/image_25.jpg)

*Budget allocation and spend for each application in the Applications tab.*

- **Outcome:** You can review your institution’s overall usage, model performance, budget consumption, and application spend.

- **Next:** Continue to Part IV for day-to-day account and access management.


### Part IV — Manage & Maintain

*Day-to-day account, access, and testing tasks you will return to after initial setup.*


## 11. Manage Applications

- **Objective:** View your institution’s applications and adjust their budget allocations.

- **Role:** Institution Admin

- **Prerequisites:** Your institution has at least one onboarded application.

- **Step 1** In the left navigation, click **Institution Management**.


![Institution Management in the left navigation.](images/onboarding-institution/image_26.jpg)

*Institution Management in the left navigation.*

- **Step 2** Click the **Applications** tab to view your applications and their budget allocations.


![The Applications tab and institution budget overview.](images/onboarding-institution/image_27.jpg)

*The Applications tab and institution budget overview.*

- **Step 3** Click the **Edit budget** sliders icon next to the application you want to update.


![The Edit budget action for an application.](images/onboarding-institution/image_28.jpg)

*The Edit budget action for an application.*

- **Step 4** Review the **Allocated**, **Consumed**, and **Remaining (Institution)** amounts. Enter the new percentage within the **Allowed Range**, then click **Save Changes**. The allocation cannot be reduced below what the application has already consumed.


![Updating an application’s budget allocation and saving the change.](images/onboarding-institution/image_29.jpg)

*Updating an application’s budget allocation and saving the change.*

- **Step 5** To view an application’s details, click the application in the list. The details show its description, domain, status, budget allocation, and active API keys. Click **Close** when you are done.


![Application details, showing its budget allocation and amount.](images/onboarding-institution/image_30.jpg)

*Application details, showing its budget allocation and amount.*

- **Outcome:** You can view each application’s budget and save changes to its allocation.

- **Next:** Continue to Manage API Keys.


## 12. Manage API Keys

- **Objective:** View your applications’ API keys, adjust their budgets, rename them or change their permissions, rotate them, or revoke access.

- **Role:** Institution Admin

- **Prerequisites:** You have at least one existing API key.

- **Step 1** In the left navigation, click **API Key Management**. Use the search box and the application, permission, and status filters to find a key.


![API Key Management in the left navigation.](images/onboarding-institution/image_31.jpg)

*API Key Management in the left navigation.*

- **Step 2** To change a key’s budget, click the **Edit Budget** icon next to it.


![The Edit Budget action for an API key.](images/onboarding-institution/image_32.jpg)

*The Edit Budget action for an API key.*

- **Step 3** Review the **Allocated**, **Consumed**, and **Remaining** amounts. Enter the new allocation as a percentage of the application’s budget, within the **Allowed Range**, then click **Save Changes**.


![Updating a key’s budget allocation and saving the change.](images/onboarding-institution/image_33.jpg)

*Updating a key’s budget allocation and saving the change.*

- **Step 4** To rename a key or change its permissions, click the **Update key** icon next to it.


![The Update key action for an API key.](images/onboarding-institution/image_34.jpg)

*The Update key action for an API key.*

- **Step 5** Update the **Key Name** or **Permissions**, then click **Save Changes**. You cannot change the key’s application, budget, or expiry in this panel.


![Updating the key name and permissions.](images/onboarding-institution/image_35.jpg)

*Updating the key name and permissions.*

- **Step 6** To replace a key with a new one, click the **Rotate key** icon next to it.


![The Rotate key action for an API key.](images/onboarding-institution/image_36.jpg)

*The Rotate key action for an API key.*

- **Step 7** Select a **Grace period** of 1, 3, 7, or 14 days, then click **Rotate API Key**.


![Selecting the grace period and rotating the key.](images/onboarding-institution/image_37.jpg)

*Selecting the grace period and rotating the key.*

- **Step 8** Click **Copy** and store the new key securely, then click **I’ve saved the new key**.


![The rotated key, shown once with the Copy option.](images/onboarding-institution/image_38.jpg)

*The rotated key, shown once with the Copy option.*

- **Step 9** To stop a key from granting access, click the **Revoke key** icon next to it.


![The Revoke key action for an API key.](images/onboarding-institution/image_39.jpg)

*The Revoke key action for an API key.*

- **Step 10** In the confirmation dialog, review the total allocated, already consumed, and unused budget that returns to the application, then click **Revoke API Key**.


![Confirming the key revocation.](images/onboarding-institution/image_40.jpg)

*Confirming the key revocation.*

- **Outcome:** The selected key’s budget, name, or permissions are updated, or the key is rotated. If you revoked the key, it immediately stops authenticating requests.

- **Next:** Continue to Manage Institution Users.


## 13. Manage Institution Users

- **Objective:** Update a user’s details or role, suspend or restore their access, or delete their account.

- **Role:** Institution Admin

- **Prerequisites:** You have at least one existing institution user.

- **Step 1** In the left navigation, click **Institution Management**.


![Institution Management in the left navigation.](images/onboarding-institution/image_41.jpg)

*Institution Management in the left navigation.*

- **Step 2** Click the **Users** tab. Use the search box and the **Status** and **Role** filters to find a user.


![The Users tab, showing your institution’s users.](images/onboarding-institution/image_42.jpg)

*The Users tab, showing your institution’s users.*

- **Step 3** To update a user, click the edit icon next to them.


![The edit action for a user.](images/onboarding-institution/image_43.jpg)

*The edit action for a user.*

- **Step 4** Update the **Username**, **Full Name**, **Role**, or **Phone Number**, then click **Save Changes**. The email address cannot be changed.


![Updating a user’s details and role.](images/onboarding-institution/image_44.jpg)

*Updating a user’s details and role.*

- **Step 5** To suspend a user, click the dropdown arrow next to their account, then click **Suspend**.


![The Suspend action for a user.](images/onboarding-institution/image_45.jpg)

*The Suspend action for a user.*

- **Step 6** In the **Change user status** dialog, check that the new status is **Suspended**, then click **Update**.


![Confirming the user’s suspension.](images/onboarding-institution/image_46.jpg)

*Confirming the user’s suspension.*

- **Step 7** To restore a suspended user’s access, click the dropdown arrow next to their account, then click **Activate**.


![The Activate action for a suspended user.](images/onboarding-institution/image_47.jpg)

*The Activate action for a suspended user.*

- **Step 8** In the **Change user status** dialog, check that the new status is **Active**, then click **Update**.


![Confirming the user’s activation.](images/onboarding-institution/image_48.jpg)

*Confirming the user’s activation.*

- **Step 9** To delete a user, click the dropdown arrow next to their account, then click the delete icon.


![The delete action for a user.](images/onboarding-institution/image_49.jpg)

*The delete action for a user.*

- **Step 10** In the **Delete user** dialog, click **Delete**.


![Confirming the user’s deletion.](images/onboarding-institution/image_50.jpg)

*Confirming the user’s deletion.*

- **Outcome:** The user’s details or role are updated, or their account is suspended, activated, or deleted, depending on the action you completed.

- **Next:** Continue to Try It Now.


## 14. Try It Now

- **Objective:** Explore and test an available model directly in the portal.

- **Role:** Institution Admin or Institution User

- **Prerequisites:** At least one service is available to your institution’s tier.

- **Step 1** Open **Explore** and click **Try it now** on a model task type card. The following example uses **Large Language Model (LLM)**.


![The Explore page, showing every model task type available to test.](images/onboarding-institution/image_51.jpg)

*The Explore page, showing every model task type available to test.*

- **Step 2** Select an **LLM Service**, then choose the **Source Language** and **Target Language**.


![Selecting the LLM service, source language, and target language.](images/onboarding-institution/image_52.jpg)

*Selecting the LLM service, source language, and target language.*

- **Step 3** Enter your text in **Source Text**, then click **Translate**.


![Entering source text and clicking Translate.](images/onboarding-institution/image_53.jpg)

*Entering source text and clicking Translate.*

- **Outcome:** You have submitted text to the selected model and can review its response in the portal.

- **Next:** Continue to View Available Models.


## 15. View Available Models

- **Objective:** View the models registered on the platform by your Adopter Admin.

- **Role:** Institution Admin

- **Prerequisites:** None.

- **Step 1** In the left navigation, click **Model Management**.


![Model Management in the left navigation.](images/onboarding-institution/image_54.jpg)

*Model Management in the left navigation.*

- **Step 2** Review the models registered on the platform, including each model’s name, version, status, task type, creation date, and number of services. Use the search box and the **Status** and **Task type** filters to find a model. This view is read-only.


![The registered models in Model Management.](images/onboarding-institution/image_55.jpg)

*The registered models in Model Management.*

- **Outcome:** You can view the models currently registered on the platform.

- **Next:** Continue to Logs Dashboard.


## 16. Logs Dashboard

- **Objective:** Review your institution’s request logs and trace details.

- **Role:** Institution Admin

- **Prerequisites:** At least one request has been made using your institution’s API keys.

- **Step 1** In the left navigation, click **Logs Dashboard**.


![Logs Dashboard in the left navigation.](images/onboarding-institution/image_56.jpg)

*Logs Dashboard in the left navigation.*

- **Step 2** Review the total, successful, and failed requests. To find a request, use **Search**, **Task Type**, **Status**, **Service**, **Status Code**, **End User**, **Metadata**, or the **Start Time** and **End Time**, then click **Search**. Click a request to open its trace details.


![Request totals, filters, and the request list.](images/onboarding-institution/image_57.jpg)

*Request totals, filters, and the request list.*

- **Step 3** Review the trace details, including the Trace ID, service, institution, environment, and each span’s timestamp, duration, status, and attributes.


![Trace details, showing the request, model, and inference spans.](images/onboarding-institution/image_58.jpg)

*Trace details, showing the request, model, and inference spans.*

- **Outcome:** You can trace your institution’s requests and review their timing when investigating an application issue.

- **Next:** Continue to Manage Your Profile.


## 17. Manage Your Profile

- **Objective:** Update your profile, change your password, sign out, or delete your own account.

- **Role:** Institution Admin

- **Prerequisites:** None.

- **Step 1** Open the menu in the top-right corner, then click **Profile**.


![The Profile option in the top-right menu.](images/onboarding-institution/image_59.jpg)

*The Profile option in the top-right menu.*

- **Step 2** Review your details on the **User Details** tab. Click **Edit** to change the editable fields. Your username and email address cannot be changed.


![Your user details on the Profile page.](images/onboarding-institution/image_60.jpg)

*Your user details on the Profile page.*

- **Step 3** Click the **Change Password** tab. Enter your **Current Password** and **New Password**, then enter the new password again in **Confirm New Password**. Click **Update Password**.


![A new password meeting all requirements, ready to update.](images/onboarding-institution/image_61.jpg)

*A new password meeting all requirements, ready to update.*

- **Step 4** To sign out, open the menu in the top-right corner and click **Sign out**. You return to the sign-in page.


![The Sign out option in the top-right menu.](images/onboarding-institution/image_62.jpg)

*The Sign out option in the top-right menu.*

- **Step 5** To delete your account, open the **User Details** tab, scroll to **Delete Account**, and click **Delete Account**.


![The Delete Account section of your profile.](images/onboarding-institution/image_63.jpg)

*The Delete Account section of your profile.*

- **Step 6** Read the confirmation, select each acknowledgement checkbox, then click **Delete Account**.


![Confirming the account deletion.](images/onboarding-institution/image_64.jpg)

*Confirming the account deletion.*

- **Outcome:** Your profile or password is updated, you are signed out, or your account is deleted, depending on the action you completed.
