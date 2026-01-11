"""
System Metrics API Router
서버 리소스 모니터링 API (관리자 전용)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_admin_user

router = APIRouter(prefix="/admin/metrics", tags=["Admin - System Metrics"])


# ==================== Response Models ====================

class CPUMetrics(BaseModel):
    """CPU metrics"""
    usage_percent: float = Field(..., description="Overall CPU usage percentage")
    per_core: List[float] = Field(default_factory=list, description="Per-core usage percentages")
    core_count: int = Field(..., description="Number of CPU cores")
    frequency_mhz: Optional[float] = None


class MemoryMetrics(BaseModel):
    """Memory metrics"""
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float


class DiskMetrics(BaseModel):
    """Disk metrics"""
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    read_bytes: int = 0
    write_bytes: int = 0


class NetworkMetrics(BaseModel):
    """Network I/O metrics"""
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int


class ProcessMetrics(BaseModel):
    """Current process metrics"""
    pid: int
    memory_mb: float
    cpu_percent: float
    threads: int
    open_files: int


class SystemMetricsResponse(BaseModel):
    """Complete system metrics response"""
    cpu: CPUMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    network: NetworkMetrics
    process: ProcessMetrics
    uptime_seconds: float
    timestamp: datetime


class MetricHistory(BaseModel):
    """Historical metric point"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# ==================== Metrics Collection ====================

# In-memory history (last 60 readings, ~1 hour at 1 min intervals)
_metrics_history: List[Dict[str, Any]] = []
_MAX_HISTORY = 60


def _collect_metrics() -> Dict[str, Any]:
    """Collect current system metrics using psutil"""
    try:
        import psutil
    except ImportError:
        # Return mock data if psutil is not installed
        return _get_mock_metrics()
    
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        cpu_freq = psutil.cpu_freq()
        
        # Memory
        mem = psutil.virtual_memory()
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()
        
        # Network
        net = psutil.net_io_counters()
        
        # Current process
        proc = psutil.Process()
        proc_mem = proc.memory_info()
        
        # System uptime
        boot_time = psutil.boot_time()
        uptime = datetime.now().timestamp() - boot_time
        
        return {
            "cpu": {
                "usage_percent": cpu_percent,
                "per_core": cpu_per_core,
                "core_count": psutil.cpu_count(),
                "frequency_mhz": cpu_freq.current if cpu_freq else None
            },
            "memory": {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent": mem.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent,
                "read_bytes": disk_io.read_bytes if disk_io else 0,
                "write_bytes": disk_io.write_bytes if disk_io else 0
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv
            },
            "process": {
                "pid": proc.pid,
                "memory_mb": round(proc_mem.rss / (1024**2), 2),
                "cpu_percent": proc.cpu_percent(),
                "threads": proc.num_threads(),
                "open_files": len(proc.open_files()) if hasattr(proc, 'open_files') else 0
            },
            "uptime_seconds": uptime,
            "timestamp": datetime.now(timezone.utc)
        }
    except Exception as e:
        return _get_mock_metrics()


def _get_mock_metrics() -> Dict[str, Any]:
    """Return mock metrics for development/testing"""
    import random
    return {
        "cpu": {
            "usage_percent": random.uniform(10, 60),
            "per_core": [random.uniform(5, 80) for _ in range(8)],
            "core_count": 8,
            "frequency_mhz": 3200.0
        },
        "memory": {
            "total_gb": 32.0,
            "used_gb": round(random.uniform(8, 20), 2),
            "available_gb": round(random.uniform(12, 24), 2),
            "percent": random.uniform(30, 70)
        },
        "disk": {
            "total_gb": 512.0,
            "used_gb": round(random.uniform(150, 300), 2),
            "free_gb": round(random.uniform(200, 350), 2),
            "percent": random.uniform(40, 60),
            "read_bytes": random.randint(1000000000, 5000000000),
            "write_bytes": random.randint(500000000, 2000000000)
        },
        "network": {
            "bytes_sent": random.randint(100000000, 500000000),
            "bytes_recv": random.randint(200000000, 800000000),
            "packets_sent": random.randint(100000, 500000),
            "packets_recv": random.randint(150000, 600000)
        },
        "process": {
            "pid": 12345,
            "memory_mb": round(random.uniform(200, 500), 2),
            "cpu_percent": random.uniform(1, 10),
            "threads": random.randint(10, 30),
            "open_files": random.randint(20, 100)
        },
        "uptime_seconds": random.randint(3600, 86400),
        "timestamp": datetime.now(timezone.utc)
    }


# ==================== API Endpoints ====================

@router.get(
    "",
    response_model=SuccessResponse[SystemMetricsResponse],
    summary="시스템 메트릭 조회",
    description="CPU, 메모리, 디스크, 네트워크 등 시스템 리소스 현황을 조회합니다."
)
async def get_system_metrics(
    admin_user: dict = Depends(get_admin_user)
):
    """Get current system metrics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    metrics = _collect_metrics()
    
    # Store in history
    _metrics_history.append({
        "timestamp": metrics["timestamp"],
        "cpu_percent": metrics["cpu"]["usage_percent"],
        "memory_percent": metrics["memory"]["percent"],
        "disk_percent": metrics["disk"]["percent"]
    })
    
    # Trim history
    while len(_metrics_history) > _MAX_HISTORY:
        _metrics_history.pop(0)
    
    return SuccessResponse(
        data=SystemMetricsResponse(**metrics),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/cpu",
    response_model=SuccessResponse[CPUMetrics],
    summary="CPU 메트릭 조회"
)
async def get_cpu_metrics(
    admin_user: dict = Depends(get_admin_user)
):
    """Get detailed CPU metrics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    metrics = _collect_metrics()
    
    return SuccessResponse(
        data=CPUMetrics(**metrics["cpu"]),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/memory",
    response_model=SuccessResponse[MemoryMetrics],
    summary="메모리 메트릭 조회"
)
async def get_memory_metrics(
    admin_user: dict = Depends(get_admin_user)
):
    """Get detailed memory metrics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    metrics = _collect_metrics()
    
    return SuccessResponse(
        data=MemoryMetrics(**metrics["memory"]),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/disk",
    response_model=SuccessResponse[DiskMetrics],
    summary="디스크 메트릭 조회"
)
async def get_disk_metrics(
    admin_user: dict = Depends(get_admin_user)
):
    """Get detailed disk metrics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    metrics = _collect_metrics()
    
    return SuccessResponse(
        data=DiskMetrics(**metrics["disk"]),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/history",
    response_model=SuccessResponse[List[MetricHistory]],
    summary="메트릭 히스토리 조회",
    description="최근 1시간 동안의 메트릭 히스토리를 조회합니다."
)
async def get_metrics_history(
    admin_user: dict = Depends(get_admin_user)
):
    """Get historical metrics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    history = [MetricHistory(**h) for h in _metrics_history]
    
    return SuccessResponse(
        data=history,
        meta=MetaInfo(request_id=request_id)
    )
