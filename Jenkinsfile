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
