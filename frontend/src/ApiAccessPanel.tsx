import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { KeyRound, Copy, RotateCw, Trash2, Plus, Check, ShieldAlert, Code2, Sparkles } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface ApiKeyItem {
  id: number;
  key_prefix: string;
  label: string;
  version_tag: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

interface Props {
  fnName: string;
  publicId?: string;
  token: string | null;
  invokePayload?: string;
}

export default function ApiAccessPanel({ fnName, publicId, token, invokePayload }: Props) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [label, setLabel] = useState('');
  const [pinVersion, setPinVersion] = useState('');
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');

  const headers = { headers: { Authorization: `Bearer ${token}` } };
  const base = `${API_BASE}/functions/${fnName}/keys`;
  // Absolute URL that callers outside the dashboard should use
  const origin = API_BASE.startsWith('http') ? API_BASE : `${window.location.origin}${API_BASE}`;
  const endpoint = `${origin}/f/${publicId ?? '<public_id>'}`;

  const load = useCallback(async () => {
    if (!fnName || !token) return;
    try {
      const resp = await axios.get(base, { headers: { Authorization: `Bearer ${token}` } });
      setKeys(resp.data);
      setError('');
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not load API keys');
    }
  }, [fnName, token, base]);

  useEffect(() => {
    setNewKey(null);
    setKeys([]);
    load();
  }, [load]);

  const copy = (text: string, id: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(''), 2000);
  };

  const create = async () => {
    try {
      const resp = await axios.post(base, {
        label: label.trim() || 'default',
        version_tag: pinVersion.trim() || null,
      }, headers);
      setNewKey(resp.data.api_key);
      setLabel('');
      setPinVersion('');
      load();
    } catch (e: any) {
      const d = e.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Could not create key (check the version pin format)');
    }
  };

  const rotate = async (id: number) => {
    try {
      const resp = await axios.post(`${base}/${id}/rotate`, {}, headers);
      setNewKey(resp.data.api_key);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not rotate key');
    }
  };

  const revoke = async (id: number) => {
    if (!window.confirm('Revoke this key? Anything using it will stop working immediately.')) return;
    try {
      await axios.delete(`${base}/${id}`, headers);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not revoke key');
    }
  };

  const keyText = newKey ?? '<your_api_key>';

  let formattedJsonPayload: any = { name: "World" };
  try {
    if (invokePayload && invokePayload.trim()) {
      formattedJsonPayload = JSON.parse(invokePayload.trim());
    } else {
      const lower = fnName.toLowerCase();
      if (lower.includes('fib') || lower.includes('bench') || lower.includes('calc')) {
        formattedJsonPayload = { n: 25 };
      } else if (lower.includes('multiplier')) {
        formattedJsonPayload = { a: 6, b: 7 };
      } else if (lower.includes('double')) {
        formattedJsonPayload = { x: 21 };
      } else {
        formattedJsonPayload = { name: "Developer" };
      }
    }
  } catch {
    formattedJsonPayload = { name: "Developer" };
  }

  const compactPayload = JSON.stringify(formattedJsonPayload);
  const pythonPayloadIndent = JSON.stringify(formattedJsonPayload, null, 4).replace(/\n/g, '\n    ');

  const curl = `curl -X POST ${endpoint} \\\n  -H "X-API-Key: ${keyText}" \\\n  -H "ngrok-skip-browser-warning: true" \\\n  -H "Content-Type: application/json" \\\n  -d '${compactPayload}'`;
  const python = `import requests\n\nresp = requests.post(\n    "${endpoint}",\n    headers={\n        "X-API-Key": "${keyText}",\n        "ngrok-skip-browser-warning": "true"\n    },\n    json=${pythonPayloadIndent},\n)\nprint(resp.json().get("result", resp.json()))`;

  if (!fnName) return null;

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-6 mt-6 transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200/60 flex items-center justify-center text-amber-600 shadow-sm">
            <KeyRound className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-slate-900">API Access & Public Endpoints</h2>
              <span className="font-mono text-xs px-2.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200/60 font-semibold">
                {fnName}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Securely invoke this function from microservices, webhooks, or external applications with scoped API keys.
            </p>
          </div>
        </div>
      </div>

      {/* Endpoint URL Pill */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
          <span>Public HTTPS Invocation Target</span>
        </div>
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono text-slate-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 overflow-hidden text-ellipsis whitespace-nowrap">
            <span className="px-2 py-0.5 bg-indigo-600 text-white rounded font-bold text-[10px] tracking-wide shrink-0">
              POST
            </span>
            <span className="font-medium text-slate-700 break-all select-all">{endpoint}</span>
          </div>
          <button
            onClick={() => copy(endpoint, 'endpoint')}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-lg shadow-2xs transition-colors shrink-0 cursor-pointer"
            title="Copy endpoint"
          >
            {copied === 'endpoint' ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-600" />
                <span className="text-emerald-600 font-semibold text-[11px]">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-[11px]">Copy URL</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* New Key Alert Banner */}
      {newKey && (
        <div className="p-4 bg-amber-50/90 border border-amber-300 rounded-xl space-y-2.5 shadow-sm animate-in fade-in duration-200">
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-900">
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
            <span>Copy your newly generated API key now. For security, it will not be displayed again.</span>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all text-xs text-amber-950 bg-white border border-amber-200 p-2.5 rounded-lg font-mono font-medium shadow-2xs select-all">
              {newKey}
            </code>
            <button
              onClick={() => copy(newKey, 'key')}
              className="px-3 py-2 text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-lg shadow-sm transition flex items-center gap-1.5 shrink-0 cursor-pointer"
            >
              {copied === 'key' ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Key</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Create Key Controls */}
      <div className="bg-slate-50/70 border border-slate-200/80 rounded-xl p-4">
        <div className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-3 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
          <span>Provision New Scoped Key</span>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[180px]">
            <label className="block text-[11px] font-medium text-slate-600 mb-1">Key Description / Label</label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. mobile-production, stripe-webhook"
              className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
            />
          </div>
          <div className="w-full sm:w-44">
            <label className="block text-[11px] font-medium text-slate-600 mb-1">Pin Version (Optional)</label>
            <input
              value={pinVersion}
              onChange={(e) => setPinVersion(e.target.value)}
              placeholder="e.g. v1 (blank = latest)"
              className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition"
            />
          </div>
          <button
            onClick={create}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm hover:shadow transition flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-4 h-4" /> Generate Key
          </button>
        </div>

        {error && (
          <div className="mt-3 text-xs text-rose-600 font-medium bg-rose-50 border border-rose-200 rounded-lg p-2.5 flex items-center gap-2">
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Keys Table */}
      <div>
        <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
          Active Key Credentials ({keys.length})
        </div>
        <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white shadow-2xs">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50/90 text-slate-600 uppercase text-[10px] font-bold border-b border-slate-200 tracking-wider">
              <tr>
                <th className="px-4 py-3">Key Prefix</th>
                <th className="px-4 py-3">Label</th>
                <th className="px-4 py-3">Target Version</th>
                <th className="px-4 py-3">Last Active</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keys.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400 font-medium">
                    No API keys created yet for this function.
                  </td>
                </tr>
              ) : (
                keys.map((k) => (
                  <tr key={k.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-slate-900">{k.key_prefix}••••••••</td>
                    <td className="px-4 py-3 font-medium text-slate-800">{k.label}</td>
                    <td className="px-4 py-3">
                      <span className="font-mono px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700 border border-slate-200">
                        {k.version_tag || 'latest'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {k.last_used_at ? new Date(k.last_used_at + 'Z').toLocaleString() : 'Never used'}
                    </td>
                    <td className="px-4 py-3">
                      {k.revoked ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                          Revoked
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {!k.revoked && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => rotate(k.id)}
                            className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition cursor-pointer"
                            title="Rotate Key"
                          >
                            <RotateCw className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => revoke(k.id)}
                            className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                            title="Revoke Key"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Code Examples */}
      <div>
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
          <Code2 className="w-3.5 h-3.5 text-slate-500" />
          <span>Integration Code Samples</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[
            ['cURL (Terminal)', curl],
            ['Python (Requests)', python],
          ].map(([title, code]) => (
            <div key={title} className="relative rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
              <div className="px-4 py-2 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
                <span className="text-[11px] font-mono font-medium text-slate-300">{title}</span>
                <button
                  onClick={() => copy(code, title)}
                  className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-white transition cursor-pointer"
                  title="Copy code snippet"
                >
                  {copied === title ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-400" />
                      <span className="text-emerald-400 font-medium">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-4 text-[11px] text-emerald-300 font-mono overflow-x-auto leading-relaxed selection:bg-slate-700">
                {code}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
