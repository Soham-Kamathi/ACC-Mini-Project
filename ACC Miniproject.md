Yes. **That is absolutely feasible**, and if you want to move away from Firecracker, I would frame the project as a **Docker \+ Kubernetes-based serverless/FaaS platform**.

You can make it much more complete than just “run a Docker container.” You can build a system where a user **registers a function once**, gets an endpoint, and then invokes it whenever they want—very similar to the basic developer experience of Lambda.

## **What you would build**

Think of your platform as:

                YOUR SERVERLESS PLATFORM  
                         │  
        ┌────────────────┴────────────────┐  
        │                                 │  
   Function Management               Function Execution  
        │                                 │  
   Save function                      Invoke function  
   Update function                    Run container  
   Delete function                    Return output  
   View functions                     Scale workers  
        │                                 │  
        └────────────────┬────────────────┘  
                         │  
                    Kubernetes  
                         │  
                 Docker Containers  
                         │  
                  Your Functions  
---

# **1\. What the user experience looks like**

A user signs up and sees something like:

My Functions  
────────────────────────────

hello  
  POST /invoke/hello

calculate  
  POST /invoke/calculate

weather  
  POST /invoke/weather

They create a function:

def handler(event):  
    name \= event\["name"\]  
    return {  
        "message": f"Hello {name}"  
    }

Your platform stores it.

Then they get an endpoint:

POST https://your-platform.com/invoke/hello

They send:

{  
  "name": "Soham"  
}

Your platform returns:

{  
  "message": "Hello Soham"  
}

That’s essentially the **core Lambda experience**.

---

# **2\. What happens internally?**

Suppose the user calls:

POST /invoke/hello

The request travels through:

User  
 ↓  
API Gateway  
 ↓  
Function Router  
 ↓  
Function Registry  
 ↓  
Kubernetes  
 ↓  
Pod  
 ↓  
Docker Container  
 ↓  
Function  
 ↓  
Result  
 ↓  
User

For example:

                POST /invoke/hello  
                         │  
                         ▼  
                ┌─────────────────┐  
                │   API Gateway   │  
                └────────┬────────┘  
                         ▼  
                ┌─────────────────┐  
                │ Function Router │  
                └────────┬────────┘  
                         ▼  
                ┌─────────────────┐  
                │ Function DB     │  
                │                 │  
                │ hello → image X │  
                └────────┬────────┘  
                         ▼  
                   Kubernetes  
                         │  
                         ▼  
                       Pod  
                         │  
                         ▼  
                  Docker Container  
                         │  
                         ▼  
                    handler(event)  
                         │  
                         ▼  
                       Result  
---

# **3\. Where Docker comes in**

You need a standardized execution environment.

For example, you can have a base runtime image:

Python Runtime Image  
├── Python  
├── Your FaaS SDK  
└── Function execution wrapper

When a user creates:

def handler(event):  
    return event\["x"\] \* 2

your platform packages it into an executable container image.

Conceptually:

User Function  
      ↓  
Build Function Image  
      ↓  
Docker Image  
      ↓  
Container  
---

# **4\. You should NOT make users learn Docker**

This is important.

The user shouldn’t have to say:

docker build ...  
docker run ...

Instead, your platform gives them something simple.

For example:

POST /functions

with:

{  
  "name": "double",  
  "runtime": "python",  
  "code": "..."  
}

Your backend handles Docker/Kubernetes automatically.

So Docker and Kubernetes become your **infrastructure**, not the user’s responsibility.

---

# **5\. Where Kubernetes comes in**

Suppose you have:

hello  
calculate  
resize  
translate

You don’t want to manually manage containers.

Kubernetes handles the workloads.

For example:

Kubernetes Cluster  
│  
├── Node 1  
│   ├── hello Pod  
│   └── calculate Pod  
│  
├── Node 2  
│   ├── resize Pod  
│   └── translate Pod  
│  
└── Node 3  
    └── hello Pod

Kubernetes can handle:

* scheduling  
* restarting failed containers  
* replicas  
* resource limits  
* networking  
* scaling

---

# **6\. But there is one important Lambda feature: scale-to-zero**

This would make your project much more interesting.

Suppose nobody has called:

hello()

for 10 minutes.

Instead of keeping a container running:

hello → 1 running container

you can scale it down:

hello → 0 containers

Then someone invokes it:

Request  
  ↓  
No container running  
  ↓  
Kubernetes creates Pod  
  ↓  
Container starts  
  ↓  
Function executes  
  ↓  
Response

That’s called **scale-to-zero**.

It saves resources but introduces a **cold start**.

---

# **7\. Cold start becomes one of your metrics**

Suppose:

Function is idle  
     ↓  
0 replicas

Request arrives:

08:00:00.000 → Request  
08:00:00.100 → Pod created  
08:00:00.500 → Container ready  
08:00:00.520 → Function executed

Your cold-start latency could be measured as the time from invocation until the function is ready/returns.

Then compare:

Warm invocation  
       VS  
Cold invocation  
---

# **8\. You can build a proper Function Registry**

You’ll need a database.

For example:

Functions Table  
────────────────────────────────────  
id  
name  
owner  
runtime  
image  
version  
created\_at  
memory\_limit  
timeout  
status

Example:

ID:          123  
Name:        hello  
Runtime:     python  
Image:       registry/hello:v3  
Memory:      256 MB  
Timeout:     10 sec  
Version:     3

When `/invoke/hello` arrives, your router looks up this information.

---

# **9\. Function versions**

You can even support versions like Lambda.

hello  
├── v1  
├── v2  
└── v3

User can say:

/invoke/hello

→ latest version

or:

/invoke/hello/v2

→ version 2\.

This makes the project feel much more like an actual serverless platform.

---

# **10\. Function lifecycle**

Your platform can maintain:

CREATING  
   ↓  
BUILDING  
   ↓  
READY  
   ↓  
RUNNING  
   ↓  
IDLE  
   ↓  
SCALED\_TO\_ZERO

For example:

User uploads function  
        ↓  
BUILDING  
        ↓  
Docker image created  
        ↓  
READY  
        ↓  
User invokes  
        ↓  
Kubernetes Pod created  
        ↓  
RUNNING  
        ↓  
No requests  
        ↓  
SCALE TO ZERO  
---

# **11\. Your API could look like this**

You could expose APIs such as:

### **Create function**

POST /functions

### **List functions**

GET /functions

### **Get function**

GET /functions/{name}

### **Update function**

PUT /functions/{name}

### **Delete function**

DELETE /functions/{name}

### **Invoke function**

POST /invoke/{name}

### **Function logs**

GET /functions/{name}/logs

### **Function metrics**

GET /functions/{name}/metrics

That’s already a fairly complete system.

---

# **12\. Architecture I’d recommend**

I’d divide your project into these components:

                        CLIENT  
                           │  
                           ▼  
                    ┌─────────────┐  
                    │ API Gateway │  
                    └──────┬──────┘  
                           │  
                           ▼  
                 ┌──────────────────┐  
                 │ FaaS Controller   │  
                 └────────┬─────────┘  
                          │  
             ┌────────────┼────────────┐  
             ▼            ▼            ▼  
       Function DB   Image Builder   Auth  
             │            │  
             │            ▼  
             │       Docker Registry  
             │            │  
             └────────────┼────────────┐  
                          ▼            │  
                     Kubernetes       │  
                          │            │  
                    ┌─────┼─────┐      │  
                    ▼     ▼     ▼      │  
                   Pod   Pod   Pod     │  
                    │     │     │      │  
                    ▼     ▼     ▼      │  
                Container Container Container  
                    │     │     │  
                    ▼     ▼     ▼  
                  Fn A   Fn B   Fn C  
---

# **13\. Authentication**

If you’re making this a complete product, users need accounts.

For example:

User A  
 ├── function1  
 ├── function2  
 └── function3

User B  
 ├── function4  
 └── function5

User A shouldn’t be able to modify User B’s functions.

So you’ll need:

Authentication  
       ↓  
Authorization  
       ↓  
Function ownership

You could use JWT-based authentication for your own API.

---

# **14\. Resource limits**

This is another important part.

Suppose someone uploads:

while True:  
    huge\_computation()

You don’t want it consuming your entire server.

Define:

Memory: 256 MB  
CPU: 0.5 CPU  
Timeout: 10 seconds

Kubernetes can enforce CPU and memory requests/limits, while your function runner can enforce execution timeouts.

So:

Function  
 ├── CPU limit  
 ├── Memory limit  
 ├── Timeout  
 └── Concurrency limit  
---

# **15\. What about malicious functions?**

This becomes particularly important because **users are uploading code that your system executes**.

With your Docker/Kubernetes architecture, you need to treat uploaded code as **untrusted**.

You should implement/harden things such as:

* non-root containers  
* read-only root filesystem where practical  
* dropped Linux capabilities  
* seccomp/AppArmor where available  
* CPU/memory limits  
* execution timeouts  
* restricted network access  
* separate namespaces  
* Kubernetes RBAC  
* no access to Kubernetes API credentials  
* no host filesystem mounts  
* no privileged containers

The goal is:

User Function  
      ↓  
Restricted Container  
      ↓  
Restricted Kubernetes Pod  
      ↓  
Host  
---

# **16\. This also gives you your research/evaluation component**

Now your project isn’t simply:

“We made a website that runs Docker containers.”

You can evaluate it scientifically.

### **Experiment 1 — Cold start**

Scale to zero  
      ↓  
Invoke  
      ↓  
Measure latency

### **Experiment 2 — Warm start**

Container already running  
      ↓  
Invoke  
      ↓  
Measure latency

### **Experiment 3 — Concurrent execution**

1 request  
10 requests  
50 requests  
100 requests  
500 requests

Measure:

* latency  
* throughput  
* CPU  
* memory  
* failed requests

### **Experiment 4 — Scaling**

1 replica  
2 replicas  
5 replicas  
10 replicas

Measure how performance changes.

---

# **17\. And now you can compare it to Firecracker**

This is where your original Group 06 idea can still be useful.

Your project could become:

**Design and implementation of a Kubernetes-based FaaS platform using containerized function execution, with an evaluation of cold starts, resource isolation, and scalability.**

Then in your **future work**, you can say:

Replace the container execution layer with Firecracker MicroVMs and compare isolation and startup performance.

Or, if you have enough time/resources, you can actually implement both:

            FaaS API  
                │  
        ┌───────┴────────┐  
        │                │  
   Container Backend  MicroVM Backend  
        │                │  
   Kubernetes        Firecracker  
        │                │  
    Docker          MicroVMs

That would be a **very strong final-year project**, because your API stays the same while the execution backend changes.

---

# **18\. One thing I would change from your original idea**

Don’t make:

User  
 ↓  
Kubernetes API  
 ↓  
Create Pod

your main architecture.

Instead, build your own **FaaS Controller**.

User  
 ↓  
Your API  
 ↓  
Your FaaS Controller  
 ↓  
Kubernetes API  
 ↓  
Pod  
 ↓  
Container  
 ↓  
Function

That way, you’re actually developing a **system software/platform layer**, rather than simply writing a Kubernetes deployment script.

---

# **19\. Your final project in one sentence**

I’d define it as:

**A self-hosted serverless computing platform that allows users to upload, manage, version, and invoke functions on demand, with Kubernetes orchestrating isolated Docker-based execution environments and automatically handling scaling, resource limits, and function lifecycle management.**

And the complete flow is:

             USER  
                │  
                ▼  
         ┌──────────────┐  
         │ Web Dashboard│  
         │ / REST API   │  
         └──────┬───────┘  
                │  
                ▼  
        ┌─────────────────┐  
        │ FaaS Controller │  
        └───────┬─────────┘  
                │  
       ┌────────┼─────────┐  
       ▼        ▼         ▼  
    Auth      Database   Builder  
                         │  
                         ▼  
                   Docker Image  
                         │  
                         ▼  
                ┌────────────────┐  
                │  Kubernetes    │  
                └───────┬────────┘  
                        │  
                 ┌──────┼──────┐  
                 ▼      ▼      ▼  
                Pod    Pod    Pod  
                 │      │      │  
                 ▼      ▼      ▼  
              Docker Docker Docker  
            Container Container Container  
                 │      │      │  
                 ▼      ▼      ▼  
                Fn A   Fn B   Fn C

**Yes — this is a completely viable project, and arguably easier to implement and demonstrate than the Firecracker version.** The key is to make the **FaaS controller, function lifecycle, scale-to-zero, resource control, API, function storage/versioning, and benchmarking** your actual engineering work rather than just relying on Kubernetes to do everything.

