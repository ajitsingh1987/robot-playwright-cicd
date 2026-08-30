stage('Docker Check') {
    steps {
        bat '''
            docker context use desktop-linux
            docker context show
            docker --version
            docker ps
            docker info
        '''
    }
}