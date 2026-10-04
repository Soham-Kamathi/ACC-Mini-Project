import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import ApiAccessPanel from './ApiAccessPanel';
import { 
  Server, Play, Plus, RefreshCw, Trash2, Clock, Cpu, 
  Database, Activity, Zap, CheckCircle2, AlertCircle, 
  Terminal, BarChart3, Code2, Layers, ShieldCheck, Box
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
      setAuthError(err.response?.data?.detail || 'Authentication failed');
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
      setDeployMsg(`Function '${fnName}' created and submitted for image build & deployment!`);
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

  // Auth Screen
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950 px-4">
        <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
          <div className="flex items-center gap-3 justify-center mb-6">
            <div className="p-3 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30">
              <Zap className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">K8s FaaS Platform</h1>
              <p className="text-xs text-slate-400">Serverless Function Engine</p>
            </div>
          </div>

          {authError && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/40 text-red-300 text-sm rounded-lg flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleAuth} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Username</label>
              <input
                type="text"
                required
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>

            {authMode === 'register' && (
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  className="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500 text-sm"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Password</label>
              <input
                type="password"
                required
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition text-sm shadow-lg shadow-blue-600/20"
            >
              {authMode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <button
              onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
              className="hover:text-blue-400 underline"
            >
              {authMode === 'login' ? "Need an account? Register" : "Already have an account? Sign In"}
            </button>
            <button
              onClick={autoDemoLogin}
              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 rounded text-slate-300 border border-slate-700"
            >
              1-Click Demo Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col text-slate-100">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-lg text-white shadow-md shadow-blue-500/20">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-lg text-white tracking-tight flex items-center gap-2">
              K8s FaaS Platform
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">v1.0.0</span>
            </h1>
          </div>
        </div>

        {/* Cluster / System Status Pills */}
        <div className="hidden md:flex items-center gap-3 text-xs">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700">
            <span className={`w-2 h-2 rounded-full ${clusterStatus?.kubernetes?.status === 'online' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
            <span className="text-slate-300">K8s:</span>
            <span className="font-medium text-white">{clusterStatus?.kubernetes?.status === 'online' ? 'Connected' : 'Standalone'}</span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-slate-300">Scale-to-Zero:</span>
            <span className="font-medium text-emerald-400">Active</span>
          </div>
        </div>

        {/* User Account Controls */}
        <div className="flex items-center gap-4">
          <span className="text-xs text-slate-300 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700">
            User: <strong className="text-white">{username}</strong>
          </span>
          <button
            onClick={fetchData}
            title="Refresh State"
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition border border-transparent hover:border-slate-700"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleLogout}
            className="text-xs text-slate-400 hover:text-red-400 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {backendBusy && (
          <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300">
            <AlertCircle className="w-4 h-4 shrink-0" />
            The backend is busy or unreachable. Showing the last data received; retrying automatically.
          </div>
        )}
        
        {/* KPI Stat Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase mb-2">
                <span>Total Functions</span>
                <Box className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-2xl font-bold text-white">{stats.total_functions}</div>
              <div className="text-xs text-slate-500 mt-1">{stats.scaled_to_zero_count} currently scaled to zero</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase mb-2">
                <span>Active Pod Replicas</span>
                <Server className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-emerald-400">{stats.active_replicas}</div>
              <div className="text-xs text-slate-500 mt-1">Live container pods in cluster</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase mb-2">
                <span>Total Invocations</span>
                <Activity className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-2xl font-bold text-white">{stats.total_invocations}</div>
              <div className="text-xs text-slate-500 mt-1">{stats.cold_start_count} cold starts ({stats.cold_start_ratio_pct}%)</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase mb-2">
                <span>Avg Warm Latency</span>
                <Clock className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-amber-400">{stats.avg_execution_duration_ms} <span className="text-xs text-slate-400 font-normal">ms</span></div>
              <div className="text-xs text-slate-500 mt-1">Cold start avg: {stats.avg_cold_start_duration_ms} ms</div>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 space-x-6 text-sm font-medium">
          <button
            onClick={() => setActiveTab('catalog')}
            className={`pb-3 border-b-2 flex items-center gap-2 transition ${activeTab === 'catalog' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            <Layers className="w-4 h-4" />
            Function Catalog ({functions.length})
          </button>
          <button
            onClick={() => setActiveTab('create')}
            className={`pb-3 border-b-2 flex items-center gap-2 transition ${activeTab === 'create' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            <Plus className="w-4 h-4" />
            Create & Deploy Function
          </button>
          <button
            onClick={() => setActiveTab('invoke')}
            className={`pb-3 border-b-2 flex items-center gap-2 transition ${activeTab === 'invoke' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            <Play className="w-4 h-4" />
            Invocation Console
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            className={`pb-3 border-b-2 flex items-center gap-2 transition ${activeTab === 'logs' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            <Terminal className="w-4 h-4" />
            Invocation Logs
          </button>
          <button
            onClick={() => setActiveTab('cluster')}
            className={`pb-3 border-b-2 flex items-center gap-2 transition ${activeTab === 'cluster' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            <BarChart3 className="w-4 h-4" />
            Cluster & Metrics
          </button>
        </div>

        {/* Tab 1: Catalog */}
        {activeTab === 'catalog' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Registered Functions</h2>
              <button
                onClick={() => setActiveTab('create')}
                className="flex items-center gap-2 px-3.5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium shadow"
              >
                <Plus className="w-4 h-4" /> New Function
              </button>
            </div>

            {functions.length === 0 ? (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center">
                <Box className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                <h3 className="text-lg font-medium text-white">No functions registered yet</h3>
                <p className="text-slate-400 text-sm max-w-sm mx-auto mt-1 mb-6">
                  Create your first serverless function to build a Docker image and deploy it on Kubernetes.
                </p>
                <button
                  onClick={() => setActiveTab('create')}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold inline-flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" /> Create Function
                </button>
              </div>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {functions.map((fn) => (
                  <div key={fn.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition flex flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h3 className="font-bold text-white text-base tracking-tight font-mono">{fn.name}</h3>
                        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${
                          fn.status === 'RUNNING' || fn.status === 'READY'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : fn.status === 'SCALED_TO_ZERO'
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                            : fn.status === 'BUILDING'
                            ? 'bg-blue-500/10 text-blue-400 border-blue-500/30 animate-pulse'
                            : 'bg-red-500/10 text-red-400 border-red-500/30'
                        }`}>
                          {fn.status}
                        </span>
                      </div>

                      <p className="text-xs text-slate-400 mb-4 line-clamp-2">{fn.description || 'No description provided'}</p>

                      <div className="space-y-1.5 text-xs text-slate-400 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 mb-4">
                        <div className="flex justify-between">
                          <span>Runtime:</span>
                          <span className="text-slate-200 font-mono">{fn.runtime}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Replicas:</span>
                          <span className="text-slate-200">{fn.active_replicas} pod(s) <span className="text-slate-500">(autoscale {fn.min_replicas}-{fn.max_replicas})</span></span>
                        </div>
                        <div className="flex justify-between">
                          <span>Resource Limits:</span>
                          <span className="text-slate-200">{fn.memory_limit} / {fn.cpu_limit}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Timeout:</span>
                          <span className="text-slate-200">{fn.timeout_seconds}s</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-3 border-t border-slate-800/80">
                      <button
                        onClick={() => {
                          selectedFnRef.current = fn.name;
                          setSelectedFn(fn.name);
                          setInvokePayload(getSamplePayload(fn.name));
                          setActiveTab('invoke');
                        }}
                        className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition"
                      >
                        <Play className="w-3.5 h-3.5" /> Invoke
                      </button>

                      <button
                        onClick={() => handleDelete(fn.name)}
                        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-slate-800 rounded-lg transition"
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
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-1">Create & Deploy Serverless Function</h2>
            <p className="text-xs text-slate-400 mb-6">Packages user Python code into a standardized Docker container and deploys to Kubernetes.</p>

            {deployMsg && (
              <div className={`mb-6 p-4 rounded-xl text-sm border flex items-center gap-3 ${deployMsg.startsWith('Error') ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'}`}>
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <span>{deployMsg}</span>
              </div>
            )}

            {/* Template Selector */}
            <div className="mb-6">
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Quick Starter Templates</label>
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
                    className="p-3 bg-slate-950 border border-slate-800 hover:border-blue-500/50 rounded-xl text-left transition"
                  >
                    <div className="font-semibold text-sm text-white">{t.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{t.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleDeploy} className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Function Name</label>
                  <input
                    type="text"
                    required
                    value={fnName}
                    onChange={(e) => setFnName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                    placeholder="my-function"
                    className="w-full px-3.5 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Runtime</label>
                  <select
                    value={fnRuntime}
                    onChange={(e) => setFnRuntime(e.target.value)}
                    className="w-full px-3.5 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  >
                    <option value="python311">Python 3.11 (Standard)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Memory Limit</label>
                  <select
                    value={fnMemory}
                    onChange={(e) => setFnMemory(e.target.value)}
                    className="w-full px-3.5 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  >
                    <option value="128Mi">128 MB (Micro)</option>
                    <option value="256Mi">256 MB (Standard)</option>
                    <option value="512Mi">512 MB (High Memory)</option>
                    <option value="1024Mi">1024 MB (Max)</option>
                  </select>
                </div>
              </div>

              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
                <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Autoscaling</div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1">Min replicas</label>
                    <input type="number" min={0} max={20} value={fnMinReplicas}
                      onChange={(e) => setFnMinReplicas(Math.max(0, Number(e.target.value)))}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1">Max replicas</label>
                    <input type="number" min={1} max={20} value={fnMaxReplicas}
                      onChange={(e) => setFnMaxReplicas(Math.max(1, Number(e.target.value)))}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1">Requests per pod</label>
                    <input type="number" min={1} max={100} value={fnTargetConc}
                      onChange={(e) => setFnTargetConc(Math.max(1, Number(e.target.value)))}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500" />
                  </div>
                </div>
                <p className="text-[11px] text-slate-500">
                  Pods are added when concurrent requests exceed what the current pods are sized for, up to the maximum. Min 0 allows scale-to-zero when idle; a higher minimum keeps pods warm. Set min = max for a fixed count.
                </p>
                {fnMinReplicas > fnMaxReplicas && (
                  <p className="text-[11px] text-red-400">Min replicas must not exceed max replicas.</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Description</label>
                <input
                  type="text"
                  value={fnDesc}
                  onChange={(e) => setFnDesc(e.target.value)}
                  placeholder="Optional function description"
                  className="w-full px-3.5 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Source Code (handler.py)</label>
                  <span className="text-xs text-slate-500 font-mono">def handler(event):</span>
                </div>
                <textarea
                  rows={12}
                  required
                  value={fnCode}
                  onChange={(e) => setFnCode(e.target.value)}
                  className="w-full p-4 bg-slate-950 border border-slate-700 rounded-xl text-emerald-400 font-mono text-sm leading-relaxed focus:outline-none focus:border-blue-500"
                  spellCheck={false}
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setActiveTab('catalog')}
                  className="px-4 py-2 text-slate-400 hover:text-white text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm transition shadow-lg shadow-blue-600/20 flex items-center gap-2"
                >
                  <Zap className="w-4 h-4" />
                  {loading ? 'Building & Deploying...' : 'Build & Deploy Function'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Tab 3: Invocation Console */}
        {activeTab === 'invoke' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column: Function Selector & Input Payload */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <Play className="w-5 h-5 text-blue-400" /> Test & Invoke Endpoint
              </h2>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Select Function</label>
                <select
                  value={selectedFn}
                  onChange={(e) => {
                    const fnName = e.target.value;
                    selectedFnRef.current = fnName;
                    setSelectedFn(fnName);
                    setInvokePayload(getSamplePayload(fnName));
                  }}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
                >
                  {functions.map(fn => (
                    <option key={fn.id} value={fn.name}>
                      {fn.name} ({fn.status}, {fn.active_replicas} pods)
                    </option>
                  ))}
                </select>
              </div>

              <div className="p-3 bg-slate-950/70 border border-slate-800 rounded-lg text-xs font-mono text-slate-300 flex items-center justify-between">
                <span>POST /api/v1/invoke/{selectedFn || ':name'}</span>
                <span className="text-blue-400">JSON Payload</span>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5 flex-wrap gap-1">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Event Input (JSON)</label>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wide">Presets:</span>
                    <button
                      type="button"
                      onClick={() => setInvokePayload('{\n  "name": "Developer"\n}')}
                      className="px-2 py-0.5 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                    >
                      name
                    </button>
                    <button
                      type="button"
                      onClick={() => setInvokePayload('{\n  "n": 25\n}')}
                      className="px-2 py-0.5 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                    >
                      n: 25
                    </button>
                    <button
                      type="button"
                      onClick={() => setInvokePayload('{\n  "x": 21\n}')}
                      className="px-2 py-0.5 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                    >
                      x: 21
                    </button>
                    <button
                      type="button"
                      onClick={() => setInvokePayload('{\n  "a": 6,\n  "b": 7\n}')}
                      className="px-2 py-0.5 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                    >
                      a & b
                    </button>
                    <button
                      type="button"
                      onClick={() => setInvokePayload('{}')}
                      className="px-2 py-0.5 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                    >
                      empty {'{}'}
                    </button>
                  </div>
                </div>
                <textarea
                  rows={8}
                  value={invokePayload}
                  onChange={(e) => setInvokePayload(e.target.value)}
                  className="w-full p-3.5 bg-slate-950 border border-slate-700 rounded-xl text-slate-100 font-mono text-sm focus:outline-none focus:border-blue-500"
                  spellCheck={false}
                />
              </div>

              <button
                onClick={handleInvoke}
                disabled={invoking || !selectedFn}
                className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2"
              >
                <Play className={`w-4 h-4 ${invoking ? 'animate-spin' : ''}`} />
                {invoking ? 'Executing Function...' : 'Execute Function'}
              </button>
            </div>

            {/* Right Column: Execution Latency Breakdown & Output */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center justify-between">
                  <span>Execution Result</span>
                  {invokeResult && (
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium border ${invokeResult.executed_on === 'none' ? 'bg-red-500/10 text-red-400 border-red-500/30' : invokeResult.is_cold_start ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'}`}>
                      {invokeResult.executed_on === 'none' ? 'Not Executed' : invokeResult.is_cold_start ? 'Cold Start' : 'Warm Invocation'}
                    </span>
                  )}
                </h2>

                {invokeResult ? (
                  <div className="space-y-4">
                    {/* Latency Timer Breakdown */}
                    <div className="grid grid-cols-3 gap-2 text-center bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Cold Start</div>
                        <div className="text-sm font-bold text-amber-400 font-mono">{invokeResult.cold_start_duration_ms} ms</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Execution</div>
                        <div className="text-sm font-bold text-emerald-400 font-mono">{invokeResult.execution_duration_ms} ms</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Total Latency</div>
                        <div className="text-sm font-bold text-white font-mono">{invokeResult.total_duration_ms} ms</div>
                      </div>
                    </div>

                    {invokeResult.error ? (
                      <div>
                        <label className="block text-xs font-semibold text-rose-400 uppercase tracking-wider mb-1">Execution / Runtime Error</label>
                        <pre className="p-4 bg-rose-950/40 border border-rose-800/60 rounded-xl text-rose-300 font-mono text-xs overflow-x-auto max-h-64 leading-relaxed whitespace-pre-wrap">
                          {typeof invokeResult.error === 'string' ? invokeResult.error : JSON.stringify(invokeResult.error, null, 2)}
                        </pre>
                      </div>
                    ) : (
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">Output Payload</label>
                        <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-emerald-400 font-mono text-xs overflow-x-auto max-h-64 leading-relaxed">
                          {invokeResult.result !== undefined && invokeResult.result !== null
                            ? JSON.stringify(invokeResult.result, null, 2)
                            : (invokeResult.result === null ? 'null (Function completed with no return value)' : 'No output')}
                        </pre>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl">
                    <Terminal className="w-8 h-8 mb-2 opacity-50" />
                    <span>Run an invocation to inspect results and latency timings.</span>
                  </div>
                )}
              </div>

              {invokeResult && (
                <div className="text-xs text-slate-500 pt-4 border-t border-slate-800 mt-4 flex items-center justify-between">
                  <span>Request ID: <span className="font-mono text-slate-400">{invokeResult.request_id}</span></span>
                  <span>HTTP {invokeResult.status_code}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'invoke' && selectedFn && (
          <ApiAccessPanel
            fnName={selectedFn}
            publicId={functions.find(f => f.name === selectedFn)?.public_id}
            token={token}
          />
        )}

        {/* Tab 4: Logs */}
        {activeTab === 'logs' && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-1">Live Invocation Logs</h2>
            <p className="text-xs text-slate-400 mb-4">Historical execution records with cold-start indicators and latency telemetry.</p>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-semibold border-b border-slate-800">
                  <tr>
                    <th className="p-3">Timestamp</th>
                    <th className="p-3">Request ID</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Cold Start (ms)</th>
                    <th className="p-3">Exec Time (ms)</th>
                    <th className="p-3">Total (ms)</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono">
                  {logs.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-6 text-center text-slate-500">
                        No logs recorded yet.
                      </td>
                    </tr>
                  ) : (
                    logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-800/40 transition">
                        <td className="p-3 text-slate-400">{new Date(log.timestamp).toLocaleTimeString()}</td>
                        <td className="p-3 font-mono text-slate-300">{log.request_id.slice(0, 8)}...</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-sans ${log.is_cold_start ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'}`}>
                            {log.is_cold_start ? 'COLD' : 'WARM'}
                          </span>
                        </td>
                        <td className="p-3 text-amber-400">{log.cold_start_duration_ms}</td>
                        <td className="p-3 text-emerald-400">{log.execution_duration_ms}</td>
                        <td className="p-3 text-white font-bold">{log.total_duration_ms}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded font-sans ${log.status_code === 200 ? 'text-emerald-400' : 'text-red-400'}`}>
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
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-blue-400" /> Platform Architecture & Topology
              </h2>

              <div className="space-y-3 text-xs text-slate-300">
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                  <span className="font-semibold text-slate-400">Kubernetes Orchestrator:</span>
                  <span className="text-emerald-400 font-mono">{clusterStatus?.kubernetes?.info || 'Connected'}</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                  <span className="font-semibold text-slate-400">Function Namespace:</span>
                  <span className="text-slate-200 font-mono">{clusterStatus?.kubernetes?.namespace || 'faas-fn'}</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                  <span className="font-semibold text-slate-400">Docker Registry:</span>
                  <span className="text-slate-200 font-mono">{clusterStatus?.docker?.registry || 'localhost:5000'}</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                  <span className="font-semibold text-slate-400">Reaper Daemon:</span>
                  <span className="text-emerald-400 font-mono">Running (checks every 10s)</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
                  <span className="font-semibold text-slate-400">Idle Scale-Down Threshold:</span>
                  <span className="text-amber-400 font-mono">60 seconds</span>
                </div>
              </div>

              <div className="p-4 bg-blue-950/20 border border-blue-800/30 rounded-xl text-xs text-blue-300">
                <strong>How scale-to-zero works:</strong> When a function remains idle for &gt;60s without invocations, the FaaS controller daemon scales deployment replicas to 0. Upon the next invocation request, the controller triggers on-demand pod readiness, measures cold-start latency, and executes the handler.
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-indigo-400" /> Observability & Prometheus Exporter
              </h2>
              <p className="text-xs text-slate-400">Metrics are actively scraped by Prometheus and can be visualized on Grafana dashboards.</p>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs text-slate-300 space-y-2">
                <div className="text-slate-500"># Metric Exporter Endpoint:</div>
                <div className="text-blue-400">GET /api/v1/metrics</div>
                <div className="text-slate-500 pt-2"># Exported Metric Series:</div>
                <div className="text-emerald-400">• faas_invocations_total&#123;function, status&#125;</div>
                <div className="text-amber-400">• faas_cold_starts_total&#123;function&#125;</div>
                <div className="text-indigo-400">• faas_invocation_duration_seconds&#123;function, type&#125;</div>
                <div className="text-cyan-400">• faas_active_replicas&#123;function&#125;</div>
              </div>

              <a
                href="/api/v1/metrics"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300 font-medium"
              >
                Inspect Raw Prometheus Metrics Stream &rarr;
              </a>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
