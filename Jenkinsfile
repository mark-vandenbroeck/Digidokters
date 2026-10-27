pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        disableConcurrentBuilds(abortPrevious: true)
        timeout(time: 60, unit: 'MINUTES')
        durabilityHint('PERFORMANCE_OPTIMIZED')
    }

    environment {
        VENV_DIR = '/tmp/venv'
        COVERAGE_CORE = 'sysmon'
        PYTHONUNBUFFERED = '1'
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
                    args '-u root:root --memory=2g --memory-swap=2g --cpus=1 -v /tmp/jenkins-pip-cache:/root/.cache/pip'
                    reuseNode true
                }
            }
            stages {
                stage('Install') {
                    steps {
                        sh '''
                            python -m venv ${VENV_DIR}
                            . ${VENV_DIR}/bin/activate
                            pip install --no-compile --prefer-binary -r requirements-dev.txt
                        '''
                    }
                }
                stage('Test') {
                    steps {
                        sh '''
                            . ${VENV_DIR}/bin/activate
                            pytest tests/ --junitxml=results.xml --cov=. --cov-report=xml:coverage.xml --durations=10
                        '''
                    }
                }
            }
        }

        stage('SonarQube analysis') {
            agent {
                docker {
                    image 'sonarsource/sonar-scanner-cli:latest'
                    args '-u root:root --entrypoint= --memory=2g --memory-swap=2g --cpus=1 -e SONAR_SCANNER_OPTS=-Xmx512m'
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
                catchError(buildResult: 'SUCCESS', stageResult: 'SUCCESS') {
                    timeout(time: 2, unit: 'MINUTES') {
                        waitForQualityGate abortPipeline: false
                    }
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