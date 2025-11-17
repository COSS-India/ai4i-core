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
"""
    )
    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true)
  }

  stages {

    stage('Prepare Workspace') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) deleteDir()
        }
      }
    }

    stage('Checkout') {
      steps {
        checkout([
          $class: 'GitSCM',
          branches: [[name: "*/${params.BRANCH_NAME}"]],
          userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
        ])
      }
    }

    stage('Validate Service') {
      steps {
        script {
          if (!fileExists("services/${params.SERVICE_NAME}")) {
            error "Service directory not found: services/${params.SERVICE_NAME}"
          }
        }
      }
    }

    /* -----------------------------------------------------------
     *  DOCKER BUILD WITH SAFE ESCAPED VARIABLES
     * -----------------------------------------------------------
     */
    stage('Docker Build (Cached)') {
      steps {
        dir("services/${params.SERVICE_NAME}") {

          sh """
            set -eux

            SERVICE_NAME="${params.SERVICE_NAME}"
            AWS_REGION="${env.AWS_REGION}"
            AWS_ACCOUNT="${env.AWS_ACCOUNT}"

            BUILD_TAG="build-${BUILD_NUMBER}"
            LOCAL_IMAGE="\${SERVICE_NAME}:\${BUILD_TAG}"

            ECR_REGISTRY="\${AWS_ACCOUNT}.dkr.ecr.\${AWS_REGION}.amazonaws.com"
            CACHE_IMAGE="\${ECR_REGISTRY}/ai4voice/\${SERVICE_NAME}:cache"

            echo "Pulling cache image if exists..."
            docker pull "\${CACHE_IMAGE}" || true

            echo "Building using cache..."
            docker build --cache-from="\${CACHE_IMAGE}" -t "\${LOCAL_IMAGE}" .

            echo "Build done: \${LOCAL_IMAGE}"
          """

        }
      }
    }

    /* -----------------------------------------------------------
     *  PUSH TO ECR (SAFE VERSION)
     * -----------------------------------------------------------
     */
    stage('Push to ECR') {

      when { expression { fileExists("services/${params.SERVICE_NAME}/Dockerfile") } }

      steps {
        withCredentials([usernamePassword(credentialsId: 'aws-creds',
                        usernameVariable: 'AWS_ACCESS_KEY_ID',
                        passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {

          dir("services/${params.SERVICE_NAME}") {

            sh """
              set -eux

              SERVICE_NAME="${params.SERVICE_NAME}"
              AWS_REGION="${env.AWS_REGION}"
              AWS_ACCOUNT="${env.AWS_ACCOUNT}"

              BUILD_TAG="build-${BUILD_NUMBER}"
              LOCAL_IMAGE="\${SERVICE_NAME}:\${BUILD_TAG}"

              ECR_REGISTRY="\${AWS_ACCOUNT}.dkr.ecr.\${AWS_REGION}.amazonaws.com"
              TARGET_REPO="\${ECR_REGISTRY}/ai4voice/\${SERVICE_NAME}"

              TAG="\$(TZ='Asia/Kolkata' date +'%d%m%Y-%H%M%S')-IST"
              FINAL_IMAGE="\${TARGET_REPO}:\${TAG}"
              CACHE_IMAGE="\${TARGET_REPO}:cache"

              export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="\${AWS_REGION}"

              echo "Login ECR..."
              aws ecr get-login-password --region "\${AWS_REGION}" \
                | docker login --username AWS --password-stdin "\${ECR_REGISTRY}"

              echo "Verify/Create repo..."
              aws ecr describe-repositories --repository-names "ai4voice/\${SERVICE_NAME}" || \
                aws ecr create-repository --repository-name "ai4voice/\${SERVICE_NAME}"

              echo "Tagging final image..."
              docker tag "\${LOCAL_IMAGE}" "\${FINAL_IMAGE}"

              echo "Pushing main tag..."
              docker push "\${FINAL_IMAGE}"

              echo "Updating cache..."
              docker tag "\${LOCAL_IMAGE}" "\${CACHE_IMAGE}"
              docker push "\${CACHE_IMAGE}"

              echo "Done!"
            """

          }
        }
      }
    }
  }

  post {
    success {
      echo "✅ Build Success — ${params.SERVICE_NAME}"
    }
    failure {
      echo "❌ Build Failed — ${params.SERVICE_NAME}"
    }
  }
}
