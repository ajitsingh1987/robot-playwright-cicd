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

        // 1b. Record and verify the exact branch + commit Jenkins checked out.
        //     Contract: EXPECTED_BRANCH == ACTUAL_CHECKED_OUT_BRANCH and
        //     EXPECTED_COMMIT == ACTUAL HEAD, and the branch MUST be an
        //     autonomous feature/qa-auto-* or fix/qa-auto-* branch. Any other
        //     branch (main/master/random) or any silent branch substitution makes
        //     the run fail RED immediately. Evidence is written to
        //     results/ci-evidence.json for the CI Quality Gate.
        stage('Branch Verification') {
            steps {
                bat '''
                    if not defined GIT_BRANCH (
                        echo Branch Verification RED: GIT_BRANCH not defined
                        exit /b 1
                    )
                    if not defined GIT_COMMIT (
                        echo Branch Verification RED: GIT_COMMIT not defined
                        exit /b 1
                    )

                    rem Normalize the Jenkins-reported branch (origin/... , */... ,
                    rem refs/heads/... , refs/remotes/origin/...). Use explicit
                    rem prefix slicing: the cmd substring form %VAR:*/=% is a
                    rem WILDCARD substitution and corrupted feature/... into
                    rem qa-auto-... (a real, blocking bug). Slicing is deterministic.
                    set "EXPECTED_BRANCH=%GIT_BRANCH%"
                    if /I "%EXPECTED_BRANCH:~0,20%"=="refs/remotes/origin/" set "EXPECTED_BRANCH=%EXPECTED_BRANCH:~20%"
                    if /I "%EXPECTED_BRANCH:~0,15%"=="remotes/origin/" set "EXPECTED_BRANCH=%EXPECTED_BRANCH:~15%"
                    if /I "%EXPECTED_BRANCH:~0,11%"=="refs/heads/" set "EXPECTED_BRANCH=%EXPECTED_BRANCH:~11%"
                    if /I "%EXPECTED_BRANCH:~0,7%"=="origin/" set "EXPECTED_BRANCH=%EXPECTED_BRANCH:~7%"
                    if /I "%EXPECTED_BRANCH:~0,2%"=="*/" set "EXPECTED_BRANCH=%EXPECTED_BRANCH:~2%"
                    set "EXPECTED_COMMIT=%GIT_COMMIT%"

                    rem Ask git itself which branch/commit is actually checked out.
                    for /f "delims=" %%h in ('git rev-parse HEAD') do set "ACTUAL_HEAD=%%h"
                    for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "ACTUAL_BRANCH=%%b"

                    echo Expected branch: %EXPECTED_BRANCH%
                    echo Actual branch:   %ACTUAL_BRANCH%
                    echo Expected commit: %EXPECTED_COMMIT%
                    echo Actual HEAD:     %ACTUAL_HEAD%

                    if not defined ACTUAL_BRANCH (
                        echo Branch Verification RED: could not determine the checked-out branch
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )
                    if not defined ACTUAL_HEAD (
                        echo Branch Verification RED: could not determine the checked-out commit
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )
                    if /I "%EXPECTED_BRANCH%"=="main" (
                        echo Branch Verification RED: main is not an autonomous QA branch
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )
                    if /I "%EXPECTED_BRANCH%"=="master" (
                        echo Branch Verification RED: master is not an autonomous QA branch
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )

                    rem No silent substitution: the branch git checked out must be the
                    rem exact branch Jenkins was triggered for.
                    if /I not "%EXPECTED_BRANCH%"=="%ACTUAL_BRANCH%" (
                        echo Branch Verification RED: branch substitution - expected "%EXPECTED_BRANCH%" but checked out "%ACTUAL_BRANCH%"
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )
                    rem Exact commit evidence: HEAD must equal the triggering commit.
                    if /I not "%EXPECTED_COMMIT%"=="%ACTUAL_HEAD%" (
                        echo Branch Verification RED: commit mismatch - expected "%EXPECTED_COMMIT%" but HEAD is "%ACTUAL_HEAD%"
                        echo Branch commit verification: FAIL
                        exit /b 1
                    )

                    rem Branch must match the autonomous feature/fix QA wildcard family.
                    echo %ACTUAL_BRANCH% | findstr /B /C:"feature/qa-auto-" >nul
                    if errorlevel 1 (
                        echo %ACTUAL_BRANCH% | findstr /B /C:"fix/qa-auto-" >nul
                        if errorlevel 1 (
                            echo Branch Verification RED: "%ACTUAL_BRANCH%" is not feature/qa-auto-* or fix/qa-auto-*
                            echo Branch commit verification: FAIL
                            exit /b 1
                        )
                    )

                    echo Branch commit verification: PASS
                    if not exist "results" mkdir "results"
                    echo {"branch": "%ACTUAL_BRANCH%", "commit": "%ACTUAL_HEAD%"} > "results\\ci-evidence.json"
                '''
            }
        }

        stage('Clean Results') {
            steps {
                bat '''
                    if exist results\\run rmdir /s /q results\\run
                    mkdir results\\run\\allure-results
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
                bat 'docker run --rm %IMAGE_NAME% python -m orchestra ci-gate --help'
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

        // 4b. Deterministic CI quality gate: parse output.xml (test counts),
        //     validate Allure parity + credential scan, and cross-check the
        //     checked-out branch/commit against the QA branch contract. Produces
        //     results/run/ci-quality-gate.json and exits 0 only when GREEN.
        stage('CI Quality Gate') {
            steps {
                bat '''
                    docker run --rm -v "%WORKSPACE%\\results:/app/results" %IMAGE_NAME% python -m orchestra ci-gate ^
                        --output-xml /app/results/run/output.xml ^
                        --allure-dir /app/results/run/allure-results ^
                        --branch %GIT_BRANCH% ^
                        --commit %GIT_COMMIT% ^
                        --out /app/results/run/ci-quality-gate.json
                    if errorlevel 1 exit /b 1
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