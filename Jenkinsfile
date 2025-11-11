pipeline {
    agent any

    parameters {
        string(name: 'BRANCH_NAME', defaultValue: 'dev', description: 'Git branch to clone and build')
    }

    environment {
        GIT_REPO = 'https://github.com/COSS-India/ai4i-core.git'
    }

    stages {
        stage('Checkout') {
            steps {
                echo "Checking out branch: ${params.BRANCH_NAME}"
                // Use a fresh checkout each time, ignoring the default SCM clone
                deleteDir()
                checkout([$class: 'GitSCM',
                    branches: [[name: "*/${params.BRANCH_NAME}"]],
                    userRemoteConfigs: [[url: "${env.GIT_REPO}"]]
                ])
            }
        }

        stage('Build') {
            steps {
                echo "Building project from branch: ${params.BRANCH_NAME}"
                // Example build command
                // sh 'mvn clean install'
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
