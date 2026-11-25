pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        disableConcurrentBuilds(abortPrevious: true)
        timeout(time: 60, unit: 'MINUTES')
        durabilityHint('PERFORMANCE_OPTIMIZED')
        skipDefaultCheckout(true)
    }

    environment {
        VENV_DIR = '/tmp/venv'
        COVERAGE_CORE = 'sysmon'
        PYTHONUNBUFFERED = '1'
        PYTHONDONTWRITEBYTECODE = '1'
        PIP_CACHE_DIR = '/tmp/pip-cache'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Parallel Checks & Tests') {
            failFast true
            parallel {
                stage('Secret scan') {
                    agent {
                        docker {
                            image 'ghcr.io/gitleaks/gitleaks:v8.30.1'
                            args '--entrypoint= -e HOME=/tmp'
                            reuseNode true
                        }
                    }
                    steps {
                        sh '''
                            git config --global --add safe.directory "$PWD"
                            gitleaks git --redact --verbose --exit-code 1 .
                        '''
                    }
                }

                stage('Dependency scan') {
                    agent {
                        docker {
                            image 'ghcr.io/aquasecurity/trivy:0.76.2'
                            args '--entrypoint= -e TRIVY_CACHE_DIR=/tmp/trivy-cache -v /var/cache/jenkins-trivy:/tmp/trivy-cache'
                            reuseNode true
                        }
                    }
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                            sh '''
                                trivy fs --scanners vuln \
                                  --severity HIGH,CRITICAL --ignore-unfixed \
                                  --exit-code 1 --no-progress .
                            '''
                        }
                    }
                }

                stage('Install & test') {
                    agent {
                        docker {
                            image 'python:3.12.4-slim'
                            args '--memory=2g --memory-swap=2g --cpus=1 -v /tmp/jenkins-pip-cache:/tmp/pip-cache'
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
                        stage('Unit Tests') {
                            steps {
                                sh '''
                                    . ${VENV_DIR}/bin/activate
                                    pytest tests/ --junitxml=results.xml --cov=. --cov-report=xml:coverage.xml --durations=10
                                '''
                            }
                        }
                    }
                }
            }
        }

        stage('SonarQube analysis') {
            agent {
                docker {
                    image 'sonarsource/sonar-scanner-cli:latest'
                    args '--entrypoint= --memory=2g --memory-swap=2g --cpus=1 -e SONAR_SCANNER_OPTS=-Xmx512m -e SONAR_USER_HOME=/tmp/.sonar'
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
            junit testResults: 'results.xml', allowEmptyResults: true
            recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'coverage.xml']])
        }
    }
}