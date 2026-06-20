use serde::{Deserialize, Serialize};
use sysinfo::{System, SystemExt, ProcessExt, CpuExt};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemInfo {
    pub os: String,
    #[serde(rename = "osVersion")]
    pub os_version: String,
    pub arch: String,
    #[serde(rename = "hostname")]
    pub hostname: String,
    #[serde(rename = "totalMemory")]
    pub total_memory: u64,
    #[serde(rename = "availableMemory")]
    pub available_memory: u64,
    #[serde(rename = "cpuCount")]
    pub cpu_count: usize,
    #[serde(rename = "cpuName")]
    pub cpu_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryUsage {
    pub total: u64,
    pub used: u64,
    pub free: u64,
    #[serde(rename = "usagePercent")]
    pub usage_percent: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CPUInfo {
    pub name: String,
    #[serde(rename = "vendorId")]
    pub vendor_id: String,
    pub cores: usize,
    #[serde(rename = "frequencyMhz")]
    pub frequency_mhz: u64,
    pub usage: f32,
}

/// Get comprehensive system information
#[tauri::command]
pub async fn get_system_info() -> Result<SystemInfo, String> {
    let mut sys = System::new();
    sys.refresh_system();

    Ok(SystemInfo {
        os: std::env::consts::OS.to_string(),
        os_version: format!(
            "{} {}",
            System::long_os_version().unwrap_or_default(),
            System::kernel_version()
        ),
        arch: std::env::consts::ARCH.to_string(),
        hostname: sys.host_name().unwrap_or_else(|| "unknown".to_string()),
        total_memory: sys.total_memory(),
        available_memory: sys.available_memory(),
        cpu_count: sys.cpus().len(),
        cpu_name: sys.cpus().first()
            .map(|c| c.brand().to_string())
            .unwrap_or_default(),
    })
}

/// Get memory usage information
#[tauri::command]
pub async fn get_memory_usage() -> Result<MemoryUsage, String> {
    let mut sys = System::new();
    sys.refresh_memory();

    let total = sys.total_memory();
    let available = sys.available_memory();
    let used = total.saturating_sub(available);
    
    Ok(MemoryUsage {
        total,
        used,
        free: available,
        usage_percent: if total > 0 { (used as f32 / total as f32) * 100.0 } else { 0.0 },
    })
}

/// Get CPU information
#[tauri::command]
pub async fn get_cpu_info() -> Result<CPUInfo, String> {
    let mut sys = System::new();
    sys.refresh_cpu_usage();
    
    // Wait a bit for accurate CPU usage
    std::thread::sleep(std::time::Duration::from_millis(200));
    sys.refresh_cpu_usage();

    let usage = sys.cpus().iter()
        .map(|c| c.cpu_usage())
        .sum::<f32>() / sys.cpus().len().max(1) as f32;

    Ok(CPUInfo {
        name: sys.cpus().first()
            .map(|c| c.brand().to_string())
            .unwrap_or_default(),
        vendor_id: sys.cpus().first()
            .map(|c| c.vendor_id().to_string())
            .unwrap_or_default(),
        cores: sys.cpus().len(),
        frequency_mhz: sys.cpus().first()
            .map(|c| c.frequency())
            .unwrap_or(0),
        usage,
    })
}
