from locust import FastHttpUser, TaskSet, between #type: ignore

def index(l):
    l.client.get("/")

class MinimalTest(TaskSet):
    def on_start(self):
        index(self)


class WebsiteUser(FastHttpUser):
    tasks = [MinimalTest]
    wait_time = between(1, 6)
