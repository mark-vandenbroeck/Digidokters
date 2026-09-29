pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    environment {
        VENV_DIR = '.venv'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup virtualenv') {
            agent {
                docker {
                    image 'python:3.12.4-slim'
                    args '-u root:root'
                    reuseNode true
                }
            }
            steps {
                sh '''
                    python -m venv ${VENV_DIR}
                    . ${VENV_DIR}/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Run tests') {
            agent {
                docker {
                    image 'python:3.12.4-slim'
                    args '-u root:root'
                    reuseNode true
                }
            }
            steps {
                sh '''
                    . ${VENV_DIR}/bin/activate
                    pytest --junitxml=results.xml --cov=. --cov-report=xml:coverage.xml
                '''
            }
        }

        stage('SonarQube analysis') {
            agent {
                docker {
                    image 'sonarsource/sonar-scanner-cli:latest'
                    args '-u root:root --entrypoint='
                    reuseNode true
                }
            }
            steps {
                withSonarQubeEnv('sonarqube') {
                    sh 'sonar-scanner'
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }
    }

    post {
        always {
            junit 'results.xml'
            recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'coverage.xml']])
        }
    }
}