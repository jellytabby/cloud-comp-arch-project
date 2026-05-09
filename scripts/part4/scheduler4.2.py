import psutil
import docker
def start_container_job(job, threads):
    image_map = {
        "barnes": "anakli/cca:splash2x_barnes",
        "blackscholes": "anakli/cca:parsec_blackscholes",
        "canneal": "anakli/cca:parsec_canneal",
        "freqmine": "anakli/cca:parsec_freqmine",
        "radix": "anakli/cca:splash2x_radix",
        "streamcluster": "anakli/cca:parsec_streamcluster",
        "vips": "anakli/cca:parsec_vips"
    }
    
    if job not in image_map:
        raise ValueError(f"Unknown job: {job}")
    
    image = image_map[job]
    command = f"docker run --cpuset-cpus=\"0-{threads-1}\" -d --rm --name {job} {image} ./run -a run -S parsec -p {job} -i native -n {threads}"
    docker_client = docker.from_env()
    container = docker_client.containers.run(image, command, detach=True, cpuset_cpus=f"0-{threads-1}", name=job, remove=True)
    return container

def get_cpu_utilization():
    return psutil.cpu_percent(interval=0.5)


if __name__ == "__main__":
    docker_client = docker.from_env()
    jobs = ["barnes", "blackscholes", "canneal", "freqmine", "radix", "streamcluster", "vips"]
    threads = 4

    for job in jobs:
        container = start_container_job(job, threads)
        print(f"Started container for {job}: {container.id}")
    while True:
        if not any(docker_client.containers.list(filters={"name": job}) for job in jobs):
            logger.stop()
        cpu_util = get_cpu_utilization()
        if cpu_util > 80:
            print(f"High CPU utilization detected: {cpu_util}%")
            for job in jobs:
                docker_client.containers.get(job).update(cpu_quota=50000)  # Limit to 50% CPU
        else:
            print(f"CPU utilization: {cpu_util}%")
            for job in jobs:
                docker_client.containers.get(job).update(cpu_quota=-1)  # Remove CPU limit

