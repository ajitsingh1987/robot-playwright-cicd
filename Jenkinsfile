stage('Build Docker Image') {
    steps {
        bat 'docker build -t robot-playwright-cicd:latest .'
    }
}

stage('Run Robot Tests in Docker') {
    steps {
        bat '''
        if exist allure-results rmdir /s /q allure-results
        mkdir allure-results

        docker run --rm ^
          -v "%CD%\\allure-results:/app/allure-results" ^
          robot-playwright-cicd:latest
        '''
    }
}