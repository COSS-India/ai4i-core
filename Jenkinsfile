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
"""
    )

    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true)
  }

  stages {

    /* -----------------------------
       CLEAN WORKSPACE
    ------------------------------ */
    stage('Prepare Workspace') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) deleteDir()
        }
      }
    }

    /* -----------------------------
       CHECKOUT
    ------------------------------ */
    stage('Checkout') {
      steps {
        checkout([
          $class: 'GitSCM',
          branches: [[name: "*/${params.BRANCH_NAME}"]],
          userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
        ])
      }
    }

    /* -----------------------------
       DETECT CORRECT SERVICE PATH
    ------------------------------ */
    stage('Detect Service Path') {
      steps {
        script {
          def backend = "services/${params.SERVICE_NAME}"
          def frontend = "frontend/${params.SERVICE_NAME}"

          if (fileExists(backend)) {
            env.SERVICE_PATH = backend
          } else if (fileExists(frontend)) {
            env.SERVICE_PATH = frontend
          } else {
            error """
❌ ERROR: Service not found!

Checked:
  - ${backend}
  - ${frontend}

Fix SERVICE_NAME.
"""
          }

          echo "✓ Using service path: ${env.SERVICE_PATH}"
        }
      }
    }

    /* -----------------------------
       DOCKER BUILD (NO CACHE)
    ------------------------------ */
    stage('Docker Build') {
      steps {
        dir("${env.SERVICE_PATH}") {
          sh '''
            set -eux

            SERVICE_NAME="${SERVICE_NAME}"
            BUILD_IMAGE="${SERVICE_NAME}:latest"

            echo "Building Docker image..."
            docker build -t "${BUILD_IMAGE}" .

            echo "✔ Build complete: ${BUILD_IMAGE}"
          '''
        }
      }
    }

    /* -----------------------------
       PUSH TO ECR (ONLY FINAL TAG)
    ------------------------------ */
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

              FINAL_TAG="$(TZ='Asia/Kolkata' date +'%d%m%Y-%H%M%S')-IST"

              ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
              REPO="${ECR}/ai4voice/${SERVICE_NAME}"
              FINAL_IMAGE="${REPO}:${FINAL_TAG}"

              export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="${AWS_REGION}"

              echo "Logging into ECR..."
              aws ecr get-login-password --region "${AWS_REGION}" \
                | docker login --username AWS --password-stdin "${ECR}"

              echo "Ensuring ECR repo exists..."
              aws ecr describe-repositories \
                --repository-names "ai4voice/${SERVICE_NAME}" \
                || aws ecr create-repository --repository-name "ai4voice/${SERVICE_NAME}"

              echo "Tagging final image..."
              docker tag "${SERVICE_NAME}:latest" "${FINAL_IMAGE}"

              echo "Pushing final timestamped image..."
              docker push "${FINAL_IMAGE}"

              echo "✔ FINAL IMAGE PUSHED:"
              echo "  ${FINAL_IMAGE}"
            '''
          }
        }
      }
    }
  }

  post {
    success {
      echo "✅ Build SUCCESS — ${params.SERVICE_NAME}"
    }
    failure {
      echo "❌ Build FAILED — ${params.SERVICE_NAME}"
    }
  }
}
