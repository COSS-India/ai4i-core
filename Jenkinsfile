pipeline {
  agent any

  parameters {
    string(name: 'BRANCH_NAME', defaultValue: 'master', description: 'Git branch to clone and build')

    choice(
      name: 'SERVICE_NAME',
      choices: """
alerting-service
api-gateway-service
asr-service
auth-service
config-service
dashboard-service
metrics-service
nmt-service
pipeline-service
telemetry-service
tts-service
""",
      description: 'Service directory under services/'
    )

    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true, description: 'Delete workspace before checkout')
  }

  environment {
    GIT_REPO = 'https://github.com/COSS-India/ai4i-core.git'
    AWS_REGION = 'ap-south-1'        // change if needed
    AWS_ACCOUNT = '662074586476'     // change if needed
    // Note: using existing Jenkins credential id 'aws-creds' (username/password)
  }

  stages {
    stage('Prepare') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) {
            deleteDir()
          }
        }
      }
    }

    stage('Checkout') {
      steps {
        echo "Checking out '${params.BRANCH_NAME}' from ${env.GIT_REPO}"
        checkout([$class: 'GitSCM',
          branches: [[name: "*/${params.BRANCH_NAME}"]],
          userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
        ])
      }
    }

    stage('Validate Service') {
      steps {
        script {
          def path = "services/${params.SERVICE_NAME}"
          echo "Selected service path: ${path}"
          if (!fileExists(path)) {
            error "Service '${params.SERVICE_NAME}' not found at ${path}"
          }
        }
      }
    }

    stage('Build Service') {
      steps {
        dir("services/${params.SERVICE_NAME}") {
          echo "Building service: ${params.SERVICE_NAME}"
          sh '''
            set -eux

            if [ -f "requirements.txt" ]; then
              echo "[python] Detected Python project"
              python3 -m venv venv
              . venv/bin/activate
              pip install -r requirements.txt
              echo "Python dependencies installed."
            fi

            if [ -f "Dockerfile" ]; then
              echo "[docker] Detected Dockerfile"
              IMAGE_NAME="$SERVICE_NAME:build-$BUILD_NUMBER"
              echo "Building Docker image: $IMAGE_NAME"
              docker build -t "$IMAGE_NAME" .
              echo "Built $IMAGE_NAME"
              exit 0
            fi

            echo "No build files found — skipping build."
            exit 0
          '''
        }
      }
    }

    stage('Tag & Push to ECR') {
      when {
        expression { fileExists("services/${params.SERVICE_NAME}/Dockerfile") }
      }
      steps {
        // Bind existing aws credentials (username/password) -> AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
        withCredentials([usernamePassword(credentialsId: 'aws-creds', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
          dir("services/${params.SERVICE_NAME}") {
            sh '''
              set -eux

              SERVICE="${SERVICE_NAME}"
              BUILT_TAG="build-${BUILD_NUMBER}"
              BUILT_IMAGE="${SERVICE}:${BUILT_TAG}"

              AWS_REGION="${AWS_REGION:-ap-south-1}"
              AWS_ACCOUNT="${AWS_ACCOUNT:-662074586476}"
              ECR_REGISTRY="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

              # ECR mapping (adjust as needed)
              declare -A ECR_REPO
              ECR_REPO[api-gateway-service]="${ECR_REGISTRY}/ai4voice/api-gateway-service"
              ECR_REPO[auth-service]="${ECR_REGISTRY}/ai4voice/auth-service"
              ECR_REPO[asr-service]="${ECR_REGISTRY}/ai4voice/asr-service"
              ECR_REPO[tts-service]="${ECR_REGISTRY}/ai4voice/tts-service"
              ECR_REPO[nmt-service]="${ECR_REGISTRY}/ai4voice/nmt-service"
              ECR_REPO[llm-service]="${ECR_REGISTRY}/ai4voice/llm-service"
              ECR_REPO[pipeline-service]="${ECR_REGISTRY}/ai4voice/pipeline-service"
              ECR_REPO[simple-ui-frontend]="${ECR_REGISTRY}/simple-ui-frontend"

              TARGET_REPO="${ECR_REPO[${SERVICE}]}"
              if [ -z "${TARGET_REPO}" ]; then
                echo "ERROR: No ECR mapping for service ${SERVICE}"
                exit 1
              fi

              # Timestamp in IST ddmmyyyy-HHMMSS-IST
              TIMESTAMP=$(TZ="Asia/Kolkata" date +'%d%m%Y-%H%M%S')
              TARGET_TAG="${TIMESTAMP}-IST"
              ECR_IMAGE="${TARGET_REPO}:${TARGET_TAG}"

              echo "Built image expected: ${BUILT_IMAGE}"
              if ! docker image inspect "${BUILT_IMAGE}" >/dev/null 2>&1; then
                echo "ERROR: Built image ${BUILT_IMAGE} not found. Aborting."
                exit 1
              fi

              # export aws creds for aws CLI
              export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
              export AWS_DEFAULT_REGION="${AWS_REGION}"

              echo "Logging into ECR registry ${ECR_REGISTRY}"
              aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

              # create repo if missing (repo name is basename)
              REPO_NAME=$(basename "${TARGET_REPO}")
              if ! aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
                echo "Creating ECR repo ${REPO_NAME}"
                aws ecr create-repository --repository-name "${REPO_NAME}" --region "${AWS_REGION}" >/dev/null
              else
                echo "ECR repo ${REPO_NAME} exists"
              fi

              echo "Tagging ${BUILT_IMAGE} -> ${ECR_IMAGE}"
              docker tag "${BUILT_IMAGE}" "${ECR_IMAGE}"

              echo "Pushing ${ECR_IMAGE}"
              docker push "${ECR_IMAGE}"

              echo "Pushed ${ECR_IMAGE}"
            '''
          }
        }
      }
      post {
        success {
          echo "✅ Pushed ${params.SERVICE_NAME} to ECR with timestamp tag."
        }
        failure {
          echo "❌ Push to ECR failed for ${params.SERVICE_NAME}"
        }
      }
    }
  }

  post {
    success {
      echo "✅ Build ok: branch='${params.BRANCH_NAME}', service='${params.SERVICE_NAME}'"
    }
    failure {
      echo "❌ Build failed: branch='${params.BRANCH_NAME}', service='${params.SERVICE_NAME}'"
    }
  }
}
