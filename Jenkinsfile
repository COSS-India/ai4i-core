pipeline {
    agent any

    parameters {
        string(name: 'BRANCH_NAME', defaultValue: 'main', description: 'Git branch to clone and build')
    }

    environment {
        GIT_REPO = 'https://github.com/COSS-India/ai4i-core.git'
    }

    stages {
        stage('Checkout') {
            steps {
                echo "Cloning branch: ${params.BRANCH_NAME}"
                // Clone the specified branch
                git branch: "${params.BRANCH_NAME}", url: "${env.GIT_REPO}"
            }
        }

        stage('Build') {
            steps {
                echo "Building project from branch: ${params.BRANCH_NAME}"
                // Add your build commands here, for example:
                // sh 'mvn clean install'
                // or
                // sh './gradlew build'
                // or any custom script
            }
        }
    }

    post {
        success {
            echo "Build completed successfully for branch ${params.BRANCH_NAME}"
        }
        failure {
            echo "Build failed for branch ${params.BRANCH_NAME}"
        }
    }
}
