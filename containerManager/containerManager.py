from PriorityQueue import PriorityQueue
import time

class dockerApi:
    def __init__(self):
        pass
    def createContainer():
        print ("NAO SOU MOCK")
        pass
    def deleteContainer(container_id):
        pass

class containerManager:
    def __init__(self, lifetime, docker_api = dockerApi()):
        self.docker_api = docker_api
        self.container_lifetime = lifetime
        self.lifetime_pq = PriorityQueue()
        self.user_id_to_container_id = dict()

    def activeContainerCount(self):
        return len(self.user_id_to_container_id)

    def getContainer(self, user_id):
        if self.user_id_to_container_id.get(user_id) != None:
            return self.user_id_to_container_id[user_id]
        else:
            container_id = self.docker_api.createContainer()
            self.user_id_to_container_id[user_id] = container_id

            self.lifetime_pq.insert((container_id, user_id), time.time() + self.container_lifetime)
            return container_id

    def pruneContainers(self):
        while not self.lifetime_pq.is_empty() and self.lifetime_pq.top_prio() < time.time():
            container_id, user_id = self.lifetime_pq.top()
            self.lifetime_pq.pop()
            self.user_id_to_container_id.pop(user_id)
            self.docker_api.deleteContainer(container_id)
        


