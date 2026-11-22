import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Activity, ArrowDown, ArrowUp, BarChart3, CheckCircle2, AlertCircle,
  Clock, Cpu, HardDrive, RefreshCw, Zap, Server, Shield, Layers,
  ChevronDown, ChevronRight, Copy, Check, Filter, Info, Sparkles,
  ArrowRight, Box, Play, AlertTriangle
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

export const formatTime = (ts: string | null | undefined): string => {
  if (!ts) return '-';
  const str = String(ts).trim();
  const iso = (str.includes('Z') || /[+-]\d{2}:\d{2}$/.test(str)) ? str : `${str.replace(' ', 'T')}Z`;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? str : d.toLocaleTimeString();
};

export const formatDateTime = (ts: string | null | undefined): string => {
  if (!ts) return '-';
  const str = String(ts).trim();
  const iso = (str.includes('Z') || /[+-]\d{2}:\d{2}$/.test(str)) ? str : `${str.replace(' ', 'T')}Z`;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? str : d.toLocaleString();
};

interface Props {
  token: string | null;
  initialFunctionId?: string | null;
  onSelectFunctionToInvoke?: (name: string) => void;
}

export default function ObservabilityView({ token, initialFunctionId, onSelectFunctionToInvoke }: Props) {
  // Mode: 'platform' or 'function'
  const [viewScope, setViewScope] = useState<'platform' | 'function'>(initialFunctionId ? 'function' : 'platform');
  const [selectedFnId, setSelectedFnId] = useState<string>(initialFunctionId || '');
  const [timeRange, setTimeRange] = useState<'15m' | '1h' | '6h' | '24h' | 'all'>('1h');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(5); // seconds
  const [loading, setLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  // Data States
  const [platformData, setPlatformData] = useState<any>(null);
  const [functionData, setFunctionData] = useState<any>(null);
  const [functionList, setFunctionList] = useState<any[]>([]);
  const [functionHistory, setFunctionHistory] = useState<any[]>([]);
  const [activeFunctionSubTab, setActiveFunctionSubTab] = useState<'charts' | 'pods' | 'scaling' | 'versions' | 'history'>('charts');

  // UI expand states
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const getHeaders = useCallback(() => ({
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  }), [token]);

  // Load functions list for the dropdown
  const loadFunctionList = useCallback(async () => {
    try {
      const resp = await axios.get(`${API_BASE}/observability/functions`, getHeaders());
      setFunctionList(resp.data || []);
      if (!selectedFnId && resp.data && resp.data.length > 0) {
        setSelectedFnId(resp.data[0].public_id || resp.data[0].name);
      }
    } catch (e) {
      console.error('Failed to load observability functions list', e);
    }
  }, [getHeaders, selectedFnId]);

  // Load platform overview data
  const loadPlatformData = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get(`${API_BASE}/observability/overview?time_range=${timeRange}`, getHeaders());
      setPlatformData(resp.data);
      setLastRefreshed(new Date());
    } catch (e) {
      console.error('Failed to load platform observability', e);
    } finally {
      setLoading(false);
    }
  }, [getHeaders, timeRange]);

  // Load per-function deep data
  const loadFunctionData = useCallback(async () => {
    if (!selectedFnId) return;
    setLoading(true);
    try {
      const [deepRes, histRes] = await Promise.all([
        axios.get(`${API_BASE}/observability/functions/${selectedFnId}?time_range=${timeRange}`, getHeaders()),
        axios.get(`${API_BASE}/observability/functions/${selectedFnId}/history?limit=30`, getHeaders())
      ]);
      setFunctionData(deepRes.data);
      setFunctionHistory(histRes.data || []);
      setLastRefreshed(new Date());
    } catch (e) {
      console.error('Failed to load function observability', e);
    } finally {
      setLoading(false);
    }
  }, [getHeaders, selectedFnId, timeRange]);

  // Initial & scope change loader
  useEffect(() => {
    loadFunctionList();
  }, [loadFunctionList]);

  useEffect(() => {
    if (initialFunctionId) {
      setSelectedFnId(initialFunctionId);
      setViewScope('function');
    }
  }, [initialFunctionId]);

  useEffect(() => {
    if (viewScope === 'platform') {
      loadPlatformData();
    } else {
      loadFunctionData();
    }
  }, [viewScope, loadPlatformData, loadFunctionData]);

  // Auto-refresh timer
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      if (viewScope === 'platform') {
        loadPlatformData();
      } else {
        loadFunctionData();
      }
    }, refreshInterval * 1000);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, viewScope, loadPlatformData, loadFunctionData]);

  const copyText = (text: string, id: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedField(id);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const formatJson = (val: any) => {
    if (!val) return '';
    try {
      const parsed = typeof val === 'string' ? JSON.parse(val) : val;
      return JSON.stringify(parsed, null, 2);
    } catch {
      return String(val);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Observability Scope Bar */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          {/* Scope Selector: Platform vs Function */}
          <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200/70">
            <button
              onClick={() => setViewScope('platform')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                viewScope === 'platform'
                  ? 'bg-white text-indigo-700 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Platform Overview</span>
            </button>
            <button
              onClick={() => setViewScope('function')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                viewScope === 'function'
                  ? 'bg-white text-indigo-700 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Per-Function Deep Dive</span>
            </button>
          </div>

          {/* Function Selector Dropdown if in Function Scope */}
          {viewScope === 'function' && (
            <div className="flex items-center gap-2">
              <select
                value={selectedFnId}
                onChange={(e) => setSelectedFnId(e.target.value)}
                className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 font-mono"
              >
                {functionList.map((fn) => (
                  <option key={fn.id} value={fn.public_id || fn.name}>
                    {fn.name} ({fn.runtime}) • {fn.status}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Time Filters & Refresh Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Time range filters */}
          <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200/70">
            {(['15m', '1h', '6h', '24h', 'all'] as const).map((tr) => (
              <button
                key={tr}
                onClick={() => setTimeRange(tr)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition cursor-pointer ${
                  timeRange === tr
                    ? 'bg-slate-900 text-white'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {tr === '15m' ? '15 min' : tr === '1h' ? '1 hour' : tr === '6h' ? '6 hours' : tr === '24h' ? '24 hours' : 'All time'}
              </button>
            ))}
          </div>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-2.5 py-1.5 rounded-xl text-xs font-medium border flex items-center gap-1.5 cursor-pointer ${
              autoRefresh
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-50 text-slate-600 border-slate-200'
            }`}
            title="Auto-refresh telemetry every 10s"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
            <span>{autoRefresh ? 'Live' : 'Paused'}</span>
          </button>

          {/* Manual Refresh button */}
          <button
            onClick={() => (viewScope === 'platform' ? loadPlatformData() : loadFunctionData())}
            disabled={loading}
            className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 transition cursor-pointer"
            title="Refresh metrics now"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Render View Scope */}
      {viewScope === 'platform' ? (
        <PlatformObservabilitySection
          data={platformData}
          loading={loading}
          timeRange={timeRange}
          onSelectFunction={(pubId) => {
            setSelectedFnId(pubId);
            setViewScope('function');
          }}
        />
      ) : (
        <FunctionObservabilitySection
          data={functionData}
          history={functionHistory}
          loading={loading}
          timeRange={timeRange}
          activeSubTab={activeFunctionSubTab}
          setActiveSubTab={setActiveFunctionSubTab}
          expandedLogId={expandedLogId}
          setExpandedLogId={setExpandedLogId}
          copiedField={copiedField}
          copyText={copyText}
          formatJson={formatJson}
          onSelectFunctionToInvoke={onSelectFunctionToInvoke}
        />
      )}
    </div>
  );
}

// ============================================================================
// 1. PLATFORM-WIDE OBSERVABILITY SECTION
// ============================================================================

function PlatformObservabilitySection({
  data,
  loading,
  timeRange,
  onSelectFunction
}: {
  data: any;
  loading: boolean;
  timeRange: string;
  onSelectFunction: (publicId: string) => void;
}) {
  if (!data && loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
        <span className="text-sm font-semibold">Aggregating platform telemetry across cluster...</span>
      </div>
    );
  }

  const s = data?.summary || {};
  const timeSeries = data?.time_series || [];
  const breakdown = data?.function_breakdown || [];
  const scalingEvents = data?.recent_scaling_events || [];

  return (
    <div className="space-y-6">
      {/* 6 Key Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        {/* Card 1: Invocations & RPS */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Invocations</span>
            <Activity className="w-3.5 h-3.5 text-indigo-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
            {s.total_invocations?.toLocaleString() ?? 0}
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1">
            <span className="font-semibold text-indigo-600">{s.rps ?? 0}</span> RPS avg
            <span className="text-slate-300">•</span>
            <span className="font-semibold text-slate-700">{s.in_flight_concurrent ?? 0}</span> in-flight
          </div>
        </div>

        {/* Card 2: Success & Error Rate */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Success Rate</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          </div>
          <div className="text-2xl font-black text-emerald-700 tracking-tight font-mono">
            {s.success_rate_pct ?? 100}%
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1">
            <span>Errors: <strong className="text-rose-600">{s.failed_invocations ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>Timeouts: <strong className="text-amber-600">{s.timeout_count ?? 0}</strong></span>
          </div>
        </div>

        {/* Card 3: Latency Percentiles */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Avg Latency</span>
            <Clock className="w-3.5 h-3.5 text-sky-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
            {s.avg_execution_latency_ms ?? 0} <span className="text-xs font-normal text-slate-400">ms</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1 font-mono">
            <span>p50: <strong>{s.p50_latency_ms ?? 0}</strong>ms</span>
            <span className="text-slate-300">•</span>
            <span>p99: <strong className="text-rose-600">{s.p99_latency_ms ?? 0}</strong>ms</span>
          </div>
        </div>

        {/* Card 4: Cold Starts */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Cold Start Ratio</span>
            <Zap className="w-3.5 h-3.5 text-amber-600" />
          </div>
          <div className="text-2xl font-black text-amber-700 tracking-tight font-mono">
            {s.cold_start_ratio_pct ?? 0}%
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Count: <strong>{s.cold_start_count ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>Avg: <strong>{s.avg_cold_start_duration_ms ?? 0}ms</strong></span>
          </div>
        </div>

        {/* Card 5: Replicas & Functions */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Active Pod Replicas</span>
            <Server className="w-3.5 h-3.5 text-indigo-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
            {s.active_replicas ?? 0} <span className="text-xs font-normal text-slate-400">pods</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Total: <strong>{s.total_functions ?? 0}</strong> fns</span>
            <span className="text-slate-300">•</span>
            <span>Scaled 0: <strong>{s.scaled_to_zero_count ?? 0}</strong></span>
          </div>
        </div>

        {/* Card 6: Infrastructure & Pods */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Cluster Pod Health</span>
            <Cpu className="w-3.5 h-3.5 text-purple-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono flex items-center gap-1.5">
            <span>{s.ready_pod_count ?? 0}/{s.pod_count ?? 0}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-sans font-bold ${
              s.k8s_connected ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
            }`}>
              {s.k8s_connected ? 'K8s Online' : 'Standalone'}
            </span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Restarts: <strong>{s.pod_restarts_total ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>OOM: <strong className="text-rose-600">{s.oom_kills_total ?? 0}</strong></span>
          </div>
        </div>
      </div>

      {/* Primary Telemetry Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Chart 1: Invocation Throughput & Status */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Invocation Throughput & Error Distribution</h3>
              <p className="text-xs text-slate-500">Total requests and errors grouped across time intervals</p>
            </div>
            <div className="flex items-center gap-3 text-xs font-semibold">
              <span className="flex items-center gap-1 text-slate-700">
                <span className="w-2.5 h-2.5 rounded-sm bg-indigo-500" /> Total
              </span>
              <span className="flex items-center gap-1 text-rose-700">
                <span className="w-2.5 h-2.5 rounded-sm bg-rose-500" /> Errors
              </span>
            </div>
          </div>
          <SimpleTimeSeriesBarChart
            data={timeSeries}
            valueKey="invocations"
            errorKey="errors"
            height={200}
          />
        </div>

        {/* Chart 2: Latency Percentiles (p50 / p95 / p99 / Avg) */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Latency Percentile Trends (p50, p95, p99)</h3>
              <p className="text-xs text-slate-500">Execution duration curves reported in milliseconds</p>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-semibold">
              <span className="flex items-center gap-1 text-sky-700">
                <span className="w-2 h-2 rounded-full bg-sky-500" /> p50
              </span>
              <span className="flex items-center gap-1 text-amber-700">
                <span className="w-2 h-2 rounded-full bg-amber-500" /> p95
              </span>
              <span className="flex items-center gap-1 text-rose-700">
                <span className="w-2 h-2 rounded-full bg-rose-500" /> p99
              </span>
            </div>
          </div>
          <MultiLineLatencyChart
            data={timeSeries}
            height={200}
          />
        </div>
      </div>

      {/* Secondary Row: Cold Starts vs Warm & Resource Gauges */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Cold vs Warm Invocations */}
        <div className="lg:col-span-2 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Cold-Start vs Warm Invocations</h3>
              <p className="text-xs text-slate-500">Visualizing scale-from-zero container activations vs cached instances</p>
            </div>
            <div className="flex items-center gap-3 text-xs font-semibold">
              <span className="flex items-center gap-1 text-amber-700">
                <span className="w-2.5 h-2.5 rounded-sm bg-amber-500" /> Cold Start
              </span>
              <span className="flex items-center gap-1 text-emerald-700">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Warm Cached
              </span>
            </div>
          </div>
          <ColdWarmStackedChart data={timeSeries} height={180} />
        </div>

        {/* Cluster Resource & Utilization Summary */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="pb-2 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Cluster Resource Utilization</h3>
            <p className="text-xs text-slate-500">Container CPU & Memory relative to allocations</p>
          </div>

          <div className="space-y-4">
            {/* CPU Bar */}
            <div>
              <div className="flex justify-between items-center text-xs mb-1">
                <span className="text-slate-600 font-semibold flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-indigo-600" /> CPU Allocation
                </span>
                <span className="font-mono text-slate-900 font-bold">{s.cpu_usage_display || '0m / 0m'}</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, s.cpu_utilization_pct || 0)}%` }}
                />
              </div>
              <div className="text-right text-[10px] text-slate-400 font-mono mt-0.5">{s.cpu_utilization_pct ?? 0}% utilization</div>
            </div>

            {/* Memory Bar */}
            <div>
              <div className="flex justify-between items-center text-xs mb-1">
                <span className="text-slate-600 font-semibold flex items-center gap-1.5">
                  <HardDrive className="w-3.5 h-3.5 text-purple-600" /> Memory Allocation
                </span>
                <span className="font-mono text-slate-900 font-bold">{s.memory_usage_display || '0Mi / 0Mi'}</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-purple-600 h-2.5 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, s.memory_utilization_pct || 0)}%` }}
                />
              </div>
              <div className="text-right text-[10px] text-slate-400 font-mono mt-0.5">{s.memory_utilization_pct ?? 0}% utilization</div>
            </div>

            {/* Status note */}
            <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 text-xs text-slate-600 space-y-1">
              <div className="flex items-center gap-1.5 font-bold text-slate-700">
                <Shield className="w-3.5 h-3.5 text-emerald-600" />
                <span>Kubernetes Autoscaler Engine</span>
              </div>
              <p className="text-[11px] text-slate-500">
                Replicas scale automatically on traffic bursts and collapse to 0 after inactivity.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Function Telemetry Leaderboard Table */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Per-Function Telemetry Leaderboard</h3>
            <p className="text-xs text-slate-500">Performance, latency percentiles, and replica state across all deployed functions</p>
          </div>
        </div>

        <div className="overflow-x-auto border border-slate-200 rounded-xl">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
              <tr>
                <th className="px-4 py-3">Function</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Invocations</th>
                <th className="px-4 py-3">Success Rate</th>
                <th className="px-4 py-3">p50 Latency</th>
                <th className="px-4 py-3">p99 Latency</th>
                <th className="px-4 py-3">Replicas</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {breakdown.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                    No active function invocations logged in this time range.
                  </td>
                </tr>
              ) : (
                breakdown.map((fn: any) => (
                  <tr key={fn.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3 font-sans">
                      <div className="font-bold text-slate-900 font-mono">{fn.name}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{fn.public_id}</div>
                    </td>
                    <td className="px-4 py-3 font-sans">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                        fn.status === 'RUNNING' || fn.status === 'READY'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : fn.status === 'SCALED_TO_ZERO'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-slate-100 text-slate-600 border-slate-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          fn.status === 'RUNNING' || fn.status === 'READY'
                            ? 'bg-emerald-500'
                            : fn.status === 'SCALED_TO_ZERO'
                            ? 'bg-amber-500'
                            : 'bg-slate-400'
                        }`} />
                        {fn.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-800">{fn.total_invocations}</td>
                    <td className="px-4 py-3">
                      <span className={fn.success_rate_pct < 95 ? 'text-rose-600 font-bold' : 'text-emerald-700 font-bold'}>
                        {fn.success_rate_pct}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sky-700 font-semibold">{fn.p50_latency_ms} ms</td>
                    <td className="px-4 py-3 text-rose-700 font-semibold">{fn.p99_latency_ms} ms</td>
                    <td className="px-4 py-3 text-slate-900 font-bold">{fn.active_replicas} pod(s)</td>
                    <td className="px-4 py-3 text-right font-sans">
                      <button
                        onClick={() => onSelectFunction(fn.public_id)}
                        className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/70 rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition cursor-pointer"
                      >
                        <span>Deep Dive</span>
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Platform Scaling Operations Timeline */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
        <div className="pb-2 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">Recent Platform Autoscaling Operations</h3>
          <p className="text-xs text-slate-500">Audit trail of scale-up, scale-down, and scale-to-zero controller actions</p>
        </div>

        <div className="overflow-x-auto border border-slate-200 rounded-xl">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Timestamp</th>
                <th className="px-4 py-2.5">Function</th>
                <th className="px-4 py-2.5">Action</th>
                <th className="px-4 py-2.5">Replica Transition</th>
                <th className="px-4 py-2.5">Trigger / Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {scalingEvents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400 font-sans font-medium">
                    No autoscaling events recorded in memory buffer yet.
                  </td>
                </tr>
              ) : (
                scalingEvents.slice(0, 15).map((ev: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-2.5 text-slate-500 font-sans">
                      {formatTime(ev.timestamp)}
                    </td>
                    <td className="px-4 py-2.5 font-bold text-slate-800">{ev.function_name}</td>
                    <td className="px-4 py-2.5 font-sans">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                        ev.direction === 'UP'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}>
                        {ev.direction === 'UP' ? <ArrowUp className="w-3 h-3 text-emerald-600" /> : <ArrowDown className="w-3 h-3 text-amber-600" />}
                        {ev.direction === 'UP' ? 'SCALE UP' : 'SCALE DOWN'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-900 font-semibold">
                      {ev.from_replicas} &rarr; {ev.to_replicas} pods
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 font-sans text-xs">{ev.reason}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// 2. PER-FUNCTION COMPREHENSIVE OBSERVABILITY SECTION
// ============================================================================

function FunctionObservabilitySection({
  data,
  history,
  loading,
  timeRange,
  activeSubTab,
  setActiveSubTab,
  expandedLogId,
  setExpandedLogId,
  copiedField,
  copyText,
  formatJson,
  onSelectFunctionToInvoke
}: {
  data: any;
  history: any[];
  loading: boolean;
  timeRange: string;
  activeSubTab: 'charts' | 'pods' | 'scaling' | 'versions' | 'history';
  setActiveSubTab: (tab: 'charts' | 'pods' | 'scaling' | 'versions' | 'history') => void;
  expandedLogId: number | null;
  setExpandedLogId: (id: number | null) => void;
  copiedField: string | null;
  copyText: (text: string, id: string) => void;
  formatJson: (val: any) => string;
  onSelectFunctionToInvoke?: (name: string) => void;
}) {
  if (!data && loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
        <span className="text-sm font-semibold">Loading function telemetry & metrics...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-500">
        Please select a valid deployed function to inspect telemetry.
      </div>
    );
  }

  const fn = data.function || {};
  const inv = data.invocation_metrics || {};
  const perf = data.performance_metrics || {};
  const scale = data.scaling_metrics || {};
  const res = data.resource_metrics || {};
  const rel = data.reliability_and_deployment || {};
  const timeSeries = data.time_series || [];

  return (
    <div className="space-y-6">
      {/* Function Overview Banner */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h2 className="text-xl font-bold text-slate-900 font-mono tracking-tight">{fn.name}</h2>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border flex items-center gap-1.5 ${
              fn.status === 'RUNNING' || fn.status === 'READY'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : fn.status === 'SCALED_TO_ZERO'
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : 'bg-slate-100 text-slate-700 border-slate-200'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                fn.status === 'RUNNING' || fn.status === 'READY' ? 'bg-emerald-500' : 'bg-amber-500'
              }`} />
              {fn.status}
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs font-mono font-semibold">
              {fn.runtime}
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono flex-wrap">
            <span>Stable ID: <strong className="text-slate-700">{fn.public_id}</strong></span>
            <button
              onClick={() => copyText(fn.public_id, 'fn_id')}
              className="hover:text-indigo-600 transition cursor-pointer"
              title="Copy stable function ID"
            >
              {copiedField === 'fn_id' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
            <span className="text-slate-300">•</span>
            <span>Limits: {fn.memory_limit} / {fn.cpu_limit}</span>
            <span className="text-slate-300">•</span>
            <span>Timeout: {fn.timeout_seconds}s</span>
          </div>
        </div>

        {onSelectFunctionToInvoke && (
          <button
            onClick={() => onSelectFunctionToInvoke(fn.name)}
            className="self-start md:self-auto flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Test & Invoke Function</span>
          </button>
        )}
      </div>

      {/* 6 Per-Function Summary KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        {/* Invocations */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Invocations</span>
            <Activity className="w-3.5 h-3.5 text-indigo-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
            {inv.total_invocations ?? 0}
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Succ: <strong className="text-emerald-600">{inv.successful_invocations ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>Err: <strong className="text-rose-600">{inv.failed_invocations ?? 0}</strong></span>
          </div>
        </div>

        {/* Latency p50 / Avg */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Median Latency (p50)</span>
            <Clock className="w-3.5 h-3.5 text-sky-600" />
          </div>
          <div className="text-2xl font-black text-sky-700 tracking-tight font-mono">
            {perf.p50_latency_ms ?? 0} <span className="text-xs font-normal text-slate-400">ms</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1 font-mono">
            <span>Avg: <strong>{perf.avg_latency_ms ?? 0}ms</strong></span>
            <span className="text-slate-300">•</span>
            <span>p99: <strong className="text-rose-600">{perf.p99_latency_ms ?? 0}ms</strong></span>
          </div>
        </div>

        {/* Cold Starts & Provisioning */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Cold Starts</span>
            <Zap className="w-3.5 h-3.5 text-amber-600" />
          </div>
          <div className="text-2xl font-black text-amber-700 tracking-tight font-mono">
            {perf.cold_start_count ?? 0} <span className="text-xs font-normal text-slate-400">({perf.cold_start_percentage ?? 0}%)</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Provisioning: <strong>{perf.avg_provisioning_duration_ms ?? 0}ms</strong></span>
          </div>
        </div>

        {/* Scaling State */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Replicas & Bounds</span>
            <Server className="w-3.5 h-3.5 text-indigo-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
            {scale.current_replicas ?? 0} <span className="text-xs font-normal text-slate-400">({scale.min_replicas}-{scale.max_replicas})</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>Ready: <strong>{scale.ready_replicas ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>Target: <strong>{scale.target_concurrency ?? 5} req</strong></span>
          </div>
        </div>

        {/* Pod Restarts & OOM Kills */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Pod Health & OOM</span>
            <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight font-mono flex items-center gap-1.5">
            <span className={res.pod_restarts > 0 ? 'text-amber-600' : 'text-slate-900'}>{res.pod_restarts ?? 0}</span>
            <span className="text-xs font-normal text-slate-400">restarts</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>OOM Kills: <strong className={res.oom_kills > 0 ? 'text-rose-600' : 'text-slate-700'}>{res.oom_kills ?? 0}</strong></span>
          </div>
        </div>

        {/* In-Flight & Rate */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
            <span>Demand & Rate</span>
            <Activity className="w-3.5 h-3.5 text-purple-600" />
          </div>
          <div className="text-2xl font-black text-purple-700 tracking-tight font-mono">
            {inv.in_flight_requests ?? 0} <span className="text-xs font-normal text-slate-400">active</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-1">
            <span>RPS: <strong>{inv.invocation_rate_rps ?? 0}</strong></span>
            <span className="text-slate-300">•</span>
            <span>Timeouts: <strong className="text-amber-600">{inv.timeout_count ?? 0}</strong></span>
          </div>
        </div>
      </div>

      {/* Function Sub-Tabs Pill Navigation */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-1.5 shadow-2xs flex items-center gap-1 overflow-x-auto">
        <button
          onClick={() => setActiveSubTab('charts')}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
            activeSubTab === 'charts'
              ? 'bg-indigo-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5" />
          <span>Metrics Charts</span>
        </button>

        <button
          onClick={() => setActiveSubTab('pods')}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
            activeSubTab === 'pods'
              ? 'bg-indigo-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>Pods & Resources ({res.pods?.length ?? 0})</span>
        </button>

        <button
          onClick={() => setActiveSubTab('scaling')}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
            activeSubTab === 'scaling'
              ? 'bg-indigo-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Server className="w-3.5 h-3.5" />
          <span>Scaling & Events</span>
        </button>

        <button
          onClick={() => setActiveSubTab('versions')}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
            activeSubTab === 'versions'
              ? 'bg-indigo-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Shield className="w-3.5 h-3.5" />
          <span>Deployments & Versions ({rel.versions?.length ?? 0})</span>
        </button>

        <button
          onClick={() => setActiveSubTab('history')}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
            activeSubTab === 'history'
              ? 'bg-indigo-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Clock className="w-3.5 h-3.5" />
          <span>Invocation Telemetry ({history.length})</span>
        </button>
      </div>

      {/* Sub-Tab 1: Metrics Charts */}
      {activeSubTab === 'charts' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900 tracking-tight">Invocation Rate & Error Distribution</h3>
                <p className="text-xs text-slate-500">Total requests and errors for {fn.name}</p>
              </div>
              <div className="flex items-center gap-3 text-xs font-semibold">
                <span className="flex items-center gap-1 text-slate-700">
                  <span className="w-2.5 h-2.5 rounded-sm bg-indigo-500" /> Invocations
                </span>
                <span className="flex items-center gap-1 text-rose-700">
                  <span className="w-2.5 h-2.5 rounded-sm bg-rose-500" /> Errors
                </span>
              </div>
            </div>
            <SimpleTimeSeriesBarChart data={timeSeries} valueKey="invocations" errorKey="errors" height={220} />
          </div>

          <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900 tracking-tight">Execution Latency Percentiles (p50, p95, p99)</h3>
                <p className="text-xs text-slate-500">Latency milestones in milliseconds</p>
              </div>
              <div className="flex items-center gap-3 text-[11px] font-semibold">
                <span className="flex items-center gap-1 text-sky-700"><span className="w-2 h-2 rounded-full bg-sky-500" /> p50</span>
                <span className="flex items-center gap-1 text-amber-700"><span className="w-2 h-2 rounded-full bg-amber-500" /> p95</span>
                <span className="flex items-center gap-1 text-rose-700"><span className="w-2 h-2 rounded-full bg-rose-500" /> p99</span>
              </div>
            </div>
            <MultiLineLatencyChart data={timeSeries} height={220} />
          </div>
        </div>
      )}

      {/* Sub-Tab 2: Pods & Resource Details */}
      {activeSubTab === 'pods' && (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Kubernetes Pod Instances</h3>
              <p className="text-xs text-slate-500">Associated containers serving traffic for this function key</p>
            </div>
            <span className="text-xs font-mono font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg">
              {res.k8s_available ? 'Cluster Connected' : 'Standalone Sandbox Mode'}
            </span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Pod Name</th>
                  <th className="px-4 py-3">Phase</th>
                  <th className="px-4 py-3">Ready</th>
                  <th className="px-4 py-3">Restarts</th>
                  <th className="px-4 py-3">OOM Killed</th>
                  <th className="px-4 py-3">Node / IP</th>
                  <th className="px-4 py-3">CPU Limit</th>
                  <th className="px-4 py-3">Memory Limit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {!res.pods || res.pods.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                      {res.k8s_available
                        ? (fn.active_replicas === 0 ? 'Function is currently scaled to 0 replicas (No active pods).' : 'No pods currently running.')
                        : 'Kubernetes cluster is not connected. Function runs via local isolated sandbox.'}
                    </td>
                  </tr>
                ) : (
                  res.pods.map((p: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                      <td className="px-4 py-3 font-bold text-slate-800">{p.name}</td>
                      <td className="px-4 py-3 font-sans">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          p.phase === 'Running' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                        }`}>
                          {p.phase}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {p.ready ? (
                          <span className="text-emerald-600 font-bold flex items-center gap-1 font-sans">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Ready
                          </span>
                        ) : (
                          <span className="text-amber-600 font-bold flex items-center gap-1 font-sans">
                            <Clock className="w-3.5 h-3.5" /> Pending
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-semibold">{p.restarts}</td>
                      <td className="px-4 py-3">
                        {p.oom_killed ? (
                          <span className="text-rose-600 font-bold font-sans">OOM Killed</span>
                        ) : (
                          <span className="text-slate-400 font-sans">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 font-sans text-xs">
                        {p.node || 'unknown-node'} / {p.ip || 'no-ip'}
                      </td>
                      <td className="px-4 py-3 font-bold">{p.cpu_limit_millicores}m</td>
                      <td className="px-4 py-3 font-bold">{p.memory_limit_mb}Mi</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sub-Tab 3: Autoscaling & Events */}
      {activeSubTab === 'scaling' && (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Autoscaling Parameters & Event Log</h3>
              <p className="text-xs text-slate-500">Configured bounds and historical scale-up/scale-down operations</p>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono font-semibold">
              <span>Min: <strong className="text-slate-800">{scale.min_replicas}</strong></span>
              <span>Max: <strong className="text-slate-800">{scale.max_replicas}</strong></span>
              <span>Target: <strong className="text-slate-800">{scale.target_concurrency} req/pod</strong></span>
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Direction</th>
                  <th className="px-4 py-3">Transition</th>
                  <th className="px-4 py-3">Reason / Autoscaler Trigger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {!scale.recent_scaling_events || scale.recent_scaling_events.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                      No autoscaling events recorded for this function yet.
                    </td>
                  </tr>
                ) : (
                  scale.recent_scaling_events.map((ev: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                      <td className="px-4 py-3 font-sans text-slate-500">
                        {formatTime(ev.timestamp)}
                      </td>
                      <td className="px-4 py-3 font-sans">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[10px] font-bold ${
                          ev.direction === 'UP'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {ev.direction === 'UP' ? <ArrowUp className="w-3 h-3 text-emerald-600" /> : <ArrowDown className="w-3 h-3 text-amber-600" />}
                          {ev.direction === 'UP' ? 'SCALE UP' : 'SCALE DOWN'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-900 font-bold">
                        {ev.from_replicas} &rarr; {ev.to_replicas} pods
                      </td>
                      <td className="px-4 py-3 text-slate-600 font-sans text-xs">{ev.reason}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sub-Tab 4: Deployments & Versions */}
      {activeSubTab === 'versions' && (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="pb-2 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Deployment & Image Build History</h3>
            <p className="text-xs text-slate-500">Track container packaging duration, deployment rollout time, and build statuses</p>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Version Tag</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Active (Routable)</th>
                  <th className="px-4 py-3">Image Tag</th>
                  <th className="px-4 py-3">Build Duration</th>
                  <th className="px-4 py-3">Deploy Duration</th>
                  <th className="px-4 py-3">Deployed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {!rel.versions || rel.versions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                      No deployed versions found for this function.
                    </td>
                  </tr>
                ) : (
                  rel.versions.map((ver: any) => (
                    <tr key={ver.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="px-4 py-3 font-bold text-slate-900">{ver.version_tag}</td>
                      <td className="px-4 py-3 font-sans">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          ver.status === 'READY'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : ver.status === 'BUILDING'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200 animate-pulse'
                            : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}>
                          {ver.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-sans">
                        {ver.is_active ? (
                          <span className="text-emerald-700 font-bold flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Active
                          </span>
                        ) : (
                          <span className="text-slate-400">Inactive</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 max-w-xs truncate" title={ver.image_tag}>
                        {ver.image_tag}
                      </td>
                      <td className="px-4 py-3 text-indigo-700 font-semibold">{ver.build_duration_ms || 0} ms</td>
                      <td className="px-4 py-3 text-purple-700 font-semibold">{ver.deploy_duration_ms || 0} ms</td>
                      <td className="px-4 py-3 font-sans text-slate-500">
                        {formatDateTime(ver.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sub-Tab 5: Per-Function Invocation Telemetry History */}
      {activeSubTab === 'history' && (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="pb-2 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Per-Function Invocation Telemetry Records</h3>
            <p className="text-xs text-slate-500">Click any row to inspect incoming JSON request payload and returned output</p>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Request ID</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Cold Start</th>
                  <th className="px-4 py-3">Execution</th>
                  <th className="px-4 py-3">Total Latency</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                      No invocations recorded for this function yet.
                    </td>
                  </tr>
                ) : (
                  history.map((log) => {
                    const isExpanded = expandedLogId === log.id;
                    return (
                      <React.Fragment key={log.id}>
                        <tr
                          onClick={() => setExpandedLogId(isExpanded ? null : log.id)}
                          className={`cursor-pointer transition-colors ${
                            isExpanded ? 'bg-indigo-50/60 hover:bg-indigo-50/80' : 'hover:bg-slate-50/80'
                          }`}
                          title="Click to view request JSON & output"
                        >
                          <td className="px-4 py-3 font-sans text-slate-600 font-medium">
                            {formatTime(log.timestamp)}
                          </td>
                          <td className="px-4 py-3 text-slate-800 font-semibold">
                            <div className="flex items-center gap-1.5">
                              <ChevronRight className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isExpanded ? 'rotate-90 text-indigo-600' : ''}`} />
                              <span>{log.request_id.slice(0, 8)}...</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 font-sans">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                              log.is_cold_start ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            }`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${log.is_cold_start ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                              {log.is_cold_start ? 'COLD' : 'WARM'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-amber-600 font-semibold">{log.cold_start_duration_ms} ms</td>
                          <td className="px-4 py-3 text-emerald-600 font-semibold">{log.execution_duration_ms} ms</td>
                          <td className="px-4 py-3 text-slate-900 font-bold">{log.total_duration_ms} ms</td>
                          <td className="px-4 py-3 font-sans">
                            <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                              log.status_code === 200 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}>
                              {log.status_code}
                            </span>
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr className="bg-slate-900 border-y border-slate-800 text-slate-100">
                            <td colSpan={7} className="p-4 sm:p-5">
                              <div className="space-y-4">
                                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800 text-xs">
                                  <div className="flex items-center gap-2 font-mono">
                                    <span className="text-slate-400">Request:</span>
                                    <span className="text-slate-200 select-all font-semibold">{log.request_id}</span>
                                    <span className="text-slate-600">•</span>
                                    <span className="text-slate-400">{formatDateTime(log.timestamp)}</span>
                                  </div>
                                  <span className="text-xs text-indigo-300 font-sans">Click row to collapse</span>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                  <div className="bg-slate-950/90 rounded-xl overflow-hidden border border-slate-800">
                                    <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900 border-b border-slate-800">
                                      <span className="text-[11px] font-mono font-semibold text-slate-300">Incoming Request JSON</span>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          copyText(formatJson(log.payload_input), `hist_in_${log.id}`);
                                        }}
                                        className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1 cursor-pointer"
                                      >
                                        {copiedField === `hist_in_${log.id}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                        <span>Copy</span>
                                      </button>
                                    </div>
                                    <pre className="p-3 text-xs font-mono text-sky-200 whitespace-pre-wrap break-all max-h-60 overflow-y-auto">
                                      {formatJson(log.payload_input) || '(empty)'}
                                    </pre>
                                  </div>

                                  <div className="bg-slate-950/90 rounded-xl overflow-hidden border border-slate-800">
                                    <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900 border-b border-slate-800">
                                      <span className="text-[11px] font-mono font-semibold text-slate-300">Execution Output JSON</span>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          copyText(formatJson(log.payload_output), `hist_out_${log.id}`);
                                        }}
                                        className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1 cursor-pointer"
                                      >
                                        {copiedField === `hist_out_${log.id}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                        <span>Copy</span>
                                      </button>
                                    </div>
                                    <pre className="p-3 text-xs font-mono text-emerald-300 whitespace-pre-wrap break-all max-h-60 overflow-y-auto">
                                      {formatJson(log.payload_output) || '(no output)'}
                                    </pre>
                                  </div>
                                </div>

                                {log.error_message && (
                                  <div className="bg-rose-950/50 border border-rose-900/80 rounded-xl p-3 text-xs">
                                    <div className="text-rose-400 font-mono font-bold mb-1">Error Trace:</div>
                                    <pre className="font-mono text-rose-200 whitespace-pre-wrap break-all">
                                      {log.error_message}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// 3. RESPONSIVE SVG CHARTS
// ============================================================================

function SimpleTimeSeriesBarChart({
  data,
  valueKey = 'invocations',
  errorKey = 'errors',
  height = 200
}: {
  data: any[];
  valueKey?: string;
  errorKey?: string;
  height?: number;
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-slate-400 text-xs font-medium">
        No time series telemetry available for this window.
      </div>
    );
  }

  const maxVal = Math.max(1, ...data.map((d) => d[valueKey] || 0));
  const svgWidth = 600;
  const paddingX = 40;
  const paddingY = 24;
  const chartWidth = svgWidth - paddingX * 2;
  const chartHeight = height - paddingY * 2;
  const barWidth = Math.max(4, Math.floor(chartWidth / data.length) - 3);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${svgWidth} ${height}`}
        className="w-full h-auto overflow-visible select-none"
        preserveAspectRatio="none"
      >
        {/* Horizontal Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((frac, i) => {
          const y = paddingY + chartHeight * (1 - frac);
          const labelVal = Math.round(maxVal * frac);
          return (
            <g key={i}>
              <line
                x1={paddingX}
                y1={y}
                x2={svgWidth - paddingX}
                y2={y}
                stroke="#f1f5f9"
                strokeWidth="1"
                strokeDasharray={frac === 0 ? undefined : '3 3'}
              />
              <text
                x={paddingX - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-slate-400 text-[9px] font-mono"
              >
                {labelVal}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {data.map((d, i) => {
          const x = paddingX + (i * chartWidth) / data.length + (chartWidth / data.length - barWidth) / 2;
          const val = d[valueKey] || 0;
          const err = d[errorKey] || 0;
          const totalHeight = (val / maxVal) * chartHeight;
          const errHeight = (err / maxVal) * chartHeight;
          const successHeight = Math.max(0, totalHeight - errHeight);

          const yBase = paddingY + chartHeight;
          const ySuccess = yBase - totalHeight;
          const isHovered = hoveredIdx === i;

          return (
            <g
              key={i}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              className="cursor-pointer"
            >
              {/* Background hover highlight */}
              {isHovered && (
                <rect
                  x={x - 2}
                  y={paddingY}
                  width={barWidth + 4}
                  height={chartHeight}
                  fill="#e0e7ff"
                  opacity="0.4"
                  rx="3"
                />
              )}

              {/* Success bar segment */}
              {successHeight > 0 && (
                <rect
                  x={x}
                  y={yBase - successHeight}
                  width={barWidth}
                  height={successHeight}
                  fill={isHovered ? '#4f46e5' : '#6366f1'}
                  rx="2"
                />
              )}

              {/* Error bar segment */}
              {errHeight > 0 && (
                <rect
                  x={x}
                  y={ySuccess}
                  width={barWidth}
                  height={errHeight}
                  fill="#f43f5e"
                  rx="2"
                />
              )}
            </g>
          );
        })}
      </svg>

      {/* Hover tooltip */}
      {hoveredIdx !== null && data[hoveredIdx] && (
        <div className="absolute top-2 right-4 bg-slate-900/95 text-white text-[11px] p-2 rounded-lg shadow-lg font-mono pointer-events-none z-10 space-y-0.5">
          <div className="font-bold text-slate-300 font-sans border-b border-slate-700 pb-0.5 mb-1">
            {data[hoveredIdx].time_label}
          </div>
          <div className="text-indigo-300">Total: {data[hoveredIdx][valueKey]}</div>
          <div className="text-emerald-400">Success: {data[hoveredIdx].successes}</div>
          <div className="text-rose-400">Errors: {data[hoveredIdx].errors}</div>
          <div className="text-slate-400">RPS: {data[hoveredIdx].rps}</div>
        </div>
      )}
    </div>
  );
}

function MultiLineLatencyChart({
  data,
  height = 200
}: {
  data: any[];
  height?: number;
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-slate-400 text-xs font-medium">
        No latency data recorded in this period.
      </div>
    );
  }

  const maxVal = Math.max(10, ...data.map((d) => Math.max(d.p50_latency_ms || 0, d.p95_latency_ms || 0, d.p99_latency_ms || 0)));
  const svgWidth = 600;
  const paddingX = 40;
  const paddingY = 24;
  const chartWidth = svgWidth - paddingX * 2;
  const chartHeight = height - paddingY * 2;

  const getPoints = (key: string) => {
    return data.map((d, i) => {
      const x = paddingX + (i * chartWidth) / Math.max(1, data.length - 1);
      const y = paddingY + chartHeight * (1 - (d[key] || 0) / maxVal);
      return `${x},${y}`;
    }).join(' ');
  };

  const pointsP50 = getPoints('p50_latency_ms');
  const pointsP95 = getPoints('p95_latency_ms');
  const pointsP99 = getPoints('p99_latency_ms');

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${svgWidth} ${height}`}
        className="w-full h-auto overflow-visible select-none"
        preserveAspectRatio="none"
      >
        {/* Horizontal Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((frac, i) => {
          const y = paddingY + chartHeight * (1 - frac);
          const labelVal = Math.round(maxVal * frac);
          return (
            <g key={i}>
              <line
                x1={paddingX}
                y1={y}
                x2={svgWidth - paddingX}
                y2={y}
                stroke="#f1f5f9"
                strokeWidth="1"
                strokeDasharray={frac === 0 ? undefined : '3 3'}
              />
              <text
                x={paddingX - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-slate-400 text-[9px] font-mono"
              >
                {labelVal}ms
              </text>
            </g>
          );
        })}

        {/* p99 Line */}
        <polyline
          fill="none"
          stroke="#f43f5e"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={pointsP99}
        />

        {/* p95 Line */}
        <polyline
          fill="none"
          stroke="#f59e0b"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={pointsP95}
        />

        {/* p50 Line */}
        <polyline
          fill="none"
          stroke="#0284c7"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={pointsP50}
        />

        {/* Invisible interactive vertical slices for hover */}
        {data.map((d, i) => {
          const x = paddingX + (i * chartWidth) / Math.max(1, data.length - 1);
          return (
            <rect
              key={i}
              x={x - 10}
              y={paddingY}
              width={20}
              height={chartHeight}
              fill="transparent"
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              className="cursor-pointer"
            />
          );
        })}
      </svg>

      {hoveredIdx !== null && data[hoveredIdx] && (
        <div className="absolute top-2 right-4 bg-slate-900/95 text-white text-[11px] p-2.5 rounded-lg shadow-lg font-mono pointer-events-none z-10 space-y-0.5">
          <div className="font-bold text-slate-300 font-sans border-b border-slate-700 pb-0.5 mb-1">
            {data[hoveredIdx].time_label}
          </div>
          <div className="text-sky-300">p50: {data[hoveredIdx].p50_latency_ms} ms</div>
          <div className="text-amber-300">p95: {data[hoveredIdx].p95_latency_ms} ms</div>
          <div className="text-rose-400">p99: {data[hoveredIdx].p99_latency_ms} ms</div>
          <div className="text-slate-400">Avg: {data[hoveredIdx].avg_latency_ms} ms</div>
        </div>
      )}
    </div>
  );
}

function ColdWarmStackedChart({
  data,
  height = 180
}: {
  data: any[];
  height?: number;
}) {
  if (!data || data.length === 0) {
    return (
      <div className="h-[180px] flex items-center justify-center text-slate-400 text-xs font-medium">
        No cold/warm invocations recorded.
      </div>
    );
  }

  const maxVal = Math.max(1, ...data.map((d) => (d.cold_starts || 0) + (d.warm_starts || 0)));
  const svgWidth = 600;
  const paddingX = 35;
  const paddingY = 20;
  const chartWidth = svgWidth - paddingX * 2;
  const chartHeight = height - paddingY * 2;
  const barWidth = Math.max(4, Math.floor(chartWidth / data.length) - 3);

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${height}`}
      className="w-full h-auto overflow-visible select-none"
      preserveAspectRatio="none"
    >
      {[0, 0.5, 1.0].map((frac, i) => {
        const y = paddingY + chartHeight * (1 - frac);
        const labelVal = Math.round(maxVal * frac);
        return (
          <g key={i}>
            <line x1={paddingX} y1={y} x2={svgWidth - paddingX} y2={y} stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
            <text x={paddingX - 6} y={y + 3} textAnchor="end" className="fill-slate-400 text-[9px] font-mono">{labelVal}</text>
          </g>
        );
      })}

      {data.map((d, i) => {
        const x = paddingX + (i * chartWidth) / data.length + (chartWidth / data.length - barWidth) / 2;
        const cold = d.cold_starts || 0;
        const warm = d.warm_starts || 0;
        const total = cold + warm;
        const coldH = (cold / maxVal) * chartHeight;
        const warmH = (warm / maxVal) * chartHeight;
        const yBase = paddingY + chartHeight;

        return (
          <g key={i}>
            {warmH > 0 && (
              <rect x={x} y={yBase - warmH} width={barWidth} height={warmH} fill="#10b981" rx="1.5" />
            )}
            {coldH > 0 && (
              <rect x={x} y={yBase - warmH - coldH} width={barWidth} height={coldH} fill="#f59e0b" rx="1.5" />
            )}
          </g>
        );
      })}
    </svg>
  );
}
