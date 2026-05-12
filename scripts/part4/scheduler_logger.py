from datetime import datetime
from enum import Enum
import sys
import urllib.parse
import psutil
import docker
import subprocess
import time


LOG_STRING = "{timestamp} {event} {job_name} {args}"

class Job(Enum):
    SCHEDULER = "scheduler"
    MEMCACHED = "memcached"
    BARNES = "barnes"
    BLACKSCHOLES = "blackscholes"
    CANNEAL = "canneal"
    FREQMINE = "freqmine"
    RADIX = "radix"
    STREAMCLUSTER = "streamcluster"
    VIPS = "vips"

jobs = [
    Job.FREQMINE,
    Job.BARNES,
    Job.BLACKSCHOLES,
    Job.CANNEAL,
    Job.RADIX,
    Job.STREAMCLUSTER,
    Job.VIPS
]

image_map = {
    Job.BARNES: "anakli/cca:splash2x_barnes",
    Job.BLACKSCHOLES: "anakli/cca:parsec_blackscholes",
    Job.CANNEAL: "anakli/cca:parsec_canneal",
    Job.FREQMINE: "anakli/cca:parsec_freqmine",
    Job.RADIX: "anakli/cca:splash2x_radix",
    Job.STREAMCLUSTER: "anakli/cca:parsec_streamcluster",
    Job.VIPS: "anakli/cca:parsec_vips"
}

thread_map = {
    Job.BARNES: 2,
    Job.BLACKSCHOLES: 1,
    Job.CANNEAL: 2,
    Job.FREQMINE: 2,
    Job.RADIX: 1,
    Job.STREAMCLUSTER: 2,
    Job.VIPS: 1
}

order_map = [Job.FREQMINE, Job.RADIX, Job.STREAMCLUSTER, Job.CANNEAL, Job.VIPS, Job.BARNES, Job.BLACKSCHOLES]

class SchedulerLogger:
    def __init__(self):
        start_date = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.docker_client = docker.from_env()
        self.running_jobs = []
        self.remaining_jobs = jobs.copy()
        self.completed_jobs = set()
        self.file_name = None
        self.file = sys.stdout
        self._log("start", Job.SCHEDULER)

    def _log(self, event: str, job_name: Job, args: str = "") -> None:
        if isinstance(job_name, str):
            self.file.write(
            LOG_STRING.format(timestamp=datetime.now().isoformat(), event=event, job_name=job_name,
                              args=args).strip() + "\n")
        else:
            self.file.write(
                LOG_STRING.format(timestamp=datetime.now().isoformat(), event=event, job_name=job_name.value,
                                args=args).strip() + "\n")
        self.file.flush()

    def job_start(self, job: Job, initial_cores: list[str], initial_threads: int):
        assert job != Job.SCHEDULER, "You don't have to log SCHEDULER here"

        if job not in image_map:
            raise ValueError(f"Unknown job: {job}")

        image = image_map[job]
        # Run the benchmark from the correct PARSEC directory (images differ)
        bench = "parsec" if "parsec" in image else "splash2x"
        command = (
            f"./run -a run -S {bench} -p {job.value} -i native -n {initial_threads}"
        )
        container = self.docker_client.containers.run(
            image,
            command,
            detach=True,
            cpuset_cpus=f"0-{initial_threads-1}",
            name=job.value,
            remove=False,
        )
        self._log("start", job, "[" + (",".join(str(i) for i in initial_cores)) + "] " + str(initial_threads))
        return container

    def memcached_start(self, initial_cores: list[str], initial_threads: int):
        job = Job.MEMCACHED
        self._log("start", job, "["+(",".join(str(i) for i in initial_cores))+"] "+str(initial_threads))
        # command_start = f"sudo sed -i 's/^-t [0-9]*/-t {initial_threads}/' /etc/memcached.conf && sudo systemctl restart memcached && sudo systemctl status memcached"
        # cpu_list = ",".join(initial_cores)
        # command_taskset = f"sudo taskset -a -cp {cpu_list} $(pgrep memcached)"
        memcached_process = [p for p in psutil.process_iter(['name']) if 'memcached' in p.info['name']][0]
        main_cmd = f"sudo renice -n -17 -p {memcached_process.pid}"
        subprocess.run(main_cmd, shell=True, check=True)

        for thread in memcached_process.threads():
            thread_cmd = f"sudo renice -n -17 -p {thread.id}"
            subprocess.run(thread_cmd, shell=True, check=True)
        self._log("custom", job, "Reniced memcached to -17")
        # subprocess.run(command_start, shell=True, check=True)
        time.sleep(2)  # Give memcached some time to restart
        # subprocess.run(command_taskset, shell=True, check=True)



    def job_end(self, job: Job) -> bool:
        assert job != Job.SCHEDULER, "You don't have to log SCHEDULER here"
        for container in self.docker_client.containers.list(all=True):
            if container.name == job.value:
                container.stop()
                self._log("end", job)
                return True
        return False

    def get_completed_jobs(self) -> None:
        for container in self.docker_client.containers.list(all=True):
            if container.status == "exited":
                job_name = container.name
                job = Job(job_name)
                if job in self.completed_jobs:
                    continue
                self.completed_jobs.add(job)
                if job in self.running_jobs:
                    self.running_jobs.remove(job)
                self._log("end", job)

    def update_cores(self, job: Job, cores: list[str]) -> None:
        assert job != Job.SCHEDULER, "You don't have to log SCHEDULER here"
        container = self.docker_client.containers.get(job.value)
        container.update(cpuset_cpus=",".join(cores))
        self._log("update_cores", job, "["+(",".join(str(i) for i in cores))+"]")

    def job_pause(self, job: Job) -> None:
        assert job != Job.SCHEDULER, "You don't have to log SCHEDULER here"
        container = self.docker_client.containers.get(job.value)
        if container.status == "running":
            container.pause()
            self._log("pause", job)
        else:
            self._log("warning", job, f"Cannot pause container {job.value} as it is not running (status: {container.status})")

    def job_unpause(self, job: Job) -> None:
        assert job != Job.SCHEDULER, "You don't have to log SCHEDULER here"
        container = self.docker_client.containers.get(job.value)
        if container.status == "paused":
            self.docker_client.containers.get(job.value).unpause()
        else:
            self._log("warning", job, f"Cannot unpause container {job.value} as it is not paused (status: {container.status})")
        self._log("unpause", job)

    def custom_event(self, job:Job, comment: str):
        self._log("custom", job, urllib.parse.quote_plus(comment))

    def end(self) -> None:
        self._log("end", Job.SCHEDULER)
        self.file.flush()

    def get_file_name(self):
        return self.file_name


def get_memcached_process() -> psutil.Process | None:
    for process in psutil.process_iter(["name"]):
        name = process.info.get("name")
        if name and "memcached" in name:
            return process
    return None


def get_cpu_utils(interval: float = 1.0):
    psutil.cpu_percent(interval=interval, percpu=True)  # Warm up the CPU percent calculation
    return [(cpu_id, util) for cpu_id, util in enumerate(psutil.cpu_percent(interval=interval, percpu=True))]


if __name__ == "__main__":
    logger = SchedulerLogger()
    logger.memcached_start(initial_cores=["0", "1", "2", "3"], initial_threads=3)
    time.sleep(5)  # Give memcached some time to start up
    memcached_process = get_memcached_process()

    last_util = -1
    MAX_CPU_UTIL = 100
    HIGH_CPU_UTIL = 50
    MEDIUM_CPU_UTIL = 40
    LOW_CPU_UTIL = 0  # Explicitly define the lower bound
    NUM_CONCURRENT_JOBS = 2
    QPS_INTERVAL_S = 15
    paused = False

    while True:
        # if memcached_process is None or not memcached_process.is_running():
        #     memcached_process = get_memcached_process()
        cpu_utils = get_cpu_utils(1.0)
        if len(logger.remaining_jobs) > 0 and len(logger.running_jobs) < NUM_CONCURRENT_JOBS:
            next_job = logger.remaining_jobs.pop(0)
            initial_threads = thread_map[next_job]
            initial_cores = [str(i[0]) for i in sorted(cpu_utils, key=lambda x: x[1])[:initial_threads]]
            logger.job_start(next_job, initial_cores=initial_cores, initial_threads=2)
            logger.running_jobs.append(next_job)
        if len(logger.running_jobs) == 0:
            logger.end()
            exit(0)

        memcached_max_cpu_util = max(cpu_utils, key=lambda x: x[1]) if cpu_utils else 0
        print(f"Memcached max thread CPU utilization: {memcached_max_cpu_util}%")
        if max(cpu_utils, key=lambda x: x[1])[1] >= HIGH_CPU_UTIL:
            min_cpu_index = min(cpu_utils, key=lambda x: x[1])[0] if cpu_utils else 0
            for job in logger.running_jobs:
                logger.update_cores(job, cores=[str(min_cpu_index)])
        elif max(cpu_utils, key=lambda x: x[1])[1] < MEDIUM_CPU_UTIL:
            for job in logger.running_jobs:
                initial_threads = thread_map[job]
                updated_cores = [str(i) for i in sorted(cpu_utils, key=lambda x: x[1])]
                updated_cores = updated_cores[:initial_threads]
                logger.update_cores(job, cores=updated_cores)




        # if HIGH_CPU_UTIL <= cpu_util <= MAX_CPU_UTIL and last_util != HIGH_CPU_UTIL:
        #     logger.custom_event(Job.SCHEDULER, f"High CPU utilization detected: {cpu_util}%")
        #     last_util = HIGH_CPU_UTIL
        #     for i, job in enumerate(logger.running_jobs):
        #         new_cores = ["3"] if i < 3 else ["2"]
        #         logger.update_cores(job, cores=new_cores)

        # elif MEDIUM_CPU_UTIL <= cpu_util < HIGH_CPU_UTIL and last_util != MEDIUM_CPU_UTIL:
        #     logger.custom_event(Job.SCHEDULER, f"Moderate CPU utilization detected: {cpu_util}%")
        #     last_util = MEDIUM_CPU_UTIL
        #     for job in logger.running_jobs:
        #         logger.update_cores(job, cores=["2", "3"])

        # elif LOW_CPU_UTIL <= cpu_util < MEDIUM_CPU_UTIL and last_util != LOW_CPU_UTIL:
        #     logger.custom_event(Job.SCHEDULER, f"Low CPU utilization detected: {cpu_util}%")
        #     last_util = LOW_CPU_UTIL
        #     for job in logger.running_jobs:
        #         logger.update_cores(job, cores=["1", "2", "3"])

        logger.get_completed_jobs()




