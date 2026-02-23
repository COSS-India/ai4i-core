## Feature Flags Configuration
The UI is integrated with feature flags to conditionally show/hide service features. If you want to control the visibility of services in the UI, you can create the following feature flags in Unleash:


The following feature flags are used by the frontend to control service visibility:

- **`asr-enabled`** - Controls visibility of ASR (Automatic Speech Recognition) service
- **`tts-enabled`** - Controls visibility of TTS (Text-to-Speech) service
- **`nmt-enabled`** - Controls visibility of NMT (Neural Machine Translation) service
- **`llm-enabled`** - Controls visibility of LLM (Large Language Model) service
- **`pipeline-enabled`** - Controls visibility of Pipeline service

### How to Create Feature Flags in Unleash

1. **Access Unleash UI**: 
   - **Local Development**: Navigate to http://localhost:4242/feature-flags
   - **Default Username**: `admin`
   - **Default Password**: `unleash4all`

2. **Create a Feature Flag**:
   - Click "Create feature toggle"
   - Enter the flag name (e.g., `asr-enabled`)
   - Add a description (optional)
   - Select flag type: `release` (recommended)
   - Click "Create feature toggle"

3. **Configure Environment Settings**:
   - Enable or disable the flag for each environment (development, staging, production)
   - Add targeting strategies if needed (gradual rollout, user targeting, etc.)

4. **Repeat** for each flag you want to configure

### Behavior

- **If a flag exists and is enabled**: The corresponding service will be visible in the UI
- **If a flag exists and is disabled**: The corresponding service will be hidden in the UI
- **If a flag doesn't exist**: The service will be visible by default

**Note**: Feature flags are completely optional. If you don't create them, all services will be visible in the UI by default. Only create flags if you need to control service visibility.

