pipeline {
    agent any

    environment {
        IMAGE_NAME = "${env.JOB_NAME}-${env.BUILD_NUMBER}".replaceAll('[^A-Za-z0-9_.-]', '-').toLowerCase()
    }

    options {
        disableConcurrentBuilds()
        timestamps()
    }

    stages {

        // 1. Fetch code from GitHub (triggered by webhook)
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Clean Results') {
            steps {
                bat '''
                    if exist results\run rmdir /s /q results\run
                    mkdir results\run\allure-results
                '''
            }
        }

        // 2. Verify Docker Desktop daemon is running
        stage('Docker Check') {
            steps {
                bat '''
                    docker context show
                    docker --version
                    docker ps
                '''
            }
        }

        // 3. Build the test image
        stage('Docker Build') {
            steps {
                bat 'docker build -t %IMAGE_NAME% .'
            }
        }

        stage('Framework Gates') {
            steps {
                bat 'docker run --rm %IMAGE_NAME% python -m orchestra arch'
                bat 'docker run --rm %IMAGE_NAME% python -m pytest orchestra/tests -q'
                bat 'docker run --rm %IMAGE_NAME% python -m orchestra dry-run --mode NEW_AUTOMATION --scope FULL_REGRESSION'
            }
        }

        // 4. Run Robot + Playwright tests in Docker.
        //    docker run returns non-zero when any test fails.
        //    Results are still published through catchError.
        stage('Docker Run') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat 'docker run --rm -v "%WORKSPACE%\\results:/app/results" %IMAGE_NAME%'
                }
            }
        }

        stage('Evidence Gate') {
            steps {
                bat '''
                    if not exist results\run\output.xml exit /b 1
                    if not exist results\run\allure-results exit /b 1
                    dir /b results\run\allure-results\*-result.json >nul 2>&1 || exit /b 1
                '''
            }
        }

        // 5. Generate Allure report from workspace results.
        //    reportBuildPolicy ALWAYS -> report is built even on test failure.
        stage('Allure') {
            steps {
                allure includeProperties: false,
                       jdk: '',
                       results: [[path: 'results/run/allure-results']],
                       report: 'results/run/allure-report',
                       reportBuildPolicy: 'ALWAYS'
            }
        }

        // 6. Archive all results for later download/history.
        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'results/**', allowEmptyArchive: false
            }
        }
    }

    // 7. Post actions always run regardless of build outcome.
    post {
        always {
            echo "Build result: ${currentBuild.currentResult}"
        }

        success {
            echo 'Pipeline SUCCESS'
        }

        failure {
            echo 'Pipeline FAILED - tests failed or infrastructure error'
            // notification hook point (email / Teams / Discord)
        }

        cleanup {
            cleanWs()
        }
    }
}