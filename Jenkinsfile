// This Jenkinsfile should be stored in the 'devops' branch
// It will clone the code from the parameterized branch (default: 'dev')
pipeline {
    agent any
    
    parameters {
        string(
            name: 'BRANCH',
            defaultValue: 'dev',
            description: 'Git branch to checkout (code branch, not Jenkinsfile branch)'
        )
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "*/${params.BRANCH}"]],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [],
                    userRemoteConfigs: [[
                        url: 'https://github.com/COSS-India/ai4i-core.git',
                        credentialsId: ''
                    ]]
                ])
            }
        }
    }
}

