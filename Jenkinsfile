stage('Docker Check') {
    steps {
        bat '''
            set DOCKER_HOST=npipe:////./pipe/dockerDesktopLinuxEngine

            echo ===== DOCKER HOST =====
            echo %DOCKER_HOST%

            echo ===== DOCKER PATH =====
            where docker

            echo ===== DOCKER VERSION =====
            docker --version

            echo ===== DOCKER PS =====
            docker ps

            echo ===== DOCKER INFO =====
            docker info
        '''
    }
}