import React, { useState, useEffect, useRef, useMemo } from 'react';
import axios from 'axios';
import ApiAccessPanel from './ApiAccessPanel';
import { 
  Server, Play, Plus, RefreshCw, Trash2, Clock, Cpu, 
  Database, Activity, Zap, CheckCircle2, AlertCircle, 
  Terminal, BarChart3, Code2, Layers, ShieldCheck, Box,
  Search, ArrowRight, ExternalLink, LogOut, User, Copy,
  Check, Sparkles, Filter, Info, Shield, Radio, Flame,
  Gauge, Sliders, ChevronRight, PlayCircle, HardDrive,
  FileCode, Cpu as CpuIcon
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface FunctionItem {
  id: number;
  name: string;
  public_id: string;
  runtime: string;
  description: string;
  status: string;
  status_message: string;
  memory_limit: string;
  cpu_limit: string;
  timeout_seconds: number;
  active_replicas: number;
  min_replicas: number;
  max_replicas: number;
  target_concurrency: number;
  last_invoked_at: string | null;
  created_at: string;
}

interface InvocationLog {
  id: number;
  request_id: string;
  is_cold_start: boolean;
  cold_start_duration_ms: number;
  execution_duration_ms: number;
  total_duration_ms: number;
  status_code: number;
  payload_input: string;
  payload_output: string;
  error_message: string;
  timestamp: string;
}

interface Stats {
  total_functions: number;
  active_replicas: number;
  scaled_to_zero_count: number;
  total_invocations: number;
  cold_start_count: number;
  warm_invocation_count: number;
  cold_start_ratio_pct: number;
  avg_execution_duration_ms: number;
  avg_cold_start_duration_ms: number;
}

const TEMPLATES = {
  hello: {
    name: 'hello-world',
    desc: 'Basic hello world with event payload parsing',
    code: `def handler(event):
    name = event.get("name", "World")
    return {
        "message": f"Hello, {name} from Serverless FaaS!",
        "status": "success"
    }`
  },
  fibonacci: {
    name: 'fibonacci-calc',
    desc: 'CPU-intensive Fibonacci benchmark calculator',
    code: `def handler(event):
    n = int(event.get("n", 30))
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {
        "n": n,
        "fibonacci_number": a,
        "computed_by": "Python 3.11 Runtime"
    }`
  },
  transform: {
    name: 'json-transformer',
    desc: 'Transforms and filters structured JSON objects',
    code: `def handler(event):
    items = event.get("items", [])
    filtered = [item for item in items if item.get("score", 0) > 50]
    return {
        "total_received": len(items),
        "total_filtered": len(filtered),
        "results": filtered
    }`
  }
};

const getSamplePayload = (fnName: string): string => {
  const name = fnName.toLowerCase();
  if (name.includes('hello')) {
    return '{\n  "name": "Developer"\n}';
  }
  if (name.includes('double') || name.includes('calc-double')) {
    return '{\n  "x": 21\n}';
  }
  if (name.includes('multiplier')) {
    return '{\n  "a": 6,\n  "b": 7\n}';
  }
  if (name.includes('fib') || name.includes('bench') || name.includes('calc')) {
    return '{\n  "n": 25\n}';
  }
  if (name.includes('transform')) {
    return '{\n  "items": [\n    {"id": 1, "score": 85},\n    {"id": 2, "score": 30}\n  ]\n}';
  }
  return '{\n  "name": "Cloud Engineer"\n}';
};

export default function App() {
  const [activeTab, setActiveTab] = useState<'catalog' | 'create' | 'invoke' | 'logs' | 'cluster'>('catalog');
  const [token, setToken] = useState<string | null>(localStorage.getItem('faas_token'));
  const [username, setUsername] = useState<string>(localStorage.getItem('faas_username') || '');
  
  // Auth Form State
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authUsername, setAuthUsername] = useState('demo_dev');
  const [authEmail, setAuthEmail] = useState('demo@faas.io');
  const [authPassword, setAuthPassword] = useState('Password123!');
  const [authError, setAuthError] = useState('');

  // Dashboard Data
  const [functions, setFunctions] = useState<FunctionItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<InvocationLog[]>([]);
  const [clusterStatus, setClusterStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [backendBusy, setBackendBusy] = useState(false);

  // Search & Filters in Catalog
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'RUNNING' | 'SCALED_TO_ZERO' | 'BUILDING'>('ALL');

  // Function Form State
  const [fnName, setFnName] = useState('calc-fibonacci');
  const [fnDesc, setFnDesc] = useState('Calculates fibonacci numbers');
  const [fnRuntime, setFnRuntime] = useState('python311');
  const [fnCode, setFnCode] = useState(TEMPLATES.fibonacci.code);
  const [fnMemory, setFnMemory] = useState('256Mi');
  const [fnCpu, setFnCpu] = useState('500m');
  const [fnTimeout, setFnTimeout] = useState(10);
  const [fnMinReplicas, setFnMinReplicas] = useState(0);
  const [fnMaxReplicas, setFnMaxReplicas] = useState(5);
  const [fnTargetConc, setFnTargetConc] = useState(5);
  const [deployMsg, setDeployMsg] = useState('');

  // Invocation State
  const [selectedFn, setSelectedFn] = useState<string>('');
  const [invokePayload, setInvokePayload] = useState('{\n  "n": 25\n}');
  const [invokeResult, setInvokeResult] = useState<any>(null);
  const [invoking, setInvoking] = useState(false);
  const [copiedRequestId, setCopiedRequestId] = useState(false);
  const [copiedOutput, setCopiedOutput] = useState(false);
  const selectedFnRef = useRef<string>('');
  selectedFnRef.current = selectedFn;

  // Setup Axios Header
  const getHeaders = () => ({
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });

  // Handle Login / Register
  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError('');
    try {
      if (authMode === 'register') {
        const resp = await axios.post(`${API_BASE}/auth/register`, {
          username: authUsername,
          email: authEmail,
          password: authPassword
        });
        localStorage.setItem('faas_token', resp.data.access_token);
        localStorage.setItem('faas_username', resp.data.user.username);
        setToken(resp.data.access_token);
        setUsername(resp.data.user.username);
      } else {
        const formData = new FormData();
        formData.append('username', authUsername);
        formData.append('password', authPassword);
        const resp = await axios.post(`${API_BASE}/auth/login`, formData);
        localStorage.setItem('faas_token', resp.data.access_token);
        localStorage.setItem('faas_username', resp.data.user.username);
        setToken(resp.data.access_token);
        setUsername(resp.data.user.username);
      }
    } catch (err: any) {
      setAuthError(err.response?.data?.detail || 'Authentication failed. Please check your credentials.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('faas_token');
    localStorage.removeItem('faas_username');
    setToken(null);
    setUsername('');
  };

  // Auto create demo account if none exists
  const autoDemoLogin = async () => {
    try {
      const resp = await axios.post(`${API_BASE}/auth/register`, {
        username: 'developer',
        email: 'developer@k8s-faas.io',
        password: 'Password123!'
      });
      localStorage.setItem('faas_token', resp.data.access_token);
      localStorage.setItem('faas_username', resp.data.user.username);
      setToken(resp.data.access_token);
      setUsername(resp.data.user.username);
    } catch {
      const formData = new FormData();
      formData.append('username', 'developer');
      formData.append('password', 'Password123!');
      const resp = await axios.post(`${API_BASE}/auth/login`, formData);
      localStorage.setItem('faas_token', resp.data.access_token);
      localStorage.setItem('faas_username', resp.data.user.username);
      setToken(resp.data.access_token);
      setUsername(resp.data.user.username);
    }
  };

  // Fetch Data
  const fetchData = async () => {
    if (!token) return;
    try {
      setLoading(true);
      // A failed request must not wipe the screen: keep the last data we received and tell the user.
      const [fnRes, statsRes, logsRes, clusterRes] = await Promise.all([
        axios.get(`${API_BASE}/functions/`, getHeaders()).catch(() => null),
        axios.get(`${API_BASE}/stats`, getHeaders()).catch(() => null),
        axios.get(`${API_BASE}/logs/recent`, getHeaders()).catch(() => null),
        axios.get(`${API_BASE}/cluster/status`).catch(() => null)
      ]);
      setBackendBusy(!fnRes || !statsRes || !logsRes || !clusterRes);
      if (fnRes) setFunctions(fnRes.data || []);
      if (statsRes) setStats(statsRes.data || null);
      if (logsRes) setLogs(logsRes.data || []);
      if (clusterRes) setClusterStatus(clusterRes.data || null);
      if (fnRes && fnRes.data?.length > 0 && !selectedFnRef.current) {
        const firstFn = fnRes.data[0].name;
        selectedFnRef.current = firstFn;
        setSelectedFn(firstFn);
        setInvokePayload(getSamplePayload(firstFn));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchData();
      const interval = setInterval(fetchData, 5000);
      return () => clearInterval(interval);
    }
  }, [token]);

  // Deploy Function
  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeployMsg('');
    try {
      setLoading(true);
      await axios.post(`${API_BASE}/functions/`, {
        name: fnName,
        description: fnDesc,
        runtime: fnRuntime,
        code: fnCode,
        memory_limit: fnMemory,
        cpu_limit: fnCpu,
        timeout_seconds: fnTimeout,
        min_replicas: fnMinReplicas,
        max_replicas: fnMaxReplicas,
        target_concurrency: fnTargetConc
      }, getHeaders());
      setDeployMsg(`Success: Function '${fnName}' created and submitted for image build & deployment!`);
      fetchData();
      setTimeout(() => setActiveTab('catalog'), 1500);
    } catch (err: any) {
      setDeployMsg(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Invoke Function
  const handleInvoke = async () => {
    if (!selectedFn) return;
    setInvoking(true);
    setInvokeResult(null);
    try {
      let parsedPayload: any = {};
      const trimmed = (invokePayload || '').trim();
      if (!trimmed) {
        parsedPayload = {};
      } else {
        try {
          parsedPayload = JSON.parse(trimmed);
        } catch {
          // Attempt python dict syntax auto-correction: single quotes -> double quotes, True/False/None
          try {
            const normalized = trimmed
              .replace(/'/g, '"')
              .replace(/\bTrue\b/g, 'true')
              .replace(/\bFalse\b/g, 'false')
              .replace(/\bNone\b/g, 'null');
            parsedPayload = JSON.parse(normalized);
          } catch {
            setInvokeResult({
              error: `Invalid JSON syntax. Ensure keys and strings are enclosed in double quotes (e.g. {"name": "Alice"}).`,
              status_code: 400,
              is_cold_start: false,
              cold_start_duration_ms: 0,
              execution_duration_ms: 0,
              total_duration_ms: 0
            });
            setInvoking(false);
            return;
          }
        }
      }
      const resp = await axios.post(`${API_BASE}/invoke/${selectedFn}`, parsedPayload, getHeaders());
      setInvokeResult(resp.data);
      fetchData();
    } catch (err: any) {
      const errDetail = err.response?.data?.detail;
      const formattedError = typeof errDetail === 'object' ? JSON.stringify(errDetail, null, 2) : (errDetail || err.message);
      setInvokeResult({
        error: formattedError,
        status_code: err.response?.status || 500,
        is_cold_start: false,
        cold_start_duration_ms: 0,
        execution_duration_ms: 0,
        total_duration_ms: 0
      });
    } finally {
      setInvoking(false);
    }
  };

  // Delete Function
  const handleDelete = async (name: string) => {
    if (!confirm(`Are you sure you want to delete function '${name}'?`)) return;
    try {
      await axios.delete(`${API_BASE}/functions/${name}`, getHeaders());
      fetchData();
    } catch (err: any) {
      alert(`Delete error: ${err.response?.data?.detail || err.message}`);
    }
  };

  const copyToClipboard = (text: string, setter: (val: boolean) => void) => {
    navigator.clipboard?.writeText(text);
    setter(true);
    setTimeout(() => setter(false), 2000);
  };

  // Filtered function list
  const filteredFunctions = useMemo(() => {
    return functions.filter((fn) => {
      const matchesSearch = 
        fn.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (fn.description && fn.description.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesStatus = 
        statusFilter === 'ALL' ||
        (statusFilter === 'RUNNING' && (fn.status === 'RUNNING' || fn.status === 'READY')) ||
        (statusFilter === 'SCALED_TO_ZERO' && fn.status === 'SCALED_TO_ZERO') ||
        (statusFilter === 'BUILDING' && fn.status === 'BUILDING');
      return matchesSearch && matchesStatus;
    });
  }, [functions, searchQuery, statusFilter]);

  // Auth Screen (Light Mode Redesign)
  if (!token) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 relative overflow-hidden px-4 py-12">
        {/* Soft background ambient gradient shapes */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-gradient-to-b from-indigo-100/60 via-blue-50/40 to-transparent blur-3xl pointer-events-none" />
        <div className="absolute -bottom-20 -right-20 w-96 h-96 bg-emerald-100/40 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -top-20 -left-20 w-96 h-96 bg-purple-100/40 rounded-full blur-3xl pointer-events-none" />

        <div className="max-w-md w-full relative z-10 space-y-6">
          {/* Logo & Platform Header */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center p-3.5 bg-gradient-to-tr from-indigo-600 to-blue-500 text-white rounded-2xl shadow-lg shadow-indigo-500/25 ring-4 ring-indigo-50">
              <Zap className="w-8 h-8" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              K8s FaaS Platform
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 max-w-xs mx-auto">
              Production-grade Kubernetes Serverless Function Engine with zero-idle cold-start orchestration.
            </p>
          </div>

          {/* Form Card */}
          <div className="bg-white border border-slate-200/90 rounded-2xl p-7 sm:p-8 shadow-[0_12px_32px_rgba(15,23,42,0.06)] backdrop-blur-xl">
            {/* Segmented Tab Bar */}
            <div className="flex p-1 bg-slate-100 rounded-xl mb-6">
              <button
                type="button"
                onClick={() => { setAuthMode('login'); setAuthError(''); }}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                  authMode === 'login'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setAuthMode('register'); setAuthError(''); }}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                  authMode === 'register'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Create Account
              </button>
            </div>

            {authError && (
              <div className="mb-5 p-3.5 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
                <span className="font-medium leading-relaxed">{authError}</span>
              </div>
            )}

            <form onSubmit={handleAuth} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">Username</label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                    placeholder="Enter your username"
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 text-sm transition"
                  />
                </div>
              </div>

              {authMode === 'register' && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">Email Address</label>
                  <input
                    type="email"
                    required
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    placeholder="developer@faas.io"
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 text-sm transition"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">Password</label>
                <input
                  type="password"
                  required
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 text-sm transition"
                />
              </div>

              <button
                type="submit"
                className="w-full mt-2 py-3 bg-indigo-600 hover:bg-indigo-700 active:scale-[0.99] text-white font-semibold rounded-xl transition text-sm shadow-md shadow-indigo-600/20 flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>{authMode === 'login' ? 'Sign In to Cluster' : 'Register Account'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            {/* Quick Demo Login Option */}
            <div className="mt-6 pt-5 border-t border-slate-100">
              <button
                type="button"
                onClick={autoDemoLogin}
                className="w-full py-2.5 px-4 bg-slate-50 hover:bg-slate-100/90 active:bg-slate-150 border border-slate-200/90 rounded-xl text-xs font-semibold text-slate-700 flex items-center justify-center gap-2 transition cursor-pointer"
              >
                <Sparkles className="w-4 h-4 text-indigo-600" />
                <span>1-Click Demo Developer Login</span>
              </button>
              <p className="text-[11px] text-center text-slate-400 mt-2">
                Instant access with preloaded demo credentials.
              </p>
            </div>
          </div>

          {/* Architecture trust badges */}
          <div className="grid grid-cols-3 gap-2 text-center text-[11px] text-slate-500">
            <div className="p-2 bg-white/70 rounded-lg border border-slate-200/60 shadow-2xs">
              <span className="font-semibold text-slate-700 block">K8s Native</span>
              <span>Isolated Namespaces</span>
            </div>
            <div className="p-2 bg-white/70 rounded-lg border border-slate-200/60 shadow-2xs">
              <span className="font-semibold text-slate-700 block">Scale-to-Zero</span>
              <span>60s Idle Reaper</span>
            </div>
            <div className="p-2 bg-white/70 rounded-lg border border-slate-200/60 shadow-2xs">
              <span className="font-semibold text-slate-700 block">Prometheus</span>
              <span>Exported Telemetry</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col antialiased">
      {/* Top Navbar */}
      <header className="glass-header border-b border-slate-200/80 sticky top-0 z-40 px-4 sm:px-8 py-3 flex items-center justify-between shadow-2xs">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-tr from-indigo-600 to-blue-500 rounded-xl text-white flex items-center justify-center shadow-md shadow-indigo-500/20 ring-2 ring-indigo-50">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-slate-900 text-base sm:text-lg tracking-tight">
                K8s FaaS Platform
              </h1>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/70 font-mono font-semibold">
                v1.0.0
              </span>
            </div>
            <p className="text-[11px] text-slate-500 hidden sm:block">Serverless Kubernetes Orchestrator</p>
          </div>
        </div>

        {/* Cluster / System Status Pills */}
        <div className="hidden lg:flex items-center gap-2.5 text-xs">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-slate-200/90 shadow-2xs">
            <span className={`w-2 h-2 rounded-full ${
              clusterStatus?.kubernetes?.status === 'online' 
                ? 'bg-emerald-500 ring-4 ring-emerald-500/20 animate-pulse' 
                : 'bg-amber-500 ring-4 ring-amber-500/20'
            }`} />
            <span className="text-slate-500 font-medium">Cluster:</span>
            <span className="font-semibold text-slate-800">
              {clusterStatus?.kubernetes?.status === 'online' ? 'Connected' : 'Standalone'}
            </span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-slate-200/90 shadow-2xs">
            <span className="w-2 h-2 rounded-full bg-emerald-500 ring-4 ring-emerald-500/20" />
            <span className="text-slate-500 font-medium">Scale-to-Zero:</span>
            <span className="font-semibold text-emerald-700">Active (60s idle)</span>
          </div>
        </div>

        {/* User Account & Actions */}
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200/90 rounded-xl shadow-2xs">
            <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center">
              {username ? username[0].toUpperCase() : 'U'}
            </div>
            <span className="text-xs font-semibold text-slate-800 hidden sm:inline">{username}</span>
          </div>

          <button
            onClick={fetchData}
            title="Refresh State"
            className="p-2 text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-200/90 rounded-xl shadow-2xs transition cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          </button>

          <button
            onClick={handleLogout}
            title="Sign Out"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-slate-200/90 hover:border-rose-200 rounded-xl transition cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Busy / Reconnecting Notice */}
        {backendBusy && (
          <div className="flex items-center gap-2.5 px-4 py-3 bg-amber-50 border border-amber-200/90 rounded-xl text-xs text-amber-800 shadow-2xs animate-in fade-in">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>The backend is busy or reconnecting. Showing cached runtime metrics; retrying automatically in background.</span>
          </div>
        )}
        
        {/* KPI Stat Cards (Light Mode) */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            {/* Card 1 */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-2xs hover:shadow-md transition-all duration-200">
              <div className="flex items-center justify-between text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">
                <span>Functions</span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center border border-blue-100">
                  <Box className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">{stats.total_functions}</div>
              <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500" />
                <span>{stats.scaled_to_zero_count} currently scaled to zero</span>
              </div>
            </div>

            {/* Card 2 */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-2xs hover:shadow-md transition-all duration-200">
              <div className="flex items-center justify-between text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">
                <span>Active Pods</span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100">
                  <Server className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-emerald-600 tracking-tight">{stats.active_replicas}</div>
              <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span>Live container pods ready</span>
              </div>
            </div>

            {/* Card 3 */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-2xs hover:shadow-md transition-all duration-200">
              <div className="flex items-center justify-between text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">
                <span>Invocations</span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
                  <Activity className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">{stats.total_invocations}</div>
              <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                <span className="font-medium text-slate-700">{stats.cold_start_count}</span>
                <span>cold starts ({stats.cold_start_ratio_pct}%)</span>
              </div>
            </div>

            {/* Card 4 */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-2xs hover:shadow-md transition-all duration-200">
              <div className="flex items-center justify-between text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">
                <span>Avg Warm Latency</span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center border border-amber-100">
                  <Clock className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                {stats.avg_execution_duration_ms} <span className="text-xs text-slate-500 font-semibold">ms</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                Cold start avg: <span className="font-semibold text-amber-700">{stats.avg_cold_start_duration_ms} ms</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab Navigation Pill Bar */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-1.5 shadow-2xs flex items-center gap-1 overflow-x-auto">
          <button
            onClick={() => setActiveTab('catalog')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition-all whitespace-nowrap cursor-pointer ${
              activeTab === 'catalog'
                ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Catalog</span>
            <span className={`px-2 py-0.2 rounded-full text-[11px] font-mono ${
              activeTab === 'catalog' ? 'bg-indigo-700 text-white' : 'bg-slate-100 text-slate-700'
            }`}>
              {functions.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('create')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition-all whitespace-nowrap cursor-pointer ${
              activeTab === 'create'
                ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
            }`}
          >
            <Plus className="w-4 h-4" />
            <span>Deploy Function</span>
          </button>

          <button
            onClick={() => setActiveTab('invoke')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition-all whitespace-nowrap cursor-pointer ${
              activeTab === 'invoke'
                ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
            }`}
          >
            <Play className="w-4 h-4" />
            <span>Invocation Console</span>
          </button>

          <button
            onClick={() => setActiveTab('logs')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition-all whitespace-nowrap cursor-pointer ${
              activeTab === 'logs'
                ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
            }`}
          >
            <Terminal className="w-4 h-4" />
            <span>Live Logs</span>
            {logs.length > 0 && (
              <span className={`px-2 py-0.2 rounded-full text-[11px] font-mono ${
                activeTab === 'logs' ? 'bg-indigo-700 text-white' : 'bg-slate-100 text-slate-700'
              }`}>
                {logs.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('cluster')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition-all whitespace-nowrap cursor-pointer ${
              activeTab === 'cluster'
                ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Cluster & Telemetry</span>
          </button>
        </div>

        {/* Tab 1: Catalog */}
        {activeTab === 'catalog' && (
          <div className="space-y-4">
            {/* Catalog Toolbar */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex-1 flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="relative flex-1 max-w-md">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search functions by name or tag..."
                    className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs sm:text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                  />
                </div>

                <div className="flex items-center gap-1.5 flex-wrap">
                  {(['ALL', 'RUNNING', 'SCALED_TO_ZERO', 'BUILDING'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setStatusFilter(mode)}
                      className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                        statusFilter === mode
                          ? 'bg-slate-900 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {mode === 'ALL' ? 'All' : mode === 'RUNNING' ? 'Running' : mode === 'SCALED_TO_ZERO' ? 'Scaled 0' : 'Building'}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={() => setActiveTab('create')}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 active:scale-[0.99] text-white rounded-xl text-xs sm:text-sm font-semibold shadow-sm shadow-indigo-600/20 transition cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>New Function</span>
              </button>
            </div>

            {functions.length === 0 ? (
              <div className="bg-white border border-slate-200/90 rounded-2xl p-12 text-center shadow-2xs">
                <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto mb-4">
                  <Box className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">No functions registered yet</h3>
                <p className="text-slate-500 text-sm max-w-md mx-auto mt-1 mb-6">
                  Deploy your first serverless function to build a Docker container and automatically orchestrate it on Kubernetes with scale-to-zero.
                </p>
                <div className="flex flex-wrap justify-center gap-3">
                  <button
                    onClick={() => {
                      setFnName(TEMPLATES.hello.name);
                      setFnDesc(TEMPLATES.hello.desc);
                      setFnCode(TEMPLATES.hello.code);
                      setActiveTab('create');
                    }}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-semibold transition flex items-center gap-2 cursor-pointer"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    Deploy 'hello-world'
                  </button>
                  <button
                    onClick={() => setActiveTab('create')}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition flex items-center gap-2 cursor-pointer"
                  >
                    <Plus className="w-4 h-4" /> Custom Function
                  </button>
                </div>
              </div>
            ) : filteredFunctions.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center text-slate-500 text-sm">
                No functions matched the filter query '{searchQuery}'.
              </div>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredFunctions.map((fn) => (
                  <div 
                    key={fn.id} 
                    className="bg-white border border-slate-200/90 hover:border-slate-300 rounded-2xl p-5 shadow-2xs transition-card flex flex-col justify-between"
                  >
                    <div>
                      {/* Title & Status */}
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="min-w-0">
                          <h3 className="font-bold text-slate-900 text-base tracking-tight font-mono truncate">
                            {fn.name}
                          </h3>
                        </div>
                        <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-semibold border flex items-center gap-1.5 shrink-0 ${
                          fn.status === 'RUNNING' || fn.status === 'READY'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : fn.status === 'SCALED_TO_ZERO'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : fn.status === 'BUILDING'
                            ? 'bg-blue-50 text-blue-700 border-blue-200 animate-pulse'
                            : 'bg-rose-50 text-rose-700 border-rose-200'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            fn.status === 'RUNNING' || fn.status === 'READY'
                              ? 'bg-emerald-500'
                              : fn.status === 'SCALED_TO_ZERO'
                              ? 'bg-amber-500'
                              : fn.status === 'BUILDING'
                              ? 'bg-blue-500'
                              : 'bg-rose-500'
                          }`} />
                          <span>{fn.status}</span>
                        </span>
                      </div>

                      <p className="text-xs text-slate-500 mb-4 line-clamp-2 min-h-[32px]">
                        {fn.description || 'Standard serverless handler with autoscaling.'}
                      </p>

                      {/* Specs Matrix */}
                      <div className="space-y-2 text-xs text-slate-600 bg-slate-50/90 p-3 rounded-xl border border-slate-200/70 mb-4">
                        <div className="flex justify-between items-center">
                          <span className="text-slate-500 font-medium">Runtime:</span>
                          <span className="font-mono text-slate-800 bg-white px-2 py-0.5 rounded border border-slate-200 text-[11px]">
                            {fn.runtime}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-slate-500 font-medium">Replicas:</span>
                          <span className="text-slate-800 font-medium">
                            {fn.active_replicas} pod{fn.active_replicas === 1 ? '' : 's'}{' '}
                            <span className="text-slate-400 font-normal">({fn.min_replicas}-{fn.max_replicas})</span>
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-slate-500 font-medium">Resources:</span>
                          <span className="text-slate-800 font-mono text-[11px]">{fn.memory_limit} / {fn.cpu_limit}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-slate-500 font-medium">Timeout:</span>
                          <span className="text-slate-800 font-medium">{fn.timeout_seconds}s</span>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                      <button
                        onClick={() => {
                          selectedFnRef.current = fn.name;
                          setSelectedFn(fn.name);
                          setInvokePayload(getSamplePayload(fn.name));
                          setActiveTab('invoke');
                        }}
                        className="px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/70 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>Test & Invoke</span>
                      </button>

                      <button
                        onClick={() => handleDelete(fn.name)}
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                        title="Delete Function"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Create Function */}
        {activeTab === 'create' && (
          <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-2xs space-y-6">
            <div>
              <h2 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
                Create & Deploy Serverless Function
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                Packages user Python code into a standardized Docker container and deploys it to your Kubernetes cluster.
              </p>
            </div>

            {deployMsg && (
              <div className={`p-4 rounded-xl text-xs sm:text-sm border flex items-center gap-3 ${
                deployMsg.startsWith('Error') 
                  ? 'bg-rose-50 border-rose-200 text-rose-800' 
                  : 'bg-emerald-50 border-emerald-200 text-emerald-800'
              }`}>
                {deployMsg.startsWith('Error') ? (
                  <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
                ) : (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                )}
                <span className="font-medium">{deployMsg}</span>
              </div>
            )}

            {/* Template Selector */}
            <div>
              <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider mb-2.5">
                Quick Starter Templates
              </label>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {Object.entries(TEMPLATES).map(([key, t]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      setFnName(t.name);
                      setFnDesc(t.desc);
                      setFnCode(t.code);
                    }}
                    className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer ${
                      fnName === t.name 
                        ? 'bg-indigo-50/80 border-indigo-300 ring-2 ring-indigo-500/20 shadow-2xs' 
                        : 'bg-slate-50/80 hover:bg-slate-100/70 border-slate-200'
                    }`}
                  >
                    <div className="font-bold text-sm text-slate-900 flex items-center justify-between">
                      <span>{t.name}</span>
                      {fnName === t.name && <Check className="w-4 h-4 text-indigo-600" />}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">{t.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleDeploy} className="space-y-6">
              {/* Configuration Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Function Name
                  </label>
                  <input
                    type="text"
                    required
                    value={fnName}
                    onChange={(e) => setFnName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                    placeholder="my-function"
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">Lowercase alphanumeric and dashes only</p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Runtime
                  </label>
                  <select
                    value={fnRuntime}
                    onChange={(e) => setFnRuntime(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                  >
                    <option value="python311">Python 3.11 (Standard Container)</option>
                  </select>
                  <p className="text-[11px] text-slate-400 mt-1">Optimized Debian Slim execution sandbox</p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Memory Limit
                  </label>
                  <select
                    value={fnMemory}
                    onChange={(e) => setFnMemory(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                  >
                    <option value="128Mi">128 MB (Micro - Light logic)</option>
                    <option value="256Mi">256 MB (Standard - Default)</option>
                    <option value="512Mi">512 MB (High Memory)</option>
                    <option value="1024Mi">1024 MB (Max)</option>
                  </select>
                  <p className="text-[11px] text-slate-400 mt-1">Resource limit assigned to pod cgroups</p>
                </div>
              </div>

              {/* Autoscaling Parameters Card */}
              <div className="p-4 bg-slate-50/90 border border-slate-200/90 rounded-2xl space-y-3">
                <div className="flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-indigo-600" />
                  <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Kubernetes Autoscaling & Concurrency Controls
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                      Min Replicas
                    </label>
                    <input 
                      type="number" 
                      min={0} 
                      max={20} 
                      value={fnMinReplicas}
                      onChange={(e) => setFnMinReplicas(Math.max(0, Number(e.target.value)))}
                      className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition" 
                    />
                    <span className="text-[11px] text-slate-400 mt-0.5 block">0 enables scale-to-zero</span>
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                      Max Replicas
                    </label>
                    <input 
                      type="number" 
                      min={1} 
                      max={20} 
                      value={fnMaxReplicas}
                      onChange={(e) => setFnMaxReplicas(Math.max(1, Number(e.target.value)))}
                      className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition" 
                    />
                    <span className="text-[11px] text-slate-400 mt-0.5 block">Upper ceiling for autoscale</span>
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                      Target Concurrency (req/pod)
                    </label>
                    <input 
                      type="number" 
                      min={1} 
                      max={100} 
                      value={fnTargetConc}
                      onChange={(e) => setFnTargetConc(Math.max(1, Number(e.target.value)))}
                      className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition" 
                    />
                    <span className="text-[11px] text-slate-400 mt-0.5 block">Requests before pod scale out</span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Pods are added dynamically when concurrent requests exceed pod targets. Setting min = 0 lets idle functions scale to 0 pods after 60s, keeping infrastructure costs at zero.
                </p>
                {fnMinReplicas > fnMaxReplicas && (
                  <p className="text-[11px] text-rose-600 font-semibold bg-rose-50 border border-rose-200 p-2 rounded-lg">
                    Validation Error: Min replicas ({fnMinReplicas}) must not exceed max replicas ({fnMaxReplicas}).
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                  Description
                </label>
                <input
                  type="text"
                  value={fnDesc}
                  onChange={(e) => setFnDesc(e.target.value)}
                  placeholder="Optional function description and documentation"
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                />
              </div>

              {/* Code Editor Container */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-indigo-600" />
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Source Code (handler.py)
                    </span>
                  </div>
                  <span className="text-xs font-mono text-slate-500 font-semibold">
                    Entrypoint: <code className="text-indigo-600">def handler(event):</code>
                  </span>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
                  <div className="px-4 py-2 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                      <span className="ml-2 font-medium text-slate-300">handler.py</span>
                    </div>
                    <span>Python 3.11</span>
                  </div>
                  <textarea
                    rows={12}
                    required
                    value={fnCode}
                    onChange={(e) => setFnCode(e.target.value)}
                    className="w-full p-4 bg-slate-900 text-emerald-400 font-mono text-xs sm:text-sm leading-relaxed focus:outline-none selection:bg-slate-700 resize-y"
                    spellCheck={false}
                  />
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setActiveTab('catalog')}
                  className="px-4 py-2.5 text-slate-600 hover:text-slate-900 text-sm font-semibold transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || fnMinReplicas > fnMaxReplicas}
                  className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition shadow-md shadow-indigo-600/20 flex items-center gap-2 cursor-pointer"
                >
                  <Zap className="w-4 h-4" />
                  <span>{loading ? 'Building Docker Image...' : 'Build & Deploy Function'}</span>
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Tab 3: Invocation Console */}
        {activeTab === 'invoke' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Column: Function Selector & Input Payload */}
              <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-2xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                      <Play className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-slate-900">Test & Invoke Function</h2>
                      <p className="text-xs text-slate-500">Send synchronous test payloads to execute handler</p>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Select Target Function
                  </label>
                  <select
                    value={selectedFn}
                    onChange={(e) => {
                      const name = e.target.value;
                      selectedFnRef.current = name;
                      setSelectedFn(name);
                      setInvokePayload(getSamplePayload(name));
                    }}
                    className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
                  >
                    {functions.map((fn) => (
                      <option key={fn.id} value={fn.name}>
                        {fn.name} ({fn.status}, {fn.active_replicas} pods)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono text-slate-700 flex items-center justify-between">
                  <span className="font-semibold truncate">POST /api/v1/invoke/{selectedFn || ':name'}</span>
                  <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-bold shrink-0">
                    JSON PAYLOAD
                  </span>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2 flex-wrap gap-1.5">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Event Input Payload
                    </label>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold">Presets:</span>
                      <button
                        type="button"
                        onClick={() => setInvokePayload('{\n  "name": "Developer"\n}')}
                        className="px-2 py-0.5 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md border border-slate-200 transition cursor-pointer"
                      >
                        name
                      </button>
                      <button
                        type="button"
                        onClick={() => setInvokePayload('{\n  "n": 25\n}')}
                        className="px-2 py-0.5 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md border border-slate-200 transition cursor-pointer"
                      >
                        n: 25
                      </button>
                      <button
                        type="button"
                        onClick={() => setInvokePayload('{\n  "x": 21\n}')}
                        className="px-2 py-0.5 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md border border-slate-200 transition cursor-pointer"
                      >
                        x: 21
                      </button>
                      <button
                        type="button"
                        onClick={() => setInvokePayload('{\n  "a": 6,\n  "b": 7\n}')}
                        className="px-2 py-0.5 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md border border-slate-200 transition cursor-pointer"
                      >
                        a & b
                      </button>
                      <button
                        type="button"
                        onClick={() => setInvokePayload('{}')}
                        className="px-2 py-0.5 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md border border-slate-200 transition cursor-pointer"
                      >
                        empty {}
                      </button>
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow-2xs">
                    <textarea
                      rows={8}
                      value={invokePayload}
                      onChange={(e) => setInvokePayload(e.target.value)}
                      className="w-full p-3.5 bg-slate-900 text-emerald-300 font-mono text-xs sm:text-sm focus:outline-none selection:bg-slate-700 resize-y"
                      spellCheck={false}
                    />
                  </div>
                </div>

                <button
                  onClick={handleInvoke}
                  disabled={invoking || !selectedFn}
                  className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition shadow-md shadow-emerald-600/20 flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Play className={`w-4 h-4 ${invoking ? 'animate-spin' : ''}`} />
                  <span>{invoking ? 'Executing on Kubernetes...' : 'Execute Function'}</span>
                </button>
              </div>

              {/* Right Column: Execution Latency Breakdown & Output */}
              <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-2xs flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-5 h-5 text-slate-700" />
                      <h2 className="text-base font-bold text-slate-900">Execution Telemetry & Result</h2>
                    </div>
                    {invokeResult && (
                      <span className={`text-xs px-2.5 py-1 rounded-full font-semibold border flex items-center gap-1.5 ${
                        invokeResult.executed_on === 'none' 
                          ? 'bg-rose-50 text-rose-700 border-rose-200' 
                          : invokeResult.is_cold_start 
                          ? 'bg-amber-50 text-amber-700 border-amber-200' 
                          : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          invokeResult.executed_on === 'none'
                            ? 'bg-rose-500'
                            : invokeResult.is_cold_start
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                        }`} />
                        <span>
                          {invokeResult.executed_on === 'none' 
                            ? 'Not Executed' 
                            : invokeResult.is_cold_start 
                            ? 'Cold Start (Pod Spun Up)' 
                            : 'Warm Invocation (Live Pod)'}
                        </span>
                      </span>
                    )}
                  </div>

                  {invokeResult ? (
                    <div className="space-y-4">
                      {/* Latency Timer Breakdown */}
                      <div className="grid grid-cols-3 gap-2 text-center bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Cold Start</div>
                          <div className="text-base font-bold text-amber-600 font-mono mt-0.5">
                            {invokeResult.cold_start_duration_ms} <span className="text-xs font-normal text-slate-400">ms</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Execution</div>
                          <div className="text-base font-bold text-emerald-600 font-mono mt-0.5">
                            {invokeResult.execution_duration_ms} <span className="text-xs font-normal text-slate-400">ms</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Total Latency</div>
                          <div className="text-base font-bold text-slate-900 font-mono mt-0.5">
                            {invokeResult.total_duration_ms} <span className="text-xs font-normal text-slate-400">ms</span>
                          </div>
                        </div>
                      </div>

                      {invokeResult.error ? (
                        <div className="space-y-1">
                          <label className="block text-xs font-bold text-rose-600 uppercase tracking-wider">
                            Execution / Runtime Error
                          </label>
                          <pre className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 font-mono text-xs overflow-x-auto max-h-64 leading-relaxed whitespace-pre-wrap">
                            {typeof invokeResult.error === 'string' ? invokeResult.error : JSON.stringify(invokeResult.error, null, 2)}
                          </pre>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                              Output Response
                            </label>
                            <button
                              onClick={() => copyToClipboard(
                                JSON.stringify(invokeResult.result, null, 2),
                                setCopiedOutput
                              )}
                              className="text-xs text-indigo-600 hover:text-indigo-700 flex items-center gap-1 font-medium cursor-pointer"
                            >
                              {copiedOutput ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                              <span>{copiedOutput ? 'Copied' : 'Copy Result'}</span>
                            </button>
                          </div>
                          <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow-2xs">
                            <pre className="p-4 text-emerald-300 font-mono text-xs overflow-x-auto max-h-64 leading-relaxed selection:bg-slate-700">
                              {invokeResult.result !== undefined && invokeResult.result !== null
                                ? JSON.stringify(invokeResult.result, null, 2)
                                : (invokeResult.result === null ? 'null (Function completed with no return value)' : 'No output')}
                            </pre>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="h-64 flex flex-col items-center justify-center text-slate-400 text-xs sm:text-sm border-2 border-dashed border-slate-200 rounded-2xl bg-slate-50/50">
                      <Terminal className="w-8 h-8 mb-2 text-slate-300" />
                      <span className="font-medium text-slate-600">No invocation executed yet.</span>
                      <span className="text-xs text-slate-400 mt-0.5">Click 'Execute Function' to inspect latency timings and output.</span>
                    </div>
                  )}
                </div>

                {invokeResult && (
                  <div className="text-xs text-slate-500 pt-4 border-t border-slate-100 mt-4 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span>Request ID:</span>
                      <button
                        onClick={() => copyToClipboard(invokeResult.request_id, setCopiedRequestId)}
                        className="font-mono text-slate-800 hover:text-indigo-600 flex items-center gap-1 font-semibold cursor-pointer"
                        title="Copy Request ID"
                      >
                        <span>{invokeResult.request_id}</span>
                        {copiedRequestId ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3 text-slate-400" />}
                      </button>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      invokeResult.status_code === 200 
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                        : 'bg-rose-50 text-rose-700 border border-rose-200'
                    }`}>
                      HTTP {invokeResult.status_code}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* API Access Panel Component (Integrated under Invocation) */}
            {selectedFn && (
              <ApiAccessPanel
                fnName={selectedFn}
                publicId={functions.find(f => f.name === selectedFn)?.public_id}
                token={token}
              />
            )}
          </div>
        )}

        {/* Tab 4: Logs */}
        {activeTab === 'logs' && (
          <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-2xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
              <div>
                <h2 className="text-lg font-bold text-slate-900 tracking-tight">Live Invocation Telemetry Logs</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Historical execution records with granular cold-start durations, pod metrics, and HTTP response codes.
                </p>
              </div>
              <button
                onClick={fetchData}
                className="self-start sm:self-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>Refresh Logs</span>
              </button>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-xl shadow-2xs">
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
                  {logs.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-slate-400 font-sans font-medium">
                        No logs recorded yet. Invocations will automatically stream here.
                      </td>
                    </tr>
                  ) : (
                    logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="px-4 py-3 font-sans text-slate-600 font-medium">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </td>
                        <td className="px-4 py-3 text-slate-800 font-semibold">{log.request_id.slice(0, 8)}...</td>
                        <td className="px-4 py-3 font-sans">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                            log.is_cold_start 
                              ? 'bg-amber-50 text-amber-700 border-amber-200' 
                              : 'bg-emerald-50 text-emerald-700 border-emerald-200'
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
                            log.status_code === 200 
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}>
                            {log.status_code}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 5: Cluster & Metrics */}
        {activeTab === 'cluster' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Architecture Card */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-2xs space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-slate-100">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">Platform Architecture & Topology</h2>
                  <p className="text-xs text-slate-500">Kubernetes cluster node bindings and daemon monitors</p>
                </div>
              </div>

              <div className="space-y-2.5 text-xs text-slate-700">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center justify-between">
                  <span className="font-semibold text-slate-600">Kubernetes Orchestrator:</span>
                  <span className="text-emerald-700 font-mono font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    {clusterStatus?.kubernetes?.info || 'Connected'}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center justify-between">
                  <span className="font-semibold text-slate-600">Function Namespace:</span>
                  <span className="text-slate-800 font-mono font-medium">
                    {clusterStatus?.kubernetes?.namespace || 'faas-fn'}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center justify-between">
                  <span className="font-semibold text-slate-600">Docker Local Registry:</span>
                  <span className="text-slate-800 font-mono font-medium">
                    {clusterStatus?.docker?.registry || 'localhost:5000'}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center justify-between">
                  <span className="font-semibold text-slate-600">Reaper Daemon Monitor:</span>
                  <span className="text-emerald-700 font-mono font-semibold">Running (checks every 10s)</span>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center justify-between">
                  <span className="font-semibold text-slate-600">Idle Scale-Down Threshold:</span>
                  <span className="text-amber-700 font-mono font-semibold">60 seconds</span>
                </div>
              </div>

              {/* Explainer Box */}
              <div className="p-4 bg-indigo-50/70 border border-indigo-200/70 rounded-xl text-xs text-indigo-900 leading-relaxed space-y-1.5">
                <div className="font-bold flex items-center gap-1.5 text-indigo-800">
                  <Info className="w-4 h-4 text-indigo-600" />
                  <span>How Scale-to-Zero Orchestration Operates:</span>
                </div>
                <p>
                  When a function remains idle for &gt;60s without incoming HTTP invocations, the FaaS controller daemon scales deployment replicas to 0. Upon receiving the next invocation, the controller triggers on-demand pod readiness, measures the cold-start duration, and dispatches the execution event payload.
                </p>
              </div>
            </div>

            {/* Prometheus Observability Card */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-2xs space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-slate-100">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                  <BarChart3 className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">Observability & Prometheus Exporter</h2>
                  <p className="text-xs text-slate-500">Standardized metrics ready for Prometheus scraping & Grafana</p>
                </div>
              </div>

              <div className="p-4 bg-slate-900 rounded-xl border border-slate-800 font-mono text-xs text-slate-300 space-y-2.5 shadow-2xs">
                <div className="text-slate-400 text-[11px] font-medium"># Metric Exporter Endpoint:</div>
                <div className="text-indigo-400 font-semibold">GET /api/v1/metrics</div>
                <div className="text-slate-400 text-[11px] font-medium pt-2"># Exported Metric Series:</div>
                <div className="text-emerald-400">• faas_invocations_total&#123;function, status&#125;</div>
                <div className="text-amber-400">• faas_cold_starts_total&#123;function&#125;</div>
                <div className="text-indigo-300">• faas_invocation_duration_seconds&#123;function, type&#125;</div>
                <div className="text-cyan-400">• faas_active_replicas&#123;function&#125;</div>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <a
                  href="/api/v1/metrics"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-semibold"
                >
                  <span>Inspect Raw Prometheus Metrics Stream</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>

                <span className="text-[11px] text-slate-400 font-mono">OpenMetrics 1.0.0</span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/80 bg-white/60 py-4 px-6 text-center text-xs text-slate-500 mt-12">
        <p>Kubernetes Serverless FaaS Platform &bull; Advanced Cloud Computing</p>
      </footer>
    </div>
  );
}
