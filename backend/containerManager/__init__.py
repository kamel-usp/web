from .PriorityQueue import PriorityQueue
import time
import docker
from collections import deque
import asyncio


class dockerApi:
    def __init__(self):
        self.client = docker.from_env()

    def build_image(self):
        print("Building image", flush=True)
        result = self.image_id = self.client.images.build(
            path="./dPaspRunner", tag="dpasp-runner", quiet=False
        )
        for item in result[1]:
            for key, value in item.items():
                if key == "stream":
                    print("[docker builder]", value, flush=True)
                else:
                    print("[docker builder]", key, ":", value, flush=True)

        print("Done building image!", flush=True)

    def createContainer(self):
        print("Spawning a container", flush=True)
        container = self.client.containers.run(
            "dpasp-runner",  # Specify the Docker image to use
            detach=True,  # Run the container in detached mode
        )
        print("A container was spawned", flush=True)
        net = self.client.networks.list(names="dpasp-instances")[0]
        net.connect(container, aliases=[f"dpasp-instance-{container.short_id}"])
        print(f"Created container with ID: {container.short_id}")
        return container.short_id

    def deleteContainer(self, container_id):
        container = self.client.containers.get(container_id)
        container.stop()


class containerManager:
    def __init__(self, lifetime, pre_allocate=2, docker_api=dockerApi()):
        self.docker_api = docker_api
        self.container_lifetime = lifetime
        self.lifetime_pq = PriorityQueue()
        self.user_id_to_container_id = dict()

        self.docker_api.build_image();

        self.pre_allocated_containers = deque()
        asyncio.create_task(self.allocContainers(pre_allocate))

    def activeContainerCount(self):
        return len(self.user_id_to_container_id)

    async def allocContainers(self, count):
        list_of_awaitables = []
        for _ in range(count):
            list_of_awaitables.append(asyncio.to_thread(self.docker_api.createContainer))
        awaitable_list = asyncio.gather(*list_of_awaitables)
        self.pre_allocated_containers.extend(await awaitable_list)

    async def getContainer(self, user_id):
        if self.user_id_to_container_id.get(user_id) != None:
            return self.user_id_to_container_id[user_id]
        else:
            asyncio.create_task(self.allocContainers(1))
            container_id = self.pre_allocated_containers.popleft()
            self.user_id_to_container_id[user_id] = container_id

            self.lifetime_pq.insert(
                (container_id, user_id), time.time() + self.container_lifetime
            )
            return container_id

    def pruneContainers(self):
        while (
            not self.lifetime_pq.is_empty()
            and self.lifetime_pq.top_prio() < time.time()
        ):
            container_id, user_id = self.lifetime_pq.top()
            self.lifetime_pq.pop()
            self.user_id_to_container_id.pop(user_id)
            self.docker_api.deleteContainer(container_id)

    def stopAllContainers(self):
        for user_id, container_id in self.user_id_to_container_id.items():
            print(f"Stopping container {container_id} from {user_id}")
            self.docker_api.deleteContainer(container_id)

        for container_id in self.pre_allocated_containers:
            print(f"Stoppin pre allocated container {container_id}")
            self.docker_api.deleteContainer(container_id)
