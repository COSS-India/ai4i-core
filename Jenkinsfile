pipeline {
  agent any

  environment {
    DOCKER_BUILDKIT = "1"
    GIT_REPO        = 'https://github.com/COSS-India/ai4i-core.git'
    AWS_REGION      = 'ap-south-1'
    AWS_ACCOUNT     = '662074586476'
  }

  parameters {
    string(name: 'BRANCH_NAME', defaultValue: 'master')

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
simple-ui
""",
      description: "Backend or Frontend service to build"
    )

    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true)
  }

  stages {

    /* ---------------------------
     * Cleanup
     * ---------------------------
     */
    stage('Prepare Workspace') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) deleteDir()
        }
      }
    }

    /* ---------------------------
     * Checkout Code
     * ---------------------------
     */
    stage('Checkout') {
      steps {
        checkout([
          $class: 'GitSCM',
          branches: [[name: "*/${params.BRANCH_NAME}"]],
          userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
        ])
      }
    }

    /* ---------------------------
     * Auto Detect Service Path
     * ---------------------------
     */
    stage('Validate Service Path') {
      steps {
        script {

          def backendPath  = "services/${params.SERVICE_NAME}"
          def frontendPath = "frontend/${params.SERVICE_NAME}"

          if (fileExists(backendPath)) {
            env.SERVICE_PATH = backendPath
          } else if (fileExists(frontendPath)) {
            env.SERVICE_PATH = frontendPath
          } else {
            error """
❌ ERROR: Service folder not found!

Checked:
  - ${backendPath}
  - ${frontendPath}

Please verify SERVICE_NAME.
"""
          }

          echo "✓ Service path detected: ${env.SERVICE_PATH}"
        }
      }
    }

    /* ---------------------------
     * Docker Build (with cache)
     * ---------------------------
     */
    stage('Docker Build (Cached)') {
      steps {
        dir("${env.SERVICE_PATH}") {

          sh '''
            set -eux

            SERVICE_NAME="${SERVICE_NAME}"
            AWS_REGION="${AWS_REGION}"
            AWS_ACCOUNT="${AWS_ACCOUNT}"

            BUILD_TAG="build-${BUILD_NUMBER}"
            LOCAL_IMAGE="${SERVICE_NAME}:${BUILD_TAG}"

            ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
            CACHE_IMAGE="${ECR}/ai4voice/${SERVICE_NAME}:cache"

            echo "Attempting to pull cache..."
            docker pull "${CACHE_IMAGE}" || true

            echo "Building Docker image (with cache)..."
            docker build \
              --cache-from="${CACHE_IMAGE}" \
              -t "${LOCAL_IMAGE}" .

            echo "✔ Build complete: ${LOCAL_IMAGE}"
          '''
        }
      }
    }

    /* ---------------------------
     * Push to ECR
     * ---------------------------
     */
    stage('Push to ECR') {

      when { expression { fileExists("${env.SERVICE_PATH}/Dockerfile") } }

      steps {
        withCredentials([usernamePassword(
          credentialsId: 'aws-creds',
          usernameVariable: 'AWS_ACCESS_KEY_ID',
          passwordVariable: 'AWS_SECRET_ACCESS_KEY'
        )]) {

          dir("${env.SERVICE_PATH}") {

            sh '''
              set -eux

              SERVICE_NAME="${SERVICE_NAME}"
              AWS_REGION="${AWS_REGION}"
              AWS_ACCOUNT="${AWS_ACCOUNT}"

              BUILD_TAG="build-${BUILD_NUMBER}"
              LOCAL_IMAGE="${SERVICE_NAME}:${BUILD_TAG}"

              ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
              TARGET_REPO="${ECR}/ai4voice/${SERVICE_NAME}"

              TIMESTAMP="$(TZ='Asia/Kolkata' date +'%d%m%Y-%H%M%S')-IST"
              FINAL_IMAGE="${TARGET_REPO}:${TIMESTAMP}"
              CACHE_IMAGE="${TARGET_REPO}:cache"

              export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="${AWS_REGION}"

              echo "Logging in to ECR..."
              aws ecr get-login-password --region "${AWS_REGION}" \
                | docker login --username AWS --password-stdin "${ECR}"

              echo "Ensuring repository exists..."
              aws ecr describe-repositories --repository-names "ai4voice/${SERVICE_NAME}" \
                || aws ecr create-repository --repository-name "ai4voice/${SERVICE_NAME}"

              echo "Tagging image..."
              docker tag "${LOCAL_IMAGE}" "${FINAL_IMAGE}"

              echo "Pushing production tag..."
              docker push "${FINAL_IMAGE}"

              echo "Updating cache tag..."
              docker tag "${LOCAL_IMAGE}" "${CACHE_IMAGE}"
              docker push "${CACHE_IMAGE}"

              echo "✔ Image pushed successfully:"
              echo "  - ${FINAL_IMAGE}"
              echo "  - ${CACHE_IMAGE}"
            '''
          }
        }
      }
    }
  }

  /* ---------------------------
   * Post Actions
   * ---------------------------
   */
  post {
    success {
      echo "✅ Build SUCCESS — ${params.SERVICE_NAME}"
    }
    failure {
      echo "❌ Build FAILED — ${params.SERVICE_NAME}"
    }
  }
}
