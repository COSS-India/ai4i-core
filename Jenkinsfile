pipeline {
  agent any

  parameters {
    // Pick the Git branch to build from
    string(name: 'BRANCH_NAME', defaultValue: 'master', description: 'Git branch to clone and build')

    // Pick exactly one service under services/
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

    // Optional toggles
    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true, description: 'Delete workspace before checkout')
  }

  environment {
    GIT_REPO = 'https://github.com/COSS-India/ai4i-core.git'
  }

  options {
    timeout(time: 45, unit: 'MINUTES')
    timestamps()
  }

  stages {
    stage('Prepare') {
      steps {
        script {
          if (params.CLEAN_WORKSPACE) {
            echo "Cleaning workspace..."
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

            if [ -f "pom.xml" ]; then
              echo "[maven] Detected pom.xml"
              mvn -B -Dmaven.test.skip=true clean package
              exit 0
            fi

            if [ -f "build.gradle" ] || [ -f "gradlew" ]; then
              echo "[gradle] Detected Gradle build"
              [ -x ./gradlew ] || chmod +x ./gradlew || true
              ./gradlew clean build -x test || gradle clean build -x test
              exit 0
            fi

            if [ -f "package.json" ]; then
              echo "[node] Detected package.json"
              npm ci || npm install
              npm run build || true
              exit 0
            fi

            if [ -f "Dockerfile" ]; then
              echo "[docker] Detected Dockerfile"
              IMAGE_NAME="${params.SERVICE_NAME}:build-${BUILD_NUMBER}"
              docker build -t "$IMAGE_NAME" .
              echo "Built $IMAGE_NAME"
              exit 0
            fi

            echo "No known build file found. Add your build steps in Jenkinsfile or include a build descriptor."
            exit 1
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
    always {
      echo "Done."
    }
  }
}
