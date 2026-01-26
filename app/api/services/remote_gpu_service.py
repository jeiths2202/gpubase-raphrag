"""
Remote GPU Monitoring Service

SSH를 통해 원격 서버의 GPU 정보를 가져옵니다.
로컬에 nvidia-smi가 없는 환경(Docker 컨테이너 등)에서 원격 GPU 서버의 상태를 모니터링합니다.
"""
import asyncio
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GpuInfo:
    """GPU 기본 정보"""
    index: int
    name: str
    memory_used: float  # MB
    memory_total: float  # MB
    memory_percent: float
    utilization: float  # 0-100
    temperature: float
    power_draw: float
    power_limit: float


@dataclass
class GpuDetailInfo(GpuInfo):
    """GPU 상세 정보"""
    uuid: str = ""
    memory_free: float = 0
    utilization_memory: float = 0
    pstate: str = "P0"
    clock_sm: int = 0
    clock_mem: int = 0
    driver_version: str = "N/A"
    cuda_version: str = "N/A"


@dataclass
class GpuProcess:
    """GPU에서 실행 중인 프로세스"""
    pid: int
    name: str
    memory_mb: float
    user: str = "N/A"
    runtime: str = "N/A"
    command: str = ""


@dataclass
class GpuStatus:
    """GPU 상태 응답"""
    available: bool
    gpu_count: int = 0
    gpus: List[GpuInfo] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "gpu_count": self.gpu_count,
            "gpus": [self._gpu_to_dict(g) for g in self.gpus],
            "error": self.error,
        }

    def _gpu_to_dict(self, gpu: GpuInfo) -> Dict[str, Any]:
        return {
            "index": gpu.index,
            "name": gpu.name,
            "memory_used": gpu.memory_used,
            "memory_total": gpu.memory_total,
            "memory_percent": gpu.memory_percent,
            "utilization": gpu.utilization,
            "temperature": gpu.temperature,
            "power_draw": gpu.power_draw,
            "power_limit": gpu.power_limit,
        }


@dataclass
class GpuDetailStatus:
    """GPU 상세 상태 응답"""
    available: bool
    gpu: Optional[GpuDetailInfo] = None
    processes: List[GpuProcess] = field(default_factory=list)
    assigned_service: Optional[Dict[str, Any]] = None
    process_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "available": self.available,
            "process_count": self.process_count,
            "error": self.error,
        }
        if self.gpu:
            result["gpu"] = {
                "index": self.gpu.index,
                "name": self.gpu.name,
                "uuid": self.gpu.uuid,
                "memory_used": self.gpu.memory_used,
                "memory_total": self.gpu.memory_total,
                "memory_free": self.gpu.memory_free,
                "memory_percent": self.gpu.memory_percent,
                "utilization_gpu": self.gpu.utilization,
                "utilization_memory": self.gpu.utilization_memory,
                "temperature": self.gpu.temperature,
                "power_draw": self.gpu.power_draw,
                "power_limit": self.gpu.power_limit,
                "pstate": self.gpu.pstate,
                "clock_sm": self.gpu.clock_sm,
                "clock_mem": self.gpu.clock_mem,
                "driver_version": self.gpu.driver_version,
                "cuda_version": self.gpu.cuda_version,
            }
        if self.processes:
            result["processes"] = [
                {
                    "pid": p.pid,
                    "name": p.name,
                    "memory_mb": p.memory_mb,
                    "user": p.user,
                    "runtime": p.runtime,
                    "command": p.command,
                }
                for p in self.processes
            ]
        if self.assigned_service:
            result["assigned_service"] = self.assigned_service
        return result


class RemoteGpuService:
    """원격 서버 GPU 모니터링 서비스"""

    # GPU-서비스 매핑 (KMS 시스템)
    GPU_SERVICE_MAP = {
        0: {"name": "Qwen Text LLM", "port": 12800, "model": "Qwen/Qwen2.5-7B-Instruct", "container": "qwen-graphrag"},
        1: {"name": "NV-EmbedQA Embedding", "port": 12801, "model": "nvidia/nv-embedqa-mistral-7b-v2", "container": "nemo-embedding-graphrag"},
        2: {"name": "Vision LLM", "port": 12803, "model": "llama-3.1-nemotron-nano-vl-8b", "container": "vision-graphrag"},
        3: {"name": "CodeQwen + Learning LLM", "port": 12802, "model": "Qwen/Qwen2.5-Coder-3B + Qwen2.5-7B-QLoRA", "container": "codeqwen-graphrag, learning-llm-graphrag"},
        4: {"name": "Qwen Text LLM", "port": 12800, "model": "Qwen/Qwen2.5-7B-Instruct", "container": "qwen-graphrag"},
        5: {"name": "NV-EmbedQA Embedding", "port": 12801, "model": "nvidia/nv-embedqa-mistral-7b-v2", "container": "nemo-embedding-graphrag"},
        6: {"name": "Vision LLM", "port": 12803, "model": "llama-3.1-nemotron-nano-vl-8b", "container": "vision-graphrag"},
        7: {"name": "CodeQwen + Learning LLM", "port": 12802, "model": "Qwen/Qwen2.5-Coder-3B + Qwen2.5-7B-QLoRA", "container": "codeqwen-graphrag, learning-llm-graphrag"},
    }

    def __init__(
        self,
        remote_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "ofuser",
        ssh_key_path: Optional[str] = None,
        ssh_password: Optional[str] = None,
        cache_ttl: int = 5,
    ):
        self.remote_host = remote_host or os.getenv("REMOTE_HOST") or os.getenv("REMOTE_GPU_HOST")
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.ssh_password = ssh_password
        self.cache_ttl = cache_ttl

        # 캐시
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    def _is_cache_valid(self, key: str) -> bool:
        """캐시 유효성 확인"""
        if key not in self._cache:
            return False
        cached_time, _ = self._cache[key]
        return (time.time() - cached_time) < self.cache_ttl

    def _get_cached(self, key: str) -> Optional[Any]:
        """캐시된 값 반환"""
        if self._is_cache_valid(key):
            return self._cache[key][1]
        return None

    def _set_cache(self, key: str, value: Any) -> None:
        """캐시 설정"""
        self._cache[key] = (time.time(), value)

    def _build_ssh_command(self, remote_cmd: str) -> List[str]:
        """SSH 명령어 빌드"""
        ssh_cmd = ["ssh"]

        # 타임아웃 및 옵션
        ssh_cmd.extend([
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
        ])

        # SSH 키 경로
        if self.ssh_key_path:
            ssh_cmd.extend(["-i", self.ssh_key_path])
        else:
            # 기본 키 경로들 시도
            default_keys = [
                os.path.expanduser("~/.ssh/id_rsa"),
                os.path.expanduser("~/.ssh/id_ed25519"),
                "/root/.ssh/id_rsa",
                "/home/ofuser/.ssh/id_rsa",
            ]
            for key_path in default_keys:
                if os.path.exists(key_path):
                    ssh_cmd.extend(["-i", key_path])
                    break

        # 포트
        if self.ssh_port != 22:
            ssh_cmd.extend(["-p", str(self.ssh_port)])

        # 사용자@호스트
        ssh_cmd.append(f"{self.ssh_user}@{self.remote_host}")

        # 원격 명령어
        ssh_cmd.append(remote_cmd)

        return ssh_cmd

    async def _run_remote_command(self, command: str, timeout: int = 10) -> Tuple[bool, str, str]:
        """원격 서버에서 명령어 실행"""
        if not self.remote_host:
            # 로컬 실행 시도
            return await self._run_local_command(command, timeout)

        ssh_cmd = self._build_ssh_command(command)
        logger.debug(f"Running SSH command: {' '.join(ssh_cmd[:5])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return (
                process.returncode == 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.warning(f"SSH command timeout after {timeout}s")
            return False, "", "Command timeout"
        except FileNotFoundError:
            logger.warning("SSH client not found, trying local execution")
            return await self._run_local_command(command, timeout)
        except Exception as e:
            logger.error(f"SSH command failed: {e}")
            return False, "", str(e)

    async def _run_local_command(self, command: str, timeout: int = 10) -> Tuple[bool, str, str]:
        """로컬에서 명령어 실행"""
        try:
            # 명령어 분리
            cmd_parts = command.split()
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return (
                process.returncode == 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            return False, "", "nvidia-smi not found"
        except asyncio.TimeoutError:
            return False, "", "Command timeout"
        except Exception as e:
            return False, "", str(e)

    def _parse_value(self, value: str, default: float = 0) -> float:
        """값 파싱 ([N/A] 처리)"""
        if not value or value.strip() in ("[N/A]", "N/A", "[Not Supported]", ""):
            return default
        try:
            return float(value.strip())
        except ValueError:
            return default

    def _parse_int(self, value: str, default: int = 0) -> int:
        """정수 값 파싱"""
        if not value or value.strip() in ("[N/A]", "N/A", "[Not Supported]", ""):
            return default
        try:
            return int(float(value.strip()))
        except ValueError:
            return default

    async def get_gpu_status(self, show_all: bool = False) -> GpuStatus:
        """GPU 상태 조회"""
        cache_key = f"gpu_status_{show_all}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        async with self._lock:
            # 다시 캐시 확인 (락 대기 중 다른 요청이 캐시를 채웠을 수 있음)
            cached = self._get_cached(cache_key)
            if cached:
                return cached

            cmd = (
                "nvidia-smi "
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,"
                "temperature.gpu,power.draw,power.limit "
                "--format=csv,noheader,nounits"
            )

            success, stdout, stderr = await self._run_remote_command(cmd)

            if not success:
                error_msg = stderr or "nvidia-smi failed"
                if "not found" in error_msg.lower():
                    error_msg = "nvidia-smi not found"
                elif "timeout" in error_msg.lower():
                    error_msg = "nvidia-smi timeout"
                result = GpuStatus(available=False, error=error_msg)
                self._set_cache(cache_key, result)
                return result

            gpus: List[GpuInfo] = []
            target_gpus = None if show_all else {4, 5, 6, 7}

            for line in stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 8:
                    gpu_index = int(parts[0])
                    if target_gpus is not None and gpu_index not in target_gpus:
                        continue

                    memory_used = self._parse_value(parts[2])
                    memory_total = self._parse_value(parts[3])
                    memory_percent = round(memory_used / memory_total * 100, 1) if memory_total > 0 else 0

                    gpus.append(GpuInfo(
                        index=gpu_index,
                        name=parts[1],
                        memory_used=memory_used,
                        memory_total=memory_total,
                        memory_percent=memory_percent,
                        utilization=self._parse_value(parts[4]),
                        temperature=self._parse_value(parts[5]),
                        power_draw=self._parse_value(parts[6]),
                        power_limit=self._parse_value(parts[7]),
                    ))

            result = GpuStatus(
                available=True,
                gpu_count=len(gpus),
                gpus=gpus,
            )
            self._set_cache(cache_key, result)
            return result

    async def get_gpu_detail(self, gpu_index: int) -> GpuDetailStatus:
        """GPU 상세 정보 조회"""
        cache_key = f"gpu_detail_{gpu_index}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        async with self._lock:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

            # GPU 기본 정보 조회
            cmd = (
                f"nvidia-smi --id={gpu_index} "
                "--query-gpu=index,name,uuid,memory.used,memory.total,memory.free,"
                "utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit,"
                "pstate,clocks.sm,clocks.mem,driver_version "
                "--format=csv,noheader,nounits"
            )

            success, stdout, stderr = await self._run_remote_command(cmd)

            if not success:
                error_msg = stderr or f"Failed to get GPU {gpu_index} info"
                result = GpuDetailStatus(available=False, error=error_msg)
                return result

            line = stdout.strip()
            if not line:
                result = GpuDetailStatus(available=False, error=f"GPU {gpu_index} not found")
                return result

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 15:
                result = GpuDetailStatus(available=False, error="Incomplete GPU data")
                return result

            # CUDA 버전 조회
            cuda_version = await self._get_cuda_version()

            memory_used = self._parse_value(parts[3])
            memory_total = self._parse_value(parts[4])
            memory_percent = round(memory_used / memory_total * 100, 1) if memory_total > 0 else 0

            gpu_info = GpuDetailInfo(
                index=int(parts[0]),
                name=parts[1],
                uuid=parts[2],
                memory_used=memory_used,
                memory_total=memory_total,
                memory_free=self._parse_value(parts[5]),
                memory_percent=memory_percent,
                utilization=self._parse_value(parts[6]),
                utilization_memory=self._parse_value(parts[7]),
                temperature=self._parse_value(parts[8]),
                power_draw=self._parse_value(parts[9]),
                power_limit=self._parse_value(parts[10]),
                pstate=parts[11] if parts[11] not in ("[N/A]", "N/A") else "P0",
                clock_sm=self._parse_int(parts[12]),
                clock_mem=self._parse_int(parts[13]),
                driver_version=parts[14] if parts[14] not in ("[N/A]", "N/A") else "N/A",
                cuda_version=cuda_version,
            )

            # 프로세스 정보 조회
            processes = await self._get_gpu_processes(gpu_index)

            # 서비스 매핑
            assigned_service = self.GPU_SERVICE_MAP.get(gpu_index)

            result = GpuDetailStatus(
                available=True,
                gpu=gpu_info,
                processes=processes,
                assigned_service=assigned_service,
                process_count=len(processes),
            )
            self._set_cache(cache_key, result)
            return result

    async def _get_cuda_version(self) -> str:
        """CUDA 버전 조회"""
        cached = self._get_cached("cuda_version")
        if cached:
            return cached

        # nvcc로 CUDA 버전 확인
        success, stdout, _ = await self._run_remote_command("nvcc --version", timeout=5)
        if success and "release" in stdout:
            match = re.search(r"release (\d+\.\d+)", stdout)
            if match:
                version = match.group(1)
                self._set_cache("cuda_version", version)
                return version

        # nvidia-smi에서 CUDA 버전 확인 시도
        success, stdout, _ = await self._run_remote_command(
            "nvidia-smi --query-gpu=driver_version --format=csv,noheader",
            timeout=5
        )
        if success:
            # Driver version을 CUDA 버전으로 매핑 (대략적)
            self._set_cache("cuda_version", "N/A")
            return "N/A"

        return "N/A"

    async def _get_gpu_processes(self, gpu_index: int) -> List[GpuProcess]:
        """GPU에서 실행 중인 프로세스 조회 (상세 정보 포함)"""
        cmd = (
            f"nvidia-smi --id={gpu_index} "
            "--query-compute-apps=pid,process_name,used_memory "
            "--format=csv,noheader,nounits"
        )

        success, stdout, _ = await self._run_remote_command(cmd, timeout=5)
        if not success:
            return []

        processes: List[GpuProcess] = []
        pids: List[int] = []

        for line in stdout.strip().split("\n"):
            if not line.strip() or "No running" in line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                try:
                    pid = int(parts[0])
                    pids.append(pid)
                    processes.append(GpuProcess(
                        pid=pid,
                        name=parts[1],
                        memory_mb=self._parse_value(parts[2]),
                    ))
                except ValueError:
                    continue

        # 프로세스 상세 정보 조회 (USER, RUNTIME, COMMAND)
        if pids:
            pid_list = ",".join(str(p) for p in pids)
            ps_cmd = f"ps -p {pid_list} -o pid=,user=,etime=,command= 2>/dev/null"
            ps_success, ps_stdout, _ = await self._run_remote_command(ps_cmd, timeout=5)

            if ps_success and ps_stdout.strip():
                # PID -> 상세 정보 매핑
                ps_info: Dict[int, Dict[str, str]] = {}
                for ps_line in ps_stdout.strip().split("\n"):
                    if not ps_line.strip():
                        continue
                    # ps 출력 파싱: PID USER ETIME COMMAND
                    ps_parts = ps_line.split(None, 3)
                    if len(ps_parts) >= 1:
                        try:
                            ps_pid = int(ps_parts[0])
                            ps_info[ps_pid] = {
                                "user": ps_parts[1] if len(ps_parts) > 1 else "N/A",
                                "runtime": ps_parts[2] if len(ps_parts) > 2 else "N/A",
                                "command": ps_parts[3][:100] if len(ps_parts) > 3 else "N/A",
                            }
                        except ValueError:
                            continue

                # 프로세스 목록에 상세 정보 추가
                for proc in processes:
                    if proc.pid in ps_info:
                        info = ps_info[proc.pid]
                        proc.user = info["user"]
                        proc.runtime = info["runtime"]
                        proc.command = info["command"]

        return processes


# 싱글톤 인스턴스
_remote_gpu_service: Optional[RemoteGpuService] = None


def get_remote_gpu_service() -> RemoteGpuService:
    """원격 GPU 서비스 싱글톤 인스턴스 반환"""
    global _remote_gpu_service

    if _remote_gpu_service is None:
        # 환경 변수에서 설정 로드
        from app.api.core.config import get_api_settings
        try:
            settings = get_api_settings()
            _remote_gpu_service = RemoteGpuService(
                remote_host=getattr(settings, "REMOTE_GPU_HOST", None),
                ssh_port=getattr(settings, "REMOTE_GPU_SSH_PORT", 22),
                ssh_user=getattr(settings, "REMOTE_GPU_SSH_USER", "root"),
                ssh_key_path=getattr(settings, "REMOTE_GPU_SSH_KEY_PATH", None),
                ssh_password=getattr(settings, "REMOTE_GPU_SSH_PASSWORD", None),
                cache_ttl=getattr(settings, "REMOTE_GPU_CACHE_TTL", 5),
            )
        except Exception as e:
            logger.warning(f"Failed to load settings for RemoteGpuService: {e}")
            # 기본값으로 생성
            _remote_gpu_service = RemoteGpuService()

    return _remote_gpu_service
