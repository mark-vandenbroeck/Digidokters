pipeline {
    agent {
        docker {
            image 'python:3.12.4-slim'
            // Nodig zodat pip packages kan installeren; args indien specifieke rechten nodig zijn
            args '-u root:root'
        }
    }

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
            steps {
                sh '''
                    . ${VENV_DIR}/bin/activate
                    pytest --junitxml=results.xml
                '''
            }
        }
    }

    post {
        always {
            junit 'results.xml'
        }
    }
}