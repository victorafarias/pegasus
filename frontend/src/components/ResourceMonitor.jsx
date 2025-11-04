import React from 'react';

/**
 * Converte bytes para Gigabytes (GB)
 */
function bytesToGB(bytes) {
  if (!bytes || bytes === 0) return '0.0';
  return (bytes / (1024 ** 3)).toFixed(1);
}

/**
 * Renderiza uma única barra de progresso para RAM ou Disco
 */
function StatBar({ label, usage, limit }) {
  // Converte de bytes para GB
  const usageGB = bytesToGB(usage);
  const limitGB = bytesToGB(limit);
  
  // Calcula a porcentagem
  const percent = (limit > 0) ? (usage / limit) * 100 : 0;
  
  return (
    <div className="ResourceBar-label">
      {label}: <span>{usageGB} / {limitGB} GB</span>
      <div className="ResourceBar" title={`${label}: ${percent.toFixed(0)}%`}>
        <div 
          className="ResourceBar-fill" 
          style={{ width: `${percent}%` }}
        ></div>
      </div>
    </div>
  );
}

/**
 * Renderiza a barra de CPU (que é apenas uma porcentagem)
 */
function CpuBar({ percent }) {
  const displayPercent = percent ? percent.toFixed(0) : '0';
  const isHigh = percent > 90;
  
  return (
    <div className="ResourceBar-label">
      CPU: <span>{displayPercent}%</span>
      <div className="ResourceBar" title={`CPU: ${displayPercent}%`}>
        <div 
          className={`ResourceBar-fill ${isHigh ? 'cpu-high' : ''}`}
          style={{ width: `${displayPercent}%` }}
        ></div>
      </div>
    </div>
  );
}


/**
 * O componente principal do monitor
 */
function ResourceMonitor({ stats }) {
  // stats = { ram: { usage, limit }, disk: { usage, limit }, cpu: { percent } }
  
  if (!stats) {
    return null;
  }
  
  return (
    <div className="ResourceMonitor">
      {stats.cpu && <CpuBar percent={stats.cpu.cpu_percent} />}
      {stats.ram && <StatBar label="RAM" usage={stats.ram.ram_usage} limit={stats.ram.ram_limit} />}
      {stats.disk && <StatBar label="Disco" usage={stats.disk.disk_usage} limit={stats.disk.disk_limit} />}
    </div>
  );
}

export default ResourceMonitor;