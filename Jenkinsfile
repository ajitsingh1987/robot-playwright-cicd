pipeline {
    agent any

    environment {
        IMAGE_NAME = "${env.JOB_NAME}-${env.BUILD_NUMBER}".toLowerCase()
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

        // 2. Verify Docker Desktop daemon is running
        stage('Docker Check') {
            steps {
                bat '''
                    docker context use desktop-linux
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

        // 4. Run Robot + Playwright tests in Docker.
        //    docker run returns non-zero when any test fails. We must
        //    still proceed to publish results, so catch the error here
        //    (marks build + stage FAILED) WITHOUT aborting the pipeline.
        stage('Docker Run') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat 'docker run --rm -v "%WORKSPACE%\\results:/app/results" %IMAGE_NAME%'
                }
            }
        }

        // 5. Generate Allure report from workspace results.
        //    reportBuildPolicy ALWAYS -> report is built even on test failure.
        stage('Allure') {
            steps {
                allure includeProperties: false,
                       jdk: '',
                       results: [[path: 'results/allure-results']],
                       report: 'results/allure-report',
                       reportBuildPolicy: 'ALWAYS'
            }
        }

        // 6. Archive all results for later download/history.
        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'results/**', allowEmptyArchive: true
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
