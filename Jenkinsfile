pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        disableConcurrentBuilds(abortPrevious: true)
        timeout(time: 45, unit: 'MINUTES')
    }

    environment {
        VENV_DIR = '.venv'
        COVERAGE_CORE = 'sysmon'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install & test') {
            agent {
                docker {
                    image 'python:3.12.4-slim'
                    args '-u root:root --memory=1g --memory-swap=1g --cpus=1'
                    reuseNode true
                }
            }
            steps {
                sh '''
                    python -m venv ${VENV_DIR}
                    . ${VENV_DIR}/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                    pytest --junitxml=results.xml --cov=. --cov-report=xml:coverage.xml
                '''
            }
        }

        stage('SonarQube analysis') {
            agent {
                docker {
                    image 'sonarsource/sonar-scanner-cli:latest'
                    args '-u root:root --entrypoint= --memory=1g --memory-swap=1g --cpus=1 -e SONAR_SCANNER_OPTS=-Xmx512m'
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