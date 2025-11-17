pipeline {
  agent any

  environment {
    DOCKER_BUILDKIT = "1"
    GIT_REPO        = 'https://github.com/COSS-India/ai4i-core.git'
    AWS_REGION      = 'ap-south-1'
    AWS_ACCOUNT     = '662074586476'
  }

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

  stages {

    /* -----------------------------------------------------------
     *  PREPARE WORKSPACE
     * -----------------------------------------------------------
     */
    stage('Prepare Workspace') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) {
            echo "Cleaning workspace..."
            deleteDir()
          }
        }
      }
    }

    /* -----------------------------------------------------------
     *  CHECKOUT SOURCE CODE
     * -----------------------------------------------------------
     */
    stage('Checkout') {
      steps {
        echo "Cloning ${params.BRANCH_NAME}..."
        checkout([$class: 'GitSCM',
          branches: [[name: "*/${params.BRANCH_NAME}"]],
          userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
        ])
      }
    }

    /* -----------------------------------------------------------
     *  VALIDATE SERVICE DIRECTORY
     * -----------------------------------------------------------
     */
    stage('Validate Service') {
      steps {
        script {
          def path = "services/${params.SERVICE_NAME}"
          if (!fileExists(path)) {
            error "❌ Service '${params.SERVICE_NAME}' not found at ${path}"
          }
          echo "Service found: ${path}"
        }
      }
    }

    /* -----------------------------------------------------------
     *  DOCKER BUILD WITH FULL CACHE SUPPORT
     * -----------------------------------------------------------
     */
    stage('Docker Build (Cached)') {
      steps {
        dir("services/${params.SERVICE_NAME}") {
          script {
            sh """
              set -eux

              SERVICE="${SERVICE_NAME}"
              BUILD_TAG="build-${BUILD_NUMBER}"
              LOCAL_IMAGE="${SERVICE}:${BUILD_TAG}"

              ECR_REGISTRY="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
              CACHE_IMAGE="\${ECR_REGISTRY}/ai4voice/\${SERVICE}:cache"

              echo "🚀 Pulling cache image (if exists)..."
              docker pull "\${CACHE_IMAGE}" || true

              echo "🚀 Building Docker image with cache..."
              docker build \
                --cache-from="\${CACHE_IMAGE}" \
                --tag "\${LOCAL_IMAGE}" \
                .

              echo "🎉 Build completed: \${LOCAL_IMAGE}"
            """
          }
        }
      }
    }

    /* -----------------------------------------------------------
     *  LOGIN, TAG & PUSH TO ECR
     * -----------------------------------------------------------
     */
    stage('Push to ECR') {
      when { expression { fileExists("services/${params.SERVICE_NAME}/Dockerfile") } }

      steps {
        withCredentials([usernamePassword(credentialsId: 'aws-creds', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {

          dir("services/${params.SERVICE_NAME}") {
            sh """
              set -eux

              SERVICE="${SERVICE_NAME}"
              BUILD_TAG="build-${BUILD_NUMBER}"
              LOCAL_IMAGE="\${SERVICE}:${BUILD_TAG}"

              AWS_REGION="${AWS_REGION}"
              AWS_ACCOUNT="${AWS_ACCOUNT}"
              ECR_REGISTRY="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

              # Service mapping
              TARGET_REPO="\${ECR_REGISTRY}/ai4voice/\${SERVICE}"

              # Timestamp (IST)
              TAG="\$(TZ='Asia/Kolkata' date +'%d%m%Y-%H%M%S')-IST"
              FINAL_IMAGE="\${TARGET_REPO}:\${TAG}"
              CACHE_IMAGE="\${TARGET_REPO}:cache"

              export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="${AWS_REGION}"

              echo "🔐 Logging into ECR..."
              aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

              echo "📦 Ensuring ECR repo exists..."
              aws ecr describe-repositories --repository-names "ai4voice/\${SERVICE}" || \
                  aws ecr create-repository --repository-name "ai4voice/\${SERVICE}"

              echo "🔖 Tagging image..."
              docker tag "\${LOCAL_IMAGE}" "\${FINAL_IMAGE}"

              echo "📤 Pushing \${FINAL_IMAGE}..."
              docker push "\${FINAL_IMAGE}"

              echo "⚡ Updating cache image..."
              docker tag "\${LOCAL_IMAGE}" "\${CACHE_IMAGE}"
              docker push "\${CACHE_IMAGE}"

              echo "🎉 Successfully pushed and updated cache."
            """
          }
        }
      }
    }
  }

  post {
    success {
      echo "✅ BUILD SUCCESS — Service: ${params.SERVICE_NAME}, Branch: ${params.BRANCH_NAME}"
    }
    failure {
      echo "❌ BUILD FAILED — Service: ${params.SERVICE_NAME}"
    }
  }
}
